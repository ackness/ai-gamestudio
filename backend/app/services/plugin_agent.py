"""Plugin Agent — post-narrative function-calling agent for game mechanics."""
from __future__ import annotations

import asyncio
import json
import pathlib
import time
from typing import Any

import litellm
from loguru import logger

from backend.app.core.config import settings
from backend.app.core.game_db import GameDB
from backend.app.core.llm_config import ResolvedLlmConfig
from backend.app.core.plugin_engine import PluginEngine
from backend.app.adapters.sql_storage import SqlStorageAdapter
from backend.app.core.plugin_hooks import DEFAULT_PLUGIN_HOOK, normalize_plugin_hooks
from backend.app.core.plugin_trigger import (
    PLUGIN_TRIGGER_INTERVAL,
    PLUGIN_TRIGGER_MANUAL,
    normalize_plugin_trigger_policy,
)
from backend.app.core.plugin_tools import get_all_tools
from backend.app.services.debug_log_service import add_debug_log as _add_log
from backend.app.services.plugin_agent_prompt import (
    SINGLE_PLUGIN_SYSTEM_PROMPT,
    _build_block_instructions,
    _build_output_declarations,
    _build_tool_instructions,
    _resolve_base_prompt,
    _sanitize_plugin_prompt,
)
from backend.app.services.plugin_agent_tools import (
    _ToolContext,
    _build_call_kwargs,
    _execute_tool,
    _handle_emit,
)

MAX_TOOL_ROUNDS = 8

ProgressCallback = Any  # Callable[[dict], None] — optional sync callback

# Re-export for external callers (tests import _build_block_instructions from here)
__all__ = [
    "run_plugin_agent",
    "invoke_single_plugin",
    "_build_block_instructions",
    "_handle_emit",
]


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
    session_language: str | None = None,
    reasoning_effort: str | None = "none",
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
                "session_language": str(session_language or "").strip().lower() or None,
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
            on_progress=on_progress, reasoning_effort=reasoning_effort,
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
    reasoning_effort: str | None = "none",
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
    session_language = str(plugin_info.get("session_language") or "").strip().lower()

    tools = get_all_tools()
    base_prompt = _sanitize_plugin_prompt(
        _resolve_base_prompt(
            plugin_root,
            metadata,
            content,
            session_language=session_language,
        )
    )
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
        session_language=session_language,
    )
    tool_instructions = _build_tool_instructions(
        plugin_root=plugin_root,
        metadata=metadata,
        tools=tools,
        session_language=session_language,
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
    storage = SqlStorageAdapter(game_db.db, session_id=game_db.session_id, autocommit=False)
    output_declarations = _build_output_declarations(metadata, name)
    ctx = _ToolContext(
        session_id=session_id, game_db=plugin_db, storage=storage, pe=pe,
        enabled_plugins=[name], plugins_dir=plugins_dir, blocks=blocks,
        plugin_name=name, turn_id=turn_id,
        declared_output_types=set(output_declarations.keys()),
        declared_output_declarations=output_declarations,
    )

    total_rounds = 0
    tool_call_names: list[str] = []

    for round_idx in range(MAX_TOOL_ROUNDS):
        total_rounds = round_idx + 1
        call_kwargs = _build_call_kwargs(config, messages, tools, reasoning_effort=reasoning_effort)
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

    # Single commit for all writes (storage and plugin_db share the same session)
    await storage.flush()
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
        "messages": messages,
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
    runtime_settings: dict[str, Any] | None = None,
    session_language: str | None = None,
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
    normalized_language = str(session_language or "").strip().lower() or None
    plugin_prompt = _sanitize_plugin_prompt(
        _resolve_base_prompt(
            plugin_root,
            metadata,
            str(plugin.get("content", "")),
            session_language=normalized_language,
        )
    )
    ctx_json = json.dumps(context, ensure_ascii=False, default=str)

    tools = get_all_tools()
    block_instructions = _build_block_instructions(
        metadata,
        plugin_name=plugin_name,
        plugin_root=plugin_root,
        runtime_settings=runtime_settings if isinstance(runtime_settings, dict) else {},
        session_language=normalized_language,
    )
    tool_instructions = _build_tool_instructions(
        plugin_root=plugin_root,
        metadata=metadata,
        tools=tools,
        session_language=normalized_language,
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
