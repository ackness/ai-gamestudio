"""Plugin Agent — post-narrative function-calling agent for game mechanics."""
from __future__ import annotations

import json
import pathlib
from typing import Any

import litellm
from loguru import logger

from backend.app.core.game_db import GameDB
from backend.app.core.llm_config import ResolvedLlmConfig
from backend.app.core.network_safety import ensure_safe_api_base
from backend.app.core.plugin_engine import PluginEngine
from backend.app.core.plugin_tools import get_all_tools
from backend.app.core.script_runner import PythonScriptRunner

MAX_TOOL_ROUNDS = 10

PLUGIN_AGENT_SYSTEM_PROMPT = """\
你是一个游戏插件代理（Plugin Agent）。你的任务是分析 DM 的叙事输出，判断需要触发哪些游戏机制，并通过工具调用来更新游戏状态和输出结构化数据。

## 工作流程
1. 阅读 DM 的叙事文本和当前游戏状态
2. 调用 list_plugins() 查看可用插件
3. 根据叙事内容判断需要哪些插件
4. 调用 load_plugin(name) 加载需要的插件详细指令
5. 按照插件指令，使用 db_* 工具操作游戏数据
6. 使用 emit_block() 输出结构化数据到前端

## 原则
- 只处理叙事中实际发生的变化，不要臆造
- 一次可以处理多个插件的需求
- 优先使用 db_* 工具持久化状态，再用 emit_block 通知前端
- 如果叙事中没有需要处理的游戏机制变化，直接结束即可
"""


async def run_plugin_agent(
    narrative: str,
    game_state: dict,
    enabled_plugins: list[str],
    session_id: str,
    game_db: GameDB,
    pe: PluginEngine,
    config: ResolvedLlmConfig,
    plugins_dir: str = "plugins",
) -> list[dict]:
    """Run the Plugin Agent after narrative completes. Returns emitted blocks."""

    state_json = json.dumps(game_state, ensure_ascii=False, default=str)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": PLUGIN_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"## 叙事文本\n{narrative}\n\n## 当前游戏状态\n{state_json}"},
    ]
    tools = get_all_tools()
    blocks: list[dict] = []

    # Build tool executor context
    ctx = _ToolContext(
        session_id=session_id,
        game_db=game_db,
        pe=pe,
        enabled_plugins=enabled_plugins,
        plugins_dir=plugins_dir,
        blocks=blocks,
    )

    for round_idx in range(MAX_TOOL_ROUNDS):
        call_kwargs = _build_call_kwargs(config, messages, tools)
        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception:
            logger.exception("Plugin Agent LLM call failed (round {})", round_idx)
            break

        message = response.choices[0].message
        if not message.tool_calls:
            break

        messages.append(message.model_dump(exclude_none=True))

        for tc in message.tool_calls:
            result = await _execute_tool(tc, ctx)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return blocks


async def invoke_single_plugin(
    plugin_name: str,
    context: dict,
    session_id: str,
    game_db: GameDB,
    pe: PluginEngine,
    config: ResolvedLlmConfig,
    plugins_dir: str = "plugins",
) -> list[dict]:
    """Invoke a single plugin directly (e.g. guide from quick-action bar)."""

    plugin = pe.load(plugin_name, plugins_dir)
    if not plugin:
        return [{"type": "notification", "data": {"message": f"插件 {plugin_name} 未找到", "level": "error"}}]

    plugin_prompt = plugin.get("content", "")
    ctx_json = json.dumps(context, ensure_ascii=False, default=str)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": f"你是游戏插件代理。请按照以下插件指令处理当前上下文，使用工具输出结果。\n\n{plugin_prompt}"},
        {"role": "user", "content": ctx_json},
    ]
    tools = get_all_tools()
    blocks: list[dict] = []

    tool_ctx = _ToolContext(
        session_id=session_id,
        game_db=game_db,
        pe=pe,
        enabled_plugins=[plugin_name],
        plugins_dir=plugins_dir,
        blocks=blocks,
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
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return blocks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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
    args = json.loads(tool_call.function.arguments)
    logger.debug("Plugin Agent tool: {}({})", name, args)

    try:
        if name == "list_plugins":
            return _handle_list_plugins(ctx)
        elif name == "load_plugin":
            return _handle_load_plugin(args, ctx)
        elif name == "execute_script":
            return await _handle_execute_script(args, ctx)
        elif name == "emit_block":
            return _handle_emit_block(args, ctx)
        elif name.startswith("db_"):
            return await _handle_db_tool(name, args, ctx)
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.exception("Tool execution error: {}", name)
        return {"error": str(e)}


def _handle_list_plugins(ctx: _ToolContext) -> list[dict]:
    plugins = ctx.pe.discover(ctx.plugins_dir)
    return [
        {"name": p["name"], "description": p.get("metadata", {}).get("description", "")}
        for p in plugins
        if p["name"] in ctx.enabled_plugins
    ]


def _handle_load_plugin(args: dict, ctx: _ToolContext) -> dict:
    name = args["name"]
    plugin = ctx.pe.load(name, ctx.plugins_dir)
    if not plugin:
        return {"error": f"Plugin '{name}' not found"}
    meta = plugin.get("metadata", {})
    return {
        "name": name,
        "prompt": plugin.get("content", ""),
        "blocks": meta.get("blocks", []),
        "capabilities": meta.get("capabilities", []),
    }


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


def _handle_emit_block(args: dict, ctx: _ToolContext) -> dict:
    block = {"type": args["type"], "data": args.get("data", {})}
    ctx.blocks.append(block)
    return {"status": "emitted", "type": args["type"]}


async def _handle_db_tool(name: str, args: dict, ctx: _ToolContext) -> Any:
    db = ctx.game_db
    if name == "db_kv_get":
        val = await db.kv_get(args["collection"], args["key"])
        return val if val is not None else {"_empty": True}
    elif name == "db_kv_set":
        await db.kv_set(args["collection"], args["key"], args["value"])
        return {"status": "ok"}
    elif name == "db_kv_query":
        return await db.kv_query(args["collection"], args.get("filter_key"))
    elif name == "db_graph_add":
        await db.graph_add(args["from_id"], args["to_id"], args["relation"], args.get("data"))
        return {"status": "ok"}
    elif name == "db_graph_query":
        return await db.graph_query(args.get("node_id"), args.get("relation"), args.get("direction", "both"))
    elif name == "db_log_append":
        await db.log_append(args["collection"], args["entry"])
        return {"status": "ok"}
    elif name == "db_log_query":
        return await db.log_query(args["collection"], args.get("limit", 10))
    return {"error": f"Unknown db tool: {name}"}
