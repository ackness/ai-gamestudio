"""Plugin Agent — post-narrative function-calling agent for game mechanics."""
from __future__ import annotations

import asyncio
import json
import pathlib
from typing import Any

import litellm
from loguru import logger

from backend.app.core.config import settings
from backend.app.core.game_db import GameDB
from backend.app.core.llm_config import ResolvedLlmConfig
from backend.app.core.network_safety import ensure_safe_api_base
from backend.app.core.plugin_engine import PluginEngine
from backend.app.core.plugin_tools import get_all_tools
from backend.app.core.script_runner import PythonScriptRunner
from backend.app.api.debug_log import _add_log

MAX_TOOL_ROUNDS = 8

ProgressCallback = Any  # Callable[[dict], None] — optional sync callback

SINGLE_PLUGIN_SYSTEM_PROMPT = """\
你是游戏插件代理。分析 DM 叙事，按插件指令执行游戏机制。

## 规则
- 当前游戏状态已在上下文中，无需 db_read 查询已有数据
- 有状态变化时用 update_and_emit 一次完成 DB 写入 + 前端通知
- 纯展示插件（如 guide）直接用 emit_block
- 叙事中没有相关变化则直接结束，不要臆造
"""


async def run_plugin_agent(
    narrative: str,
    game_state: dict,
    enabled_plugins: list[str],
    session_id: str,
    game_db: GameDB,
    pe: PluginEngine,
    config: ResolvedLlmConfig,
    plugins_dir: str | None = None,
    on_progress: ProgressCallback | None = None,
    trigger_counts: dict[str, int] | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Run enabled plugins in parallel after narrative completes."""
    plugins_dir = plugins_dir or settings.PLUGINS_DIR
    all_discovered = pe.discover(plugins_dir)
    plugins_to_run: list[dict] = []
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
        max_triggers = loaded.get("metadata", {}).get("max_triggers")
        current_count = (trigger_counts or {}).get(name, 0)
        if max_triggers is not None and current_count >= max_triggers:
            logger.debug("Plugin '{}' skipped: trigger limit ({}/{})", name, current_count, max_triggers)
            continue
        plugins_to_run.append({"name": name, "content": content, "metadata": loaded.get("metadata", {})})

    if not plugins_to_run:
        logger.debug("No plugins to run for session {}", session_id)
        return [], {
            "rounds": 0,
            "tool_calls": [],
            "blocks_emitted": [],
            "plugins_run": [],
            "plugins_executed": [],
            "plugins_emitted": [],
        }

    logger.info("Running {} plugins in parallel: {}", len(plugins_to_run), [p["name"] for p in plugins_to_run])

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

    for plugin_info, result in zip(plugins_to_run, results):
        name = plugin_info["name"]
        if isinstance(result, Exception):
            logger.exception("Plugin '{}' failed: {}", name, result)
            continue
        plugins_executed.append(name)
        blocks, plugin_rounds, tool_calls = result
        all_blocks.extend(blocks)
        all_tool_calls.extend(tool_calls)
        total_rounds = max(total_rounds, plugin_rounds)
        if blocks:
            plugins_emitted.append(name)

    _add_log(session_id, "debug", {
        "type": "plugin_agent_trace", "mode": "parallel",
        "enabled_plugins": enabled_plugins,
        "plugins_selected": [p["name"] for p in plugins_to_run],
        "plugins_executed": plugins_executed,
        "plugins_emitted": plugins_emitted,
        "total_blocks": len(all_blocks),
        "blocks_emitted": [{"type": b["type"], "plugin": b.get("_plugin")} for b in all_blocks],
    })

    return all_blocks, {
        "rounds": total_rounds, "tool_calls": all_tool_calls,
        "blocks_emitted": [b.get("type") for b in all_blocks],
        # Legacy field name kept for compatibility (emitted-only semantics).
        "plugins_run": plugins_emitted,
        # New field: execution count semantics for max_triggers.
        "plugins_executed": plugins_executed,
        "plugins_emitted": plugins_emitted,
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
) -> tuple[list[dict], int, list[str]]:
    """Run a single plugin's LLM call. Returns (blocks, rounds, tool_call_names)."""
    name = plugin_info["name"]
    content = plugin_info["content"]
    metadata = plugin_info.get("metadata", {})

    block_instructions = _build_block_instructions(metadata)
    system_parts = [SINGLE_PLUGIN_SYSTEM_PROMPT, f"## 插件指令 ({name})\n{content}"]
    if block_instructions:
        system_parts.append(f"## Block 格式参考\n{block_instructions}")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": context_text},
    ]
    tools = get_all_tools()
    blocks: list[dict] = []

    # Deferred-commit DB for batched writes
    plugin_db = GameDB(game_db.db, game_db.session_id, autocommit=False)
    ctx = _ToolContext(
        session_id=session_id, game_db=plugin_db, pe=pe,
        enabled_plugins=[name], plugins_dir=plugins_dir, blocks=blocks,
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
    return blocks, total_rounds, tool_call_names


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

    plugin_prompt = plugin.get("content", "")
    ctx_json = json.dumps(context, ensure_ascii=False, default=str)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": f"{SINGLE_PLUGIN_SYSTEM_PROMPT}\n\n## 插件指令 ({plugin_name})\n{plugin_prompt}"},
        {"role": "user", "content": ctx_json},
    ]
    tools = get_all_tools()
    blocks: list[dict] = []

    plugin_db = GameDB(game_db.db, game_db.session_id, autocommit=False)
    tool_ctx = _ToolContext(
        session_id=session_id, game_db=plugin_db, pe=pe,
        enabled_plugins=[plugin_name], plugins_dir=plugins_dir, blocks=blocks,
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

def _build_block_instructions(metadata: dict) -> str:
    """Extract block format instructions from manifest metadata for the LLM."""
    blocks = metadata.get("blocks", {})
    if not blocks or not isinstance(blocks, dict):
        return ""
    parts: list[str] = []
    for block_type, decl in blocks.items():
        if not isinstance(decl, dict):
            continue
        instruction = decl.get("instruction", "")
        if instruction:
            parts.append(f"### {block_type}\n{instruction}")
    return "\n\n".join(parts)


class _ToolContext:
    __slots__ = ("session_id", "game_db", "pe", "enabled_plugins", "plugins_dir", "blocks")

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


async def _execute_tool(tool_call: Any, ctx: _ToolContext) -> Any:
    name = tool_call.function.name
    raw_args = tool_call.function.arguments
    try:
        parsed = json.loads(raw_args or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("tool arguments must be a JSON object")
    except Exception as exc:
        logger.warning("Invalid tool arguments for {}: {}", name, exc)
        return {"error": f"Invalid arguments for '{name}': {exc}"}

    args = parsed
    logger.debug("Plugin Agent tool: {}({})", name, args)

    try:
        match name:
            case "update_and_emit":
                return await _handle_update_and_emit(args, ctx)
            case "emit_block":
                return _handle_emit_block(args, ctx)
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
                return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.exception("Tool execution error: {}", name)
        return {"error": str(e)}


async def _handle_update_and_emit(args: dict, ctx: _ToolContext) -> dict:
    """Batch KV writes + optional multiple emits + optional multiple logs in one call."""
    db = ctx.game_db
    writes = args.get("writes", [])
    written = 0
    for w in writes:
        await db.kv_set(w["collection"], w["key"], w["value"])
        written += 1

    logs = args.get("logs", [])
    for log_entry in logs:
        if isinstance(log_entry, dict):
            await db.log_append(log_entry["collection"], log_entry["entry"])

    emits = args.get("emits", [])

    emitted_types: list[str] = []
    for emit in emits:
        if not isinstance(emit, dict):
            continue
        block_type = emit.get("type", "")
        if block_type.startswith("json:"):
            block_type = block_type[5:]
        ctx.blocks.append({"type": block_type, "data": emit.get("data", {})})
        emitted_types.append(block_type)

    result: dict[str, Any] = {"status": "ok", "written": written}
    if emitted_types:
        result["emitted"] = emitted_types
    return result


def _handle_emit_block(args: dict, ctx: _ToolContext) -> dict:
    block_type = args["type"]
    if block_type.startswith("json:"):
        block_type = block_type[5:]
    ctx.blocks.append({"type": block_type, "data": args.get("data", {})})
    return {"status": "emitted", "type": block_type}


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
        return {"error": f"Plugin '{plugin_name}' not found"}
    caps = plugin.get("metadata", {}).get("capabilities", {})
    cap = caps.get(func) if isinstance(caps, dict) else None
    if not cap:
        return {"error": f"Capability '{func}' not found in {plugin_name}"}
    impl = cap.get("implementation", {})
    if impl.get("type") != "script":
        return {"error": f"Capability '{func}' is not a script type"}
    script_path = pathlib.Path(plugin.get("path", "")) / impl.get("script", "")
    runner = PythonScriptRunner()
    result = await runner.run(
        script_path, script_args,
        plugin_name=plugin_name, capability_id=func,
    )
    if result.exit_code != 0:
        return {"error": result.stderr or f"Script exited with code {result.exit_code}"}
    return result.parsed_output or {"stdout": result.stdout}
