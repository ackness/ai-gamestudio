"""Plugin Agent — post-narrative function-calling agent for game mechanics."""
from __future__ import annotations

import asyncio
import json
import pathlib
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import litellm
from loguru import logger

from backend.app.core.block_validation import validate_block_data
from backend.app.core.config import settings
from backend.app.core.game_db import GameDB
from backend.app.core.llm_config import ResolvedLlmConfig
from backend.app.core.network_safety import ensure_safe_api_base
from backend.app.core.plugin_engine import BlockDeclaration, PluginEngine
from backend.app.core.plugin_hooks import DEFAULT_PLUGIN_HOOK, normalize_plugin_hooks
from backend.app.core.plugin_trigger import (
    BLOCK_TRIGGER_ONCE_PER_SESSION,
    PLUGIN_TRIGGER_INTERVAL,
    PLUGIN_TRIGGER_MANUAL,
    normalize_block_trigger_policy,
    normalize_plugin_trigger_policy,
)
from backend.app.core.plugin_tools import get_all_tools
from backend.app.core.script_runner import PythonScriptRunner
from backend.app.api.debug_log import _add_log

MAX_TOOL_ROUNDS = 8

ProgressCallback = Any  # Callable[[dict], None] — optional sync callback

SINGLE_PLUGIN_SYSTEM_PROMPT = """\
你是游戏插件代理。分析 DM 叙事，按插件指令执行游戏机制。

## 规则
- 当前游戏状态已在上下文中，无需 db_read 查询已有数据
- 优先一次调用 emit 同时完成写库（writes/logs）和结构化输出（items）
- 叙事中没有相关变化则直接结束，不要臆造
"""


def _agent_prompt_config(metadata: dict[str, Any]) -> dict[str, Any]:
    extensions = metadata.get("extensions")
    if not isinstance(extensions, dict):
        return {}
    cfg = extensions.get("agent_prompt")
    return cfg if isinstance(cfg, dict) else {}


def _resolve_prompt_file(plugin_root: pathlib.Path | None, rel_path: str | None) -> pathlib.Path | None:
    if plugin_root is None:
        return None
    rel = str(rel_path or "").strip()
    if not rel:
        return None
    try:
        candidate = (plugin_root / rel).resolve()
    except Exception:
        return None
    if not candidate.is_file():
        return None
    if not candidate.is_relative_to(plugin_root):
        return None
    return candidate


def _read_prompt_file(path: pathlib.Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _resolve_base_prompt(
    plugin_root: pathlib.Path | None,
    metadata: dict[str, Any],
    fallback_content: str,
) -> str:
    cfg = _agent_prompt_config(metadata)
    base_path = _resolve_prompt_file(plugin_root, cfg.get("base_file"))
    if base_path is None:
        base_path = _resolve_prompt_file(plugin_root, "prompts/agent/base.md")
    text = _read_prompt_file(base_path)
    return text or fallback_content


def _sanitize_plugin_prompt(content: str) -> str:
    """Remove legacy JSON-block wording to keep the model on tool-calling rails."""
    lines: list[str] = []
    for raw in str(content or "").splitlines():
        lower = raw.lower()
        if "json:" in lower:
            continue
        if "update_and_emit" in lower:
            continue
        if "emit_block" in lower:
            continue
        lines.append(raw)
    text = "\n".join(lines).strip()
    return text or "遵循插件目标；所有结构化输出通过 emit.items 产生。"


def _resolve_output_instruction(
    *,
    plugin_root: pathlib.Path | None,
    metadata: dict[str, Any],
    output_type: str,
    output_cfg: dict[str, Any],
) -> str:
    cfg = _agent_prompt_config(metadata)
    output_files = cfg.get("output_files") if isinstance(cfg.get("output_files"), dict) else {}
    candidate_rel = str(output_cfg.get("instruction_file") or "").strip()
    if not candidate_rel and isinstance(output_files, dict):
        mapped = output_files.get(output_type)
        if mapped is not None:
            candidate_rel = str(mapped or "").strip()
    if not candidate_rel:
        candidate_rel = f"prompts/agent/outputs/{output_type}.md"

    text = _read_prompt_file(_resolve_prompt_file(plugin_root, candidate_rel))
    if text:
        return _sanitize_plugin_prompt(text)

    return _sanitize_plugin_prompt(str(output_cfg.get("instruction") or "").strip())


def _build_tool_instructions(
    *,
    plugin_root: pathlib.Path | None,
    metadata: dict[str, Any],
    tools: list[dict[str, Any]],
) -> str:
    cfg = _agent_prompt_config(metadata)
    tool_files = cfg.get("tool_files") if isinstance(cfg.get("tool_files"), dict) else {}
    parts: list[str] = []
    for tool in tools:
        func = tool.get("function")
        if not isinstance(func, dict):
            continue
        tool_name = str(func.get("name") or "").strip()
        if not tool_name:
            continue
        rel = ""
        if isinstance(tool_files, dict):
            mapped = tool_files.get(tool_name)
            if mapped is not None:
                rel = str(mapped or "").strip()
        if not rel:
            rel = f"prompts/agent/tools/{tool_name}.md"
        text = _read_prompt_file(_resolve_prompt_file(plugin_root, rel))
        if text:
            sanitized = _sanitize_plugin_prompt(text)
            if sanitized:
                parts.append(f"### {tool_name}\n{sanitized}")
    return "\n\n".join(parts)


def _example_string_for_key(key: str) -> str:
    mapping = {
        "action": "create",
        "character_id": "new",
        "content": "提示内容",
        "description": "简短描述",
        "event_id": "event_001",
        "event_type": "world",
        "id": "id_001",
        "key": "key_001",
        "level": "info",
        "name": "名称",
        "prompt": "请选择下一步行动",
        "quest_id": "quest_001",
        "session_id": "session_001",
        "source": "dm",
        "status": "active",
        "title": "标题",
        "turn_id": "turn_001",
        "type": "single",
        "visibility": "known",
    }
    return mapping.get(key, "text")


def _build_example_from_schema(schema: dict[str, Any] | None, *, key: str = "") -> Any:
    if not isinstance(schema, dict):
        return {}

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((t for t in schema_type if isinstance(t, str)), None)

    if schema_type == "string":
        return _example_string_for_key(key)
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        min_items = schema.get("minItems")
        count = int(min_items) if isinstance(min_items, int) and min_items > 0 else 1
        count = max(1, min(count, 2))
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        if key == "options":
            return ["选项A", "选项B"][: max(2, count)]
        if key == "editable_fields":
            return ["name"]
        return [
            _build_example_from_schema(item_schema, key=key[:-1] if key.endswith("s") else key)
            for _ in range(count)
        ]
    if schema_type == "object":
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        keys: list[str] = [str(k) for k in required if isinstance(k, str)]
        if not keys:
            keys = [str(k) for k in list(props.keys())[:2]]
        result: dict[str, Any] = {}
        for prop_key in keys:
            child_schema = props.get(prop_key) if isinstance(props.get(prop_key), dict) else {}
            result[prop_key] = _build_example_from_schema(child_schema, key=prop_key)
        return result

    return {}


def _build_output_schema_summary(output_cfg: dict[str, Any]) -> str:
    schema = output_cfg.get("schema")
    if not isinstance(schema, dict):
        return "data 必须是对象并符合该输出定义。"
    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = [str(k) for k in (schema.get("required") or []) if isinstance(k, str)]
    required_str = ", ".join(required[:6]) if required else "无"
    keys = ", ".join(str(k) for k in list(props.keys())[:6]) if props else "无"
    return f"required={required_str}; keys={keys}"


def _build_emit_example(output_type: str, output_cfg: dict[str, Any]) -> str:
    schema = output_cfg.get("schema") if isinstance(output_cfg.get("schema"), dict) else {}
    data_example = _build_example_from_schema(schema, key="data")
    if not isinstance(data_example, dict):
        data_example = {}
    payload = {"items": [{"type": output_type, "data": data_example}]}
    return "emit(" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ")"


def _build_output_declarations(metadata: dict[str, Any], plugin_name: str) -> dict[str, BlockDeclaration]:
    outputs = metadata.get("outputs")
    if not isinstance(outputs, dict):
        return {}
    declarations: dict[str, BlockDeclaration] = {}
    for output_type, output_cfg in outputs.items():
        if not isinstance(output_cfg, dict):
            continue
        raw_schema = output_cfg.get("schema")
        schema = raw_schema if isinstance(raw_schema, dict) else None
        schema_ref = raw_schema if isinstance(raw_schema, str) else None
        declarations[str(output_type)] = BlockDeclaration(
            block_type=str(output_type),
            plugin_name=plugin_name,
            instruction=output_cfg.get("instruction"),
            schema=schema,
            schema_ref=schema_ref,
            handler=output_cfg.get("handler") if isinstance(output_cfg.get("handler"), dict) else None,
            ui=output_cfg.get("ui") if isinstance(output_cfg.get("ui"), dict) else None,
            requires_response=bool(output_cfg.get("requires_response", False)),
            trigger=output_cfg.get("trigger") if isinstance(output_cfg.get("trigger"), dict) else None,
        )
    return declarations


def _resolve_effective_trigger_policy(
    plugin_name: str,
    policy_raw: Any,
    runtime_values: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve plugin trigger policy with optional runtime overrides."""
    policy = normalize_plugin_trigger_policy(policy_raw)
    if not isinstance(runtime_values, dict):
        return policy

    mode = str(policy.get("mode") or "always").strip().lower() or "always"
    interval_turns = int(policy.get("interval_turns") or 1)
    mode_map = policy.get("mode_map") if isinstance(policy.get("mode_map"), dict) else {}

    mode_setting_key = str(policy.get("mode_setting_key") or "").strip() or None
    if mode_setting_key:
        raw_mode = str(runtime_values.get(mode_setting_key) or "").strip().lower()
        if raw_mode:
            mapped_mode = str(mode_map.get(raw_mode, raw_mode)).strip().lower()
            if mapped_mode in {"always", "interval", "manual"}:
                mode = mapped_mode

    interval_setting_key = str(policy.get("interval_setting_key") or "").strip() or None
    if interval_setting_key and interval_setting_key in runtime_values:
        try:
            parsed = int(runtime_values.get(interval_setting_key))
            if parsed > 0:
                interval_turns = parsed
        except Exception:
            logger.debug(
                "Plugin '{}' ignored invalid runtime interval value for key '{}'",
                plugin_name,
                interval_setting_key,
            )

    policy["mode"] = mode
    policy["interval_turns"] = max(1, int(interval_turns))
    return policy


def _should_run_for_trigger_policy(
    policy: dict[str, Any],
    *,
    current_turn: int | None,
    allow_manual: bool,
) -> tuple[bool, str | None]:
    """Return whether plugin should run for this turn under trigger policy."""
    mode = str(policy.get("mode") or "always").strip().lower()
    if mode == PLUGIN_TRIGGER_MANUAL and not allow_manual:
        return False, "manual trigger required"

    if mode == PLUGIN_TRIGGER_INTERVAL:
        interval_turns = max(1, int(policy.get("interval_turns") or 1))
        if current_turn is None or current_turn <= 0:
            return True, None
        # Run on turn 1, 1+N, 1+2N, ...
        if (current_turn - 1) % interval_turns != 0:
            return False, f"interval gate (turn={current_turn}, every={interval_turns})"

    return True, None


async def run_plugin_agent(
    narrative: str,
    game_state: dict,
    enabled_plugins: list[str],
    session_id: str,
    game_db: GameDB,
    pe: PluginEngine,
    config: ResolvedLlmConfig,
    plugins_dir: str | None = None,
    hook: str = DEFAULT_PLUGIN_HOOK,
    current_turn: int | None = None,
    session_phase: str | None = None,
    runtime_settings_by_plugin: dict[str, dict[str, Any]] | None = None,
    allow_manual: bool = False,
    block_trigger_counts: dict[str, int] | None = None,
    has_player_character: bool = False,
    turn_id: str | None = None,
    on_progress: ProgressCallback | None = None,
    trigger_counts: dict[str, int] | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Run enabled plugins in parallel after narrative completes."""
    plugins_dir = plugins_dir or settings.PLUGINS_DIR
    all_discovered = pe.discover(plugins_dir)
    plugins_to_run: list[dict] = []
    selected_hook = normalize_plugin_hooks([hook], default_hooks=[DEFAULT_PLUGIN_HOOK])[0]
    for p in all_discovered:
        name = p["name"]
        if name not in enabled_plugins:
            continue
        loaded = pe.load(name, plugins_dir)
        if not loaded:
            continue
        content = loaded.get("content", "").strip()
        if not content:
            continue
        declared_hooks = normalize_plugin_hooks(loaded.get("metadata", {}).get("hooks"))
        if selected_hook not in declared_hooks:
            logger.debug(
                "Plugin '{}' skipped: hook '{}' not in {}",
                name,
                selected_hook,
                declared_hooks,
            )
            continue
        runtime_values = (
            runtime_settings_by_plugin.get(name, {})
            if isinstance(runtime_settings_by_plugin, dict)
            else {}
        )
        trigger_policy = _resolve_effective_trigger_policy(
            name,
            loaded.get("metadata", {}).get("trigger"),
            runtime_values if isinstance(runtime_values, dict) else {},
        )
        should_run, skip_reason = _should_run_for_trigger_policy(
            trigger_policy,
            current_turn=current_turn,
            allow_manual=allow_manual,
        )
        if not should_run:
            logger.debug("Plugin '{}' skipped: {}", name, skip_reason or "trigger policy")
            continue
        max_triggers = loaded.get("metadata", {}).get("max_triggers")
        current_count = (trigger_counts or {}).get(name, 0)
        if max_triggers is not None and current_count >= max_triggers:
            logger.debug("Plugin '{}' skipped: trigger limit ({}/{})", name, current_count, max_triggers)
            continue
        plugins_to_run.append(
            {
                "name": name,
                "content": content,
                "metadata": loaded.get("metadata", {}),
                "path": loaded.get("path"),
                "hooks": declared_hooks,
                "trigger_policy": trigger_policy,
                "block_trigger_counts": dict(block_trigger_counts or {}),
                "has_player_character": bool(has_player_character),
                "session_phase": str(session_phase or "").strip() or None,
                "turn_id": str(turn_id or "").strip() or None,
                "runtime_settings": runtime_values,
            }
        )

    if not plugins_to_run:
        logger.debug("No plugins to run for session {}", session_id)
        return [], {
            "rounds": 0,
            "tool_calls": [],
            "blocks_emitted": [],
            "plugins_run": [],
            "plugins_executed": [],
            "plugins_emitted": [],
            "plugin_metrics": [],
            "hook": selected_hook,
        }

    logger.info(
        "Running {} plugins in parallel for hook '{}': {}",
        len(plugins_to_run),
        selected_hook,
        [p["name"] for p in plugins_to_run],
    )

    state_json = json.dumps(game_state, ensure_ascii=False, default=str)
    context_text = f"## 叙事文本\n{narrative}\n\n## 当前游戏状态\n{state_json}"

    tasks = [
        _run_one_plugin(
            plugin_info=pi, context_text=context_text, session_id=session_id,
            game_db=game_db, pe=pe, config=config, plugins_dir=plugins_dir,
            on_progress=on_progress,
        )
        for pi in plugins_to_run
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_blocks: list[dict] = []
    all_tool_calls: list[str] = []
    total_rounds = 0
    plugins_executed: list[str] = []
    plugins_emitted: list[str] = []
    plugin_metrics: list[dict[str, Any]] = []

    for plugin_info, result in zip(plugins_to_run, results):
        name = plugin_info["name"]
        if isinstance(result, Exception):
            logger.exception("Plugin '{}' failed: {}", name, result)
            continue
        plugins_executed.append(name)
        blocks, plugin_rounds, tool_calls, metrics = result
        all_blocks.extend(blocks)
        all_tool_calls.extend(tool_calls)
        total_rounds = max(total_rounds, plugin_rounds)
        if isinstance(metrics, dict):
            plugin_metrics.append(metrics)
        if blocks:
            plugins_emitted.append(name)

    _add_log(session_id, "debug", {
        "type": "plugin_agent_trace", "mode": "parallel",
        "hook": selected_hook,
        "enabled_plugins": enabled_plugins,
        "plugins_selected": [p["name"] for p in plugins_to_run],
        "plugins_executed": plugins_executed,
        "plugins_emitted": plugins_emitted,
        "plugin_metrics": plugin_metrics,
        "total_blocks": len(all_blocks),
        "blocks_emitted": [{"type": b["type"], "plugin": b.get("_plugin")} for b in all_blocks],
    })

    return all_blocks, {
        "rounds": total_rounds, "tool_calls": all_tool_calls,
        "blocks_emitted": [b.get("type") for b in all_blocks],
        "hook": selected_hook,
        # Legacy field name kept for compatibility (emitted-only semantics).
        "plugins_run": plugins_emitted,
        # New field: execution count semantics for max_triggers.
        "plugins_executed": plugins_executed,
        "plugins_emitted": plugins_emitted,
        "plugin_metrics": plugin_metrics,
    }


async def _run_one_plugin(
    plugin_info: dict,
    context_text: str,
    session_id: str,
    game_db: GameDB,
    pe: PluginEngine,
    config: ResolvedLlmConfig,
    plugins_dir: str,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[dict], int, list[str], dict[str, Any]]:
    """Run a single plugin's LLM call.

    Returns `(blocks, rounds, tool_call_names, metrics)`.
    """
    started = time.monotonic()
    name = plugin_info["name"]
    content = plugin_info["content"]
    metadata = plugin_info.get("metadata", {})
    plugin_path = plugin_info.get("path")
    plugin_root: pathlib.Path | None = None
    if isinstance(plugin_path, str) and plugin_path.strip():
        try:
            candidate = pathlib.Path(plugin_path).resolve()
            if candidate.is_dir():
                plugin_root = candidate
        except Exception:
            plugin_root = None
    block_trigger_counts = plugin_info.get("block_trigger_counts")
    has_player_character = bool(plugin_info.get("has_player_character"))
    session_phase = str(plugin_info.get("session_phase") or "").strip().lower() or None
    turn_id = str(plugin_info.get("turn_id") or "").strip() or None
    runtime_settings = plugin_info.get("runtime_settings") or {}

    tools = get_all_tools()
    base_prompt = _sanitize_plugin_prompt(_resolve_base_prompt(plugin_root, metadata, content))
    block_instructions = _build_block_instructions(
        metadata,
        plugin_name=name,
        plugin_root=plugin_root,
        block_trigger_counts=(
            block_trigger_counts if isinstance(block_trigger_counts, dict) else {}
        ),
        has_player_character=has_player_character,
        session_phase=session_phase,
        runtime_settings=runtime_settings,
    )
    tool_instructions = _build_tool_instructions(
        plugin_root=plugin_root,
        metadata=metadata,
        tools=tools,
    )
    system_parts = [SINGLE_PLUGIN_SYSTEM_PROMPT, f"## 插件指令 ({name})\n{base_prompt}"]
    if block_instructions:
        system_parts.append(f"## 结构化输出参考\n{block_instructions}")
    if tool_instructions:
        system_parts.append(f"## Tool 使用参考\n{tool_instructions}")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": context_text},
    ]
    blocks: list[dict] = []

    # Deferred-commit DB for batched writes
    plugin_db = GameDB(game_db.db, game_db.session_id, autocommit=False)
    output_declarations = _build_output_declarations(metadata, name)
    ctx = _ToolContext(
        session_id=session_id, game_db=plugin_db, pe=pe,
        enabled_plugins=[name], plugins_dir=plugins_dir, blocks=blocks,
        plugin_name=name, turn_id=turn_id,
        declared_output_types=set(output_declarations.keys()),
        declared_output_declarations=output_declarations,
    )

    total_rounds = 0
    tool_call_names: list[str] = []

    for round_idx in range(MAX_TOOL_ROUNDS):
        total_rounds = round_idx + 1
        call_kwargs = _build_call_kwargs(config, messages, tools)
        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception:
            logger.exception("Plugin '{}' LLM call failed (round {})", name, round_idx)
            break

        message = response.choices[0].message
        if not message.tool_calls:
            break

        messages.append(message.model_dump(exclude_none=True))
        for tc in message.tool_calls:
            result = await _execute_tool(tc, ctx)
            tool_call_names.append(tc.function.name)
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

        logger.debug("Plugin '{}' round {}: {} tool calls", name, round_idx, len(message.tool_calls))
        if on_progress:
            try:
                on_progress({
                    "plugin": name, "round": round_idx + 1,
                    "tool_calls": [tc.function.name for tc in message.tool_calls],
                    "blocks_so_far": [b.get("type") for b in blocks],
                })
            except Exception:
                pass

    # Single commit for all writes
    await plugin_db.flush()

    for b in blocks:
        b["_plugin"] = name
    logger.debug("Plugin '{}' finished: {} blocks, {} rounds", name, len(blocks), total_rounds)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    metrics = {
        "plugin": name,
        "elapsed_ms": elapsed_ms,
        "rounds": total_rounds,
        "tool_calls": len(tool_call_names),
        "block_count": len(blocks),
        "block_types": [b.get("type") for b in blocks],
    }
    return blocks, total_rounds, tool_call_names, metrics


async def invoke_single_plugin(
    plugin_name: str,
    context: dict,
    session_id: str,
    game_db: GameDB,
    pe: PluginEngine,
    config: ResolvedLlmConfig,
    plugins_dir: str | None = None,
) -> list[dict]:
    """Invoke a single plugin directly (e.g. guide from quick-action bar)."""
    plugins_dir = plugins_dir or settings.PLUGINS_DIR
    plugin = pe.load(plugin_name, plugins_dir)
    if not plugin:
        return [{"type": "notification", "data": {"message": f"插件 {plugin_name} 未找到", "level": "error"}}]

    plugin_path = plugin.get("path")
    plugin_root: pathlib.Path | None = None
    if isinstance(plugin_path, str) and plugin_path.strip():
        try:
            candidate = pathlib.Path(plugin_path).resolve()
            if candidate.is_dir():
                plugin_root = candidate
        except Exception:
            plugin_root = None
    metadata = plugin.get("metadata", {}) if isinstance(plugin.get("metadata"), dict) else {}
    plugin_prompt = _sanitize_plugin_prompt(
        _resolve_base_prompt(plugin_root, metadata, str(plugin.get("content", "")))
    )
    ctx_json = json.dumps(context, ensure_ascii=False, default=str)

    tools = get_all_tools()
    block_instructions = _build_block_instructions(
        metadata,
        plugin_name=plugin_name,
        plugin_root=plugin_root,
    )
    tool_instructions = _build_tool_instructions(
        plugin_root=plugin_root,
        metadata=metadata,
        tools=tools,
    )
    system_parts = [SINGLE_PLUGIN_SYSTEM_PROMPT, f"## 插件指令 ({plugin_name})\n{plugin_prompt}"]
    if block_instructions:
        system_parts.append(f"## 结构化输出参考\n{block_instructions}")
    if tool_instructions:
        system_parts.append(f"## Tool 使用参考\n{tool_instructions}")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": ctx_json},
    ]
    blocks: list[dict] = []

    plugin_db = GameDB(game_db.db, game_db.session_id, autocommit=False)
    output_declarations = _build_output_declarations(metadata, plugin_name)
    tool_ctx = _ToolContext(
        session_id=session_id, game_db=plugin_db, pe=pe,
        enabled_plugins=[plugin_name], plugins_dir=plugins_dir, blocks=blocks,
        plugin_name=plugin_name, turn_id=None,
        declared_output_types=set(output_declarations.keys()),
        declared_output_declarations=output_declarations,
    )

    for _ in range(MAX_TOOL_ROUNDS):
        call_kwargs = _build_call_kwargs(config, messages, tools)
        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception:
            logger.exception("Single plugin invoke failed for {}", plugin_name)
            break
        message = response.choices[0].message
        if not message.tool_calls:
            break
        messages.append(message.model_dump(exclude_none=True))
        for tc in message.tool_calls:
            result = await _execute_tool(tc, tool_ctx)
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    await plugin_db.flush()
    return blocks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_output_gate(
    metadata: dict[str, Any],
    runtime_settings: dict[str, Any],
) -> set[str] | None:
    """Resolve which output types are allowed based on runtime_settings output_gate.

    Returns None if no gating applies (all outputs allowed).
    Returns a set of allowed output type names if gating is active.
    """
    extensions = metadata.get("extensions")
    if not isinstance(extensions, dict):
        return None
    rs = extensions.get("runtime_settings")
    if not isinstance(rs, dict):
        return None
    fields = rs.get("fields")
    if not isinstance(fields, dict):
        return None

    allowed: set[str] | None = None
    for field_name, field_def in fields.items():
        if not isinstance(field_def, dict):
            continue
        gate = field_def.get("output_gate")
        if not isinstance(gate, dict):
            continue
        current_value = str(
            runtime_settings.get(field_name, field_def.get("default", ""))
        ).strip()
        if not current_value:
            continue
        matched_output = gate.get(current_value)
        if matched_output:
            if allowed is None:
                allowed = set()
            allowed.add(str(matched_output))

    return allowed


def _build_block_instructions(
    metadata: dict,
    *,
    plugin_name: str = "",
    plugin_root: pathlib.Path | None = None,
    block_trigger_counts: dict[str, int] | None = None,
    has_player_character: bool = False,
    session_phase: str | None = None,
    runtime_settings: dict[str, Any] | None = None,
) -> str:
    """Extract output instruction snippets from manifest metadata for the LLM."""
    outputs = metadata.get("outputs")
    if not outputs or not isinstance(outputs, dict):
        return ""
    parts: list[str] = []
    mandatory_notes: list[str] = []
    block_counts = block_trigger_counts or {}
    gated_outputs = _resolve_output_gate(metadata, runtime_settings or {})
    for output_type, decl in outputs.items():
        if not isinstance(decl, dict):
            continue
        if gated_outputs is not None and output_type not in gated_outputs:
            continue
        trigger_policy = normalize_block_trigger_policy(decl.get("trigger"))
        if (
            trigger_policy.get("mode") == BLOCK_TRIGGER_ONCE_PER_SESSION
            and int(block_counts.get(output_type, 0) or 0) > 0
        ):
            continue
        if (
            plugin_name == "state"
            and output_type == "character_sheet"
            and has_player_character
        ):
            continue
        instruction = _resolve_output_instruction(
            plugin_root=plugin_root,
            metadata=metadata,
            output_type=output_type,
            output_cfg=decl,
        )
        schema_summary = _build_output_schema_summary(decl)
        emit_example = _build_emit_example(output_type, decl)
        section_lines = [f"### {output_type}"]
        if instruction:
            section_lines.append(instruction)
        section_lines.append(f"- schema: {schema_summary}")
        section_lines.append(
            f"- 调用模板: emit({{\"items\":[{{\"type\":\"{output_type}\",\"data\":{{...}}}}]}})"
        )
        section_lines.append(f"- 简例: {emit_example}")
        parts.append("\n".join(section_lines))

    if (
        plugin_name == "state"
        and str(session_phase or "").strip().lower() == "character_creation"
        and not has_player_character
        and int(block_counts.get("character_sheet", 0) or 0) == 0
    ):
        mandatory_notes.append(
            "【强约束】当前处于角色创建阶段且还没有玩家角色："
            "本轮必须调用 emit，在 items 中输出 exactly 1 个 character_sheet；"
            "character_sheet.data.name 必须是非空字符串，editable_fields 必须包含 'name'。"
        )

    if not parts and not mandatory_notes:
        return ""

    prefix = "所有结构化输出都应通过工具调用返回。"
    if mandatory_notes:
        prefix += "\n\n" + "\n".join(mandatory_notes)
    if not parts:
        return prefix
    return prefix + "\n\n" + "\n\n".join(parts)


class _ToolContext:
    __slots__ = (
        "session_id",
        "game_db",
        "pe",
        "enabled_plugins",
        "plugins_dir",
        "blocks",
        "plugin_name",
        "turn_id",
        "declared_output_types",
        "declared_output_declarations",
    )

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _build_call_kwargs(config: ResolvedLlmConfig, messages: list, tools: list) -> dict:
    kw: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
    }
    if not config.is_empty_key():
        kw["api_key"] = config.api_key
    if config.api_base:
        safe = ensure_safe_api_base(config.api_base, purpose="PluginAgent")
        if safe:
            kw["api_base"] = safe
    return kw


def _tool_error_response(
    *,
    tool: str,
    code: str,
    message: str,
    details: str | None = None,
    retryable: bool = True,
) -> dict[str, Any]:
    """Build a model-readable tool error payload with clear retry guidance."""
    text = f"TOOL_ERROR [{tool}] {code}: {message}"
    if details:
        text += f" | details: {details}"
    if retryable:
        text += " | action: fix arguments/state and retry this tool call."
    return {
        "ok": False,
        "error": {
            "tool": tool,
            "code": code,
            "message": message,
            "details": details,
            "retryable": retryable,
        },
        "text": text,
    }


async def _execute_tool(tool_call: Any, ctx: _ToolContext) -> Any:
    name = tool_call.function.name
    raw_args = tool_call.function.arguments
    try:
        parsed = json.loads(raw_args or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("tool arguments must be a JSON object")
    except Exception as exc:
        logger.warning("Invalid tool arguments for {}: {}", name, exc)
        return _tool_error_response(
            tool=name,
            code="INVALID_ARGUMENTS",
            message="arguments must be a JSON object",
            details=str(exc),
            retryable=True,
        )

    args = parsed
    logger.debug("Plugin Agent tool: {}({})", name, args)

    try:
        match name:
            case "emit":
                return await _handle_emit(args, ctx)
            case "db_read":
                return await _handle_db_read(args, ctx)
            case "execute_script":
                return await _handle_execute_script(args, ctx)
            case "db_log_append":
                await ctx.game_db.log_append(args["collection"], args["entry"])
                return {"status": "ok"}
            case "db_log_query":
                return await ctx.game_db.log_query(args["collection"], args.get("limit", 10))
            case "db_graph_add":
                await ctx.game_db.graph_add(args["from_id"], args["to_id"], args["relation"], args.get("data"))
                return {"status": "ok"}
            case _:
                return _tool_error_response(
                    tool=name,
                    code="UNKNOWN_TOOL",
                    message=f"unknown tool '{name}'",
                    retryable=False,
                )
    except Exception as e:
        logger.exception("Tool execution error: {}", name)
        return _tool_error_response(
            tool=name,
            code="EXECUTION_FAILED",
            message=str(e),
            details=type(e).__name__,
            retryable=True,
        )


OUTPUT_VERSION = "1.0"
KNOWN_OUTPUT_STATUS = {"queued", "generating", "done", "failed"}
MARKDOWN_OPTION_PATTERNS = (
    r"\*\*",
    r"`",
    r"^\s*[-*]\s+",
    r"^\s*\d+[.)]\s+",
)


def _normalize_output_type(raw: Any) -> str:
    output_type = str(raw or "").strip()
    if output_type.startswith("json:"):
        output_type = output_type[5:]
    return output_type


def _normalize_output_status(raw: Any) -> str:
    status = str(raw or "done").strip().lower()
    return status if status in KNOWN_OUTPUT_STATUS else "done"


def _normalize_output_meta(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    meta: dict[str, Any] = {}
    for key, value in raw.items():
        k = str(key or "").strip()
        if not k:
            continue
        meta[k] = value
    return meta


def _normalize_choice_options(raw_options: Any) -> list[dict[str, Any]]:
    """Allow compact choice payload input (array) while returning stable option objects."""
    if not isinstance(raw_options, list):
        return []
    options: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_options):
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("value") or f"Option {idx + 1}").strip()
            value = item.get("value", label)
            option_id = str(item.get("id") or f"opt_{idx + 1}").strip() or f"opt_{idx + 1}"
            normalized = dict(item)
            normalized.setdefault("id", option_id)
            normalized.setdefault("label", label)
            normalized.setdefault("value", value)
            options.append(normalized)
            continue
        label = str(item).strip() or f"Option {idx + 1}"
        options.append({"id": f"opt_{idx + 1}", "label": label, "value": label})
    return options


def _normalize_output_data(output_type: str, raw_data: Any) -> dict[str, Any]:
    # Keep output payload object-shaped for stable frontend parsing.
    if raw_data is None:
        data: dict[str, Any] = {}
    elif isinstance(raw_data, dict):
        data = dict(raw_data)
    elif output_type == "choice" and isinstance(raw_data, list):
        data = {"options": _normalize_choice_options(raw_data)}
    else:
        data = {"value": raw_data}

    # Additional normalization for common composite UI payloads.
    if output_type == "choice" and "options" in data and isinstance(data["options"], list):
        data["options"] = _normalize_choice_options(data["options"])

    return data


def _collect_emit_items(args: dict[str, Any]) -> list[dict[str, Any]]:
    items_raw = args.get("items")
    if isinstance(items_raw, list):
        return [item for item in items_raw if isinstance(item, dict)]
    return []


def _build_output_item(
    *,
    item: dict[str, Any],
    default_meta: dict[str, Any],
    ctx: _ToolContext,
) -> dict[str, Any]:
    output_type = _normalize_output_type(item.get("type", item.get("block_type")))
    if not output_type:
        raise ValueError("missing item.type")

    data = _normalize_output_data(output_type, item.get("data", item.get("payload")))
    merged_meta = dict(default_meta)
    merged_meta.update(_normalize_output_meta(item.get("meta")))
    merged_meta.setdefault("plugin", ctx.plugin_name)
    if ctx.turn_id:
        merged_meta.setdefault("turn_id", ctx.turn_id)
    merged_meta.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    item_id = str(item.get("id") or "").strip() or f"out_{uuid.uuid4().hex}"
    status = _normalize_output_status(item.get("status"))
    return {
        "id": item_id,
        "version": OUTPUT_VERSION,
        "type": output_type,
        "data": data,
        "meta": merged_meta,
        "status": status,
    }


def _validate_emit_item_data(
    output_type: str,
    data: dict[str, Any],
    declaration: BlockDeclaration | None = None,
) -> list[str]:
    errors = validate_block_data(output_type, data, declaration)

    if output_type == "character_sheet":
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("character_sheet.data.name must be a non-empty string")
        editable_fields = data.get("editable_fields")
        if editable_fields is not None:
            if not isinstance(editable_fields, list):
                errors.append("character_sheet.data.editable_fields must be an array")
            else:
                normalized = {
                    str(field or "").strip()
                    for field in editable_fields
                    if str(field or "").strip()
                }
                if "name" not in normalized:
                    errors.append("character_sheet.data.editable_fields must include 'name'")

    if output_type == "scene_update":
        action = str(data.get("action") or "move").strip().lower() or "move"
        if action == "move":
            name = data.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append("scene_update.data.name is required when action=move")

    if output_type in {"choice", "choices"}:
        options = data.get("options")
        if not isinstance(options, list):
            errors.append("choices.data.options must be an array")
            return errors
        if len(options) < 2:
            errors.append("choices.data.options must contain at least 2 separate options")
        for idx, option in enumerate(options):
            if not isinstance(option, str) or not option.strip():
                errors.append(f"choices.data.options[{idx}] must be a non-empty string")
                continue
            text = option.strip()
            if "\n" in text or "\r" in text:
                errors.append(
                    f"choices.data.options[{idx}] must be one-line plain text; split options into separate array items"
                )
            if " / " in text:
                errors.append(
                    f"choices.data.options[{idx}] appears to merge multiple options; one option per array item"
                )
            if any(re.search(pattern, text) for pattern in MARKDOWN_OPTION_PATTERNS):
                errors.append(
                    f"choices.data.options[{idx}] must be plain text without markdown formatting"
                )

    return errors


async def _handle_emit(args: dict, ctx: _ToolContext) -> dict:
    """Single unified output tool: optional writes/logs + multiple structured items."""
    db = ctx.game_db
    writes = args.get("writes", [])
    logs = args.get("logs", [])

    default_meta = _normalize_output_meta(args.get("meta"))
    items = _collect_emit_items(args)
    raw_declared_types = getattr(ctx, "declared_output_types", None)
    enforce_declared_types = isinstance(raw_declared_types, set)
    declared_output_types = set(raw_declared_types) if enforce_declared_types else set()
    raw_declared_declarations = getattr(ctx, "declared_output_declarations", None)
    declared_output_declarations = (
        raw_declared_declarations if isinstance(raw_declared_declarations, dict) else {}
    )

    pending_items: list[dict[str, Any]] = []
    strict_errors: list[str] = []
    ignored: list[str] = []
    if items and enforce_declared_types and not declared_output_types:
        ignored.append("plugin declares no outputs; all emitted items were ignored")
    for idx, item in enumerate(items):
        try:
            output_item = _build_output_item(
                item=item,
                default_meta=default_meta,
                ctx=ctx,
            )
        except ValueError as exc:
            logger.debug("Ignore invalid emit item: {}", exc)
            ignored.append(str(exc))
            continue

        output_type = str(output_item.get("type") or "")
        if enforce_declared_types and output_type not in declared_output_types:
            ignored.append(f"undeclared output type: {output_type}")
            continue

        data = output_item.get("data")
        if not isinstance(data, dict):
            strict_errors.append(f"items[{idx}].data must be an object")
            continue
        declaration = declared_output_declarations.get(output_type)
        item_errors = _validate_emit_item_data(
            output_type,
            data,
            declaration if isinstance(declaration, BlockDeclaration) else None,
        )
        for err in item_errors:
            strict_errors.append(f"items[{idx}] ({output_type}): {err}")
        if item_errors:
            continue

        pending_items.append(output_item)

    if strict_errors:
        text = "EMIT_ERROR: " + "; ".join(strict_errors[:3])
        return {
            "status": "error",
            "errors": strict_errors,
            "warnings": ignored,
            "text": text,
        }

    written = 0
    for w in writes:
        if not isinstance(w, dict):
            continue
        await db.kv_set(w["collection"], w["key"], w["value"])
        written += 1

    logged = 0
    for log_entry in logs:
        if isinstance(log_entry, dict):
            await db.log_append(log_entry["collection"], log_entry["entry"])
            logged += 1

    emitted_ids: list[str] = []
    emitted_types: list[str] = []
    for output_item in pending_items:
        ctx.blocks.append(output_item)
        emitted_ids.append(str(output_item.get("id")))
        emitted_types.append(str(output_item.get("type") or ""))

    result: dict[str, Any] = {"status": "ok", "written": written, "logged": logged}
    if emitted_types:
        result["count"] = len(emitted_types)
        result["emitted"] = emitted_types
        result["ids"] = emitted_ids
    if ignored:
        result["warnings"] = ignored
        result["text"] = "EMIT_WARNING: " + "; ".join(ignored[:3])
    return result


async def _handle_db_read(args: dict, ctx: _ToolContext) -> Any:
    """Unified read: single key or full collection."""
    collection = args["collection"]
    key = args.get("key")
    if key:
        val = await ctx.game_db.kv_get(collection, key)
        return val if val is not None else {"_empty": True}
    return await ctx.game_db.kv_query(collection)


async def _handle_execute_script(args: dict, ctx: _ToolContext) -> Any:
    plugin_name = args["plugin"]
    func = args["function"]
    script_args = args.get("args", {})
    plugin = ctx.pe.load(plugin_name, ctx.plugins_dir)
    if not plugin:
        return _tool_error_response(
            tool="execute_script",
            code="PLUGIN_NOT_FOUND",
            message=f"plugin '{plugin_name}' not found",
            retryable=False,
        )
    caps = plugin.get("metadata", {}).get("capabilities", {})
    cap = caps.get(func) if isinstance(caps, dict) else None
    if not cap:
        return _tool_error_response(
            tool="execute_script",
            code="CAPABILITY_NOT_FOUND",
            message=f"capability '{func}' not found in plugin '{plugin_name}'",
            retryable=False,
        )
    impl = cap.get("implementation", {})
    if impl.get("type") != "script":
        return _tool_error_response(
            tool="execute_script",
            code="UNSUPPORTED_CAPABILITY_TYPE",
            message=f"capability '{func}' is not a script type",
            retryable=False,
        )
    script_path = pathlib.Path(plugin.get("path", "")) / impl.get("script", "")
    runner = PythonScriptRunner()
    result = await runner.run(
        script_path, script_args,
        plugin_name=plugin_name, capability_id=func,
    )
    if result.exit_code != 0:
        return _tool_error_response(
            tool="execute_script",
            code="SCRIPT_EXECUTION_FAILED",
            message=result.stderr or f"script exited with code {result.exit_code}",
            details=str(script_path),
            retryable=True,
        )
    return result.parsed_output or {"stdout": result.stdout}
