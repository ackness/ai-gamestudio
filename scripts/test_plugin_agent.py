#!/usr/bin/env python3
"""Plugin Agent integration test — real tool-call chains with DB persistence.

Loads PLUGIN_LLM_* (or LLM_*) from .env, runs a narrative through selected
plugin(s) with a real GameDB backed by a test SQLite.

Usage:
    uv run python scripts/test_plugin_agent.py -p guide              # test guide plugin
    uv run python scripts/test_plugin_agent.py -p state --narrative "你走进酒馆..."
    uv run python scripts/test_plugin_agent.py --list                # list plugins
    uv run python scripts/test_plugin_agent.py -p guide -v           # verbose tool logs
    uv run python scripts/test_plugin_agent.py --dry-run             # show config only
    uv run python scripts/test_plugin_agent.py --db-path data/test.db  # custom DB path
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import os
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")

import litellm
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.config import Settings
from backend.app.core.game_db import GameDB
from backend.app.core.plugin_engine import PluginEngine
from backend.app.core.plugin_tools import get_all_tools
from backend.app.models.game_kv import GameKV  # noqa: F401 — table registration
from backend.app.models.game_graph import GameGraph  # noqa: F401
from backend.app.models.game_log import GameLog  # noqa: F401


# ---------------------------------------------------------------------------
# Preset narratives (selectable via --preset)
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict[str, Any]] = {
    "tavern": {
        "label": "酒馆场景（含NPC、物品、场景移动）",
        "narrative": (
            "你走进了一间昏暗的酒馆，空气中弥漫着酒香和烟草的味道。\n"
            "酒馆掌柜王大锤正在柜台后擦拭酒杯，看到你进来，他抬起头微微点了点头。\n"
            "'客官，来点什么？'他粗犷的声音在嘈杂的酒馆中格外清晰。\n"
            "你注意到角落里坐着一个神秘的黑衣人，似乎在等待什么人。\n"
            "你的背包里还有从山贼那里缴获的一把铁剑和50两银子。"
        ),
        "game_state": {
            "characters": [{
                "name": "李逍遥", "role": "player",
                "attributes": {"气血": 100, "内力": 50, "体力": 80},
                "inventory": ["长剑", "干粮", "银两×20"],
            }],
            "world": {"current_location": "青云镇", "time_of_day": "黄昏"},
            "current_scene": {"name": "青云镇", "description": "一座繁华的小镇"},
        },
    },
    "combat": {
        "label": "战斗场景（含伤害、技能、状态变化）",
        "narrative": (
            "山贼头目挥舞着大刀向你砍来！你侧身闪避，但还是被刀锋擦过左臂，"
            "鲜血顿时染红了衣袖。你咬牙运起内力，使出'青云剑法'第三式——"
            "剑光如虹，直刺山贼头目的咽喉。山贼头目惊恐地后退，但已经来不及了，"
            "剑尖划过他的胸口，留下一道深深的伤痕。山贼头目倒地不起，"
            "你从他身上搜出了一枚玉佩和30两银子。你的气血下降了15点。"
        ),
        "game_state": {
            "characters": [{
                "name": "李逍遥", "role": "player",
                "attributes": {"气血": 85, "内力": 40, "体力": 60},
                "inventory": ["长剑", "干粮", "银两×20"],
            }],
            "world": {"current_location": "青云山道", "time_of_day": "午后"},
            "current_scene": {"name": "青云山道", "description": "蜿蜒的山间小路"},
        },
    },
    "explore": {
        "label": "探索场景（含场景移动、发现物品）",
        "narrative": (
            "你沿着蜿蜒的山路向上攀登，终于来到了传说中的青云洞。\n"
            "洞口被藤蔓遮掩，隐约可以看到里面闪烁着微弱的光芒。\n"
            "你拨开藤蔓走了进去，发现洞内别有洞天——\n"
            "一个巨大的石室中央放着一把古朴的长剑，剑身上刻着奇异的符文。\n"
            "石室的墙壁上还有一幅壁画，描绘着一位白衣剑客飞天遁地的场景。"
        ),
        "game_state": {
            "characters": [{
                "name": "李逍遥", "role": "player",
                "attributes": {"气血": 100, "内力": 50, "体力": 70},
                "inventory": ["长剑", "干粮", "银两×50", "玉佩"],
            }],
            "world": {"current_location": "青云山", "time_of_day": "上午"},
            "current_scene": {"name": "青云山", "description": "云雾缭绕的仙山"},
        },
    },
}

DEFAULT_PRESET = "tavern"

# Map each plugin to its best-fit preset
PLUGIN_PRESET_MAP: dict[str, str] = {
    "state": "tavern",
    "guide": "tavern",
    "event": "tavern",
    "memory": "tavern",
    "database": "tavern",
    "social": "tavern",
    "codex": "explore",
    "image": "explore",
    "combat": "combat",
    "inventory": "combat",
}

# Plugins to skip by default in --all mode (need special APIs)
DEFAULT_SKIP = {"image"}

SYSTEM_PROMPT = """\
你是游戏插件代理。分析 DM 叙事，按插件指令执行游戏机制。

## 规则
- 当前游戏状态已在上下文中，无需 db_read 查询已有数据
- 有状态变化时用 update_and_emit 一次完成 DB 写入 + 前端通知
- 纯展示插件（如 guide）直接用 emit_block
- 叙事中没有相关变化则直接结束，不要臆造
"""

MAX_TOOL_ROUNDS = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_plugin_config(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    """Resolve plugin LLM config from CLI args > PLUGIN_LLM_* > LLM_*."""
    model = args.model or settings.PLUGIN_LLM_MODEL or settings.LLM_MODEL
    api_key = args.api_key or settings.PLUGIN_LLM_API_KEY or settings.LLM_API_KEY
    api_base = args.api_base or settings.PLUGIN_LLM_API_BASE or settings.LLM_API_BASE
    return {"model": model, "api_key": api_key, "api_base": api_base}


def discover_plugins(plugins_dir: str) -> list[dict]:
    """Discover all plugins with content."""
    pe = PluginEngine()
    all_plugins = pe.discover(plugins_dir)
    result = []
    for p in all_plugins:
        loaded = pe.load(p["name"], plugins_dir)
        if loaded and loaded.get("content", "").strip():
            meta = loaded.get("metadata", {})
            result.append({
                "name": p["name"],
                "type": meta.get("type", "?"),
                "description": meta.get("description", "")[:60],
                "content": loaded["content"],
                "metadata": meta,
            })
    return result


def build_block_instructions(metadata: dict) -> str:
    """Extract block format instructions from manifest metadata."""
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


# ---------------------------------------------------------------------------
# Test DB setup
# ---------------------------------------------------------------------------

async def setup_test_db(db_path: str) -> Any:
    """Create test SQLite engine and tables."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


# ---------------------------------------------------------------------------
# Block validation
# ---------------------------------------------------------------------------

def validate_block(block_type: str, data: Any) -> list[str]:
    """Basic validation of emitted blocks."""
    errors: list[str] = []
    if not isinstance(data, dict):
        errors.append(f"{block_type}: data is not a dict")
        return errors
    if block_type == "character_sheet" and not data.get("name"):
        errors.append("character_sheet: missing required 'name'")
    elif block_type == "scene_update" and data.get("action") == "move" and not data.get("name"):
        errors.append("scene_update: missing 'name' when action=move")
    elif block_type == "state_update" and not data.get("characters") and not data.get("world"):
        errors.append("state_update: must contain 'characters' or 'world'")
    elif block_type == "notification" and not data.get("content"):
        errors.append("notification: missing 'content'")
    return errors


# ---------------------------------------------------------------------------
# Tool execution with real GameDB
# ---------------------------------------------------------------------------

async def execute_tool(
    tool_call: Any,
    game_db: GameDB,
    pe: PluginEngine,
    plugin_name: str,
    plugins_dir: str,
    blocks: list[dict],
    errors: list[str],
    verbose: bool = False,
) -> dict:
    """Execute a tool call against real GameDB. Returns tool result."""
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}
        errors.append(f"Invalid JSON args for {name}")

    if verbose:
        args_str = json.dumps(args, ensure_ascii=False)
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        print(f"    tool: {name}({args_str})")

    try:
        if name == "emit_block":
            return _handle_emit(args, blocks, errors)
        if name == "update_and_emit":
            return await _handle_update_and_emit(args, game_db, blocks, errors)
        if name == "db_read":
            return await _handle_db_read(args, game_db)
        if name.startswith("db_"):
            return await _handle_db(name, args, game_db)
        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        errors.append(f"Tool {name} error: {exc}")
        return {"error": str(exc)}


def _handle_emit(args: dict, blocks: list[dict], errors: list[str]) -> dict:
    block_type = args.get("type", "unknown")
    if block_type.startswith("json:"):
        block_type = block_type[5:]
    data = args.get("data", {})
    block = {"type": block_type, "data": data}
    blocks.append(block)
    errs = validate_block(block_type, data)
    errors.extend(errs)
    return {"status": "emitted", "type": block_type}


async def _handle_db(name: str, args: dict, db: GameDB) -> Any:
    if name == "db_graph_add":
        await db.graph_add(args["from_id"], args["to_id"], args["relation"], args.get("data"))
        return {"status": "ok"}
    if name == "db_log_append":
        await db.log_append(args["collection"], args["entry"])
        return {"status": "ok"}
    if name == "db_log_query":
        return await db.log_query(args["collection"], args.get("limit", 10))
    return {"error": f"Unknown db tool: {name}"}


async def _handle_update_and_emit(args: dict, db: GameDB, blocks: list[dict], errors: list[str]) -> dict:
    """Handle the composite update_and_emit tool."""
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
        block_type = emit.get("type", "unknown")
        if block_type.startswith("json:"):
            block_type = block_type[5:]
        data = emit.get("data", {})
        block = {"type": block_type, "data": data}
        blocks.append(block)
        errs = validate_block(block_type, data)
        errors.extend(errs)
        emitted_types.append(block_type)

    result: dict[str, Any] = {"status": "ok", "written": written}
    if emitted_types:
        result["emitted"] = emitted_types
    return result


async def _handle_db_read(args: dict, db: GameDB) -> Any:
    """Handle the unified db_read tool."""
    collection = args["collection"]
    key = args.get("key")
    if key:
        val = await db.kv_get(collection, key)
        return val if val is not None else {"_empty": True}
    return await db.kv_query(collection)


# ---------------------------------------------------------------------------
# Core test runner
# ---------------------------------------------------------------------------

async def test_one_plugin(
    plugin: dict,
    llm_config: dict[str, Any],
    game_state: dict[str, Any],
    narrative: str,
    db_engine: Any,
    plugins_dir: str,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run a single plugin through the LLM with real DB. Returns result dict."""
    name = plugin["name"]
    content = plugin["content"]
    metadata = plugin.get("metadata", {})

    # Build system prompt
    block_instructions = build_block_instructions(metadata)
    system_parts = [SYSTEM_PROMPT, f"## 插件指令 ({name})\n{content}"]
    if block_instructions:
        system_parts.append(f"## Block 格式参考\n{block_instructions}")

    state_json = json.dumps(game_state, ensure_ascii=False, default=str)
    context_text = f"## 叙事文本\n{narrative}\n\n## 当前游戏状态\n{state_json}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": context_text},
    ]
    tools = get_all_tools()

    call_kwargs: dict[str, Any] = {
        "model": llm_config["model"],
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
    }
    if llm_config.get("api_key"):
        call_kwargs["api_key"] = llm_config["api_key"]
    if llm_config.get("api_base"):
        call_kwargs["api_base"] = llm_config["api_base"]

    result: dict[str, Any] = {
        "plugin": name, "ok": False, "rounds": 0,
        "tool_calls": [], "blocks": [], "errors": [],
        "db_ops": [], "latency_ms": 0,
    }
    blocks: list[dict] = []
    pe = PluginEngine()
    session_id = f"test-{uuid.uuid4().hex[:8]}"

    t0 = time.monotonic()

    async with SQLModelAsyncSession(db_engine, expire_on_commit=False) as db:
        game_db = GameDB(db, session_id)

        for round_idx in range(MAX_TOOL_ROUNDS):
            result["rounds"] = round_idx + 1
            # Retry with backoff on rate limit errors
            response = None
            for retry in range(3):
                try:
                    response = await litellm.acompletion(**call_kwargs)
                    break
                except litellm.RateLimitError:
                    wait = (retry + 1) * 5
                    if verbose:
                        print(f"    [rate limit] waiting {wait}s...")
                    await asyncio.sleep(wait)
                except Exception as exc:
                    result["errors"].append(f"LLM error (round {round_idx}): {type(exc).__name__}: {exc}")
                    break
            if response is None:
                if not result["errors"]:
                    result["errors"].append(f"Rate limit exhausted after 3 retries (round {round_idx})")
                break

            message = response.choices[0].message
            if not message.tool_calls:
                if verbose and message.content:
                    print(f"    [round {round_idx}] text: {message.content[:150]}")
                break

            messages.append(message.model_dump(exclude_none=True))

            for tc in message.tool_calls:
                tool_result = await execute_tool(
                    tc, game_db, pe, name, plugins_dir,
                    blocks, result["errors"], verbose,
                )
                result["tool_calls"].append(tc.function.name)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                })

        # Dump DB state after test
        snapshot = await game_db.build_state_snapshot()
        if snapshot.get("kv") or snapshot.get("graph"):
            result["db_snapshot"] = snapshot

    result["latency_ms"] = int((time.monotonic() - t0) * 1000)
    result["blocks"] = blocks
    result["ok"] = len(result["errors"]) == 0
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plugin Agent 集成测试 — 真实 tool-call 链 + DB 持久化",
    )
    parser.add_argument("-p", "--plugins", nargs="*",
                        help="要测试的插件名（留空测试全部）")
    parser.add_argument("--all", action="store_true",
                        help="测试所有插件（每个插件自动选择最佳预设）")
    parser.add_argument("--skip", nargs="*", default=[],
                        help=f"跳过的插件名（--all 模式默认跳过: {', '.join(DEFAULT_SKIP)}）")
    parser.add_argument("--delay", type=float, default=0,
                        help="每个插件测试之间的延迟秒数（用于 rate-limited API）")
    parser.add_argument("--list", action="store_true",
                        help="列出所有可用插件")
    parser.add_argument("--narrative", type=str,
                        help="自定义叙事文本（覆盖预设）")
    parser.add_argument("--preset", choices=list(PRESETS.keys()),
                        default=DEFAULT_PRESET,
                        help=f"预设场景（默认: {DEFAULT_PRESET}）")
    parser.add_argument("--model", help="覆盖模型名")
    parser.add_argument("--api-key", help="覆盖 API Key")
    parser.add_argument("--api-base", help="覆盖 API Base")
    parser.add_argument("--dry-run", action="store_true",
                        help="只显示配置，不调用模型")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="显示详细的 tool call 日志")
    parser.add_argument("--plugins-dir", default="plugins",
                        help="插件目录（默认: plugins）")
    parser.add_argument("--db-path", default="data/test_plugin.sqlite",
                        help="测试 DB 路径（默认: data/test_plugin.sqlite）")
    return parser.parse_args()


def print_config(llm_config: dict, plugins: list[dict], preset: str) -> None:
    print("=== Plugin Agent Test ===")
    print(f"model    : {llm_config['model']}")
    print(f"api_base : {llm_config['api_base'] or '(provider default)'}")
    print(f"api_key  : {'set' if llm_config['api_key'] else 'NOT SET'}")
    print(f"preset   : {preset}")
    print(f"plugins  : {', '.join(p['name'] for p in plugins)}")
    print()


def print_results(results: list[dict]) -> None:
    passed = sum(1 for r in results if r["ok"])
    total = len(results)

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} plugins passed")
    print(f"{'='*60}")

    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        blocks_info = []
        for b in r["blocks"]:
            blocks_info.append(b["type"])
        blocks_str = ", ".join(blocks_info) if blocks_info else "(none)"
        tools_str = ", ".join(r["tool_calls"]) if r["tool_calls"] else "(none)"

        print(f"\n[{status}] {r['plugin']} ({r['latency_ms']}ms, {r['rounds']} rounds)")
        print(f"  tools  : {tools_str}")
        print(f"  blocks : {blocks_str}")

        if r["errors"]:
            for err in r["errors"]:
                print(f"  ERROR  : {err}")

        # Print block data details
        for b in r["blocks"]:
            data_str = json.dumps(b["data"], ensure_ascii=False, indent=2)
            if len(data_str) > 500:
                data_str = data_str[:500] + "\n  ..."
            print(f"  --- {b['type']} ---")
            print(f"  {data_str}")

        # Print DB snapshot if any
        snap = r.get("db_snapshot")
        if snap:
            print(f"  --- DB snapshot ---")
            snap_str = json.dumps(snap, ensure_ascii=False, indent=2)
            if len(snap_str) > 400:
                snap_str = snap_str[:400] + "\n  ..."
            print(f"  {snap_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> int:
    args = parse_args()
    settings = Settings(_env_file=REPO_ROOT / ".env")
    plugins = discover_plugins(args.plugins_dir)

    if args.list:
        print("Available plugins:")
        for p in plugins:
            print(f"  {p['name']:20s} [{p['type']:8s}] {p['description']}")
        print(f"\nPresets: {', '.join(PRESETS.keys())}")
        for k, v in PRESETS.items():
            print(f"  {k:12s} — {v['label']}")
        return 0

    # Filter plugins
    run_all = args.all or (args.plugins is None and not args.list)
    if run_all:
        skip_set = set(args.skip) | DEFAULT_SKIP
        plugins = [p for p in plugins if p["name"] not in skip_set]
        if skip_set - DEFAULT_SKIP:
            print(f"Skipping: {', '.join(skip_set)}")
    elif args.plugins:
        selected = [p for p in plugins if p["name"] in args.plugins]
        unknown = set(args.plugins) - {p["name"] for p in selected}
        if unknown:
            print(f"Warning: unknown plugins: {', '.join(unknown)}")
        plugins = selected

    if not plugins:
        print("No plugins to test. Use --list to see available plugins.")
        return 1

    llm_config = resolve_plugin_config(settings, args)
    print_config(llm_config, plugins, args.preset)

    if not llm_config.get("api_key"):
        print("ERROR: No API key. Set PLUGIN_LLM_API_KEY or LLM_API_KEY in .env")
        return 1

    # Resolve narrative and game state
    preset = PRESETS[args.preset]
    narrative = args.narrative or preset["narrative"]
    game_state = preset["game_state"]

    if args.dry_run:
        print("(dry-run mode)")
        print(f"narrative: {narrative[:100]}...")
        for p in plugins:
            mapped = PLUGIN_PRESET_MAP.get(p["name"], args.preset)
            print(f"  would test: {p['name']} (preset: {mapped})")
        return 0

    # Setup test DB
    db_engine = await setup_test_db(args.db_path)
    print(f"Test DB: {args.db_path}")
    if not run_all:
        print(f"Narrative: {narrative[:80]}...\n")

    # Run tests
    results: list[dict] = []
    for i, plugin in enumerate(plugins):
        # Per-plugin preset in --all mode
        if run_all:
            mapped_preset = PLUGIN_PRESET_MAP.get(plugin["name"], args.preset)
            p_data = PRESETS[mapped_preset]
            p_narrative = p_data["narrative"]
            p_game_state = p_data["game_state"]
        else:
            mapped_preset = args.preset
            p_narrative = narrative
            p_game_state = game_state

        print(f"Testing [{plugin['name']}] (preset: {mapped_preset})...", end=" ", flush=True)
        result = await test_one_plugin(
            plugin, llm_config, p_game_state, p_narrative,
            db_engine, args.plugins_dir, args.verbose,
        )
        results.append(result)
        status = "OK" if result["ok"] else "FAIL"
        print(f"{status} ({result['latency_ms']}ms)")

        # Rate-limit delay between plugins
        if args.delay > 0 and i < len(plugins) - 1:
            await asyncio.sleep(args.delay)

    print_results(results)

    await db_engine.dispose()
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
