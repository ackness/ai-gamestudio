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
    uv run python scripts/test_plugin_agent.py --all -j 4            # run plugins concurrently
    uv run python scripts/test_plugin_agent.py --db-path data/test.db  # custom DB path
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
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
from backend.app.core.block_validation import validate_block_data
from backend.app.core.plugin_engine import BlockDeclaration, PluginEngine
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
- 优先一次调用 emit 同时完成写库（writes/logs）和结构化输出（items）
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


def sanitize_plugin_content(content: str) -> str:
    """Drop legacy block/JSON-output wording to enforce tool-first testing."""
    lines: list[str] = []
    for raw in content.splitlines():
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


def _example_string_for_key(key: str) -> str:
    mapping = {
        "action": "create",
        "character_id": "new",
        "content": "提示内容",
        "description": "简短描述",
        "event_type": "world",
        "level": "info",
        "name": "名称",
        "prompt": "请选择下一步行动",
        "quest_id": "quest_001",
        "title": "标题",
        "type": "single",
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


def _build_emit_example(output_type: str, output_cfg: dict[str, Any]) -> str:
    schema = output_cfg.get("schema") if isinstance(output_cfg.get("schema"), dict) else {}
    data_example = _build_example_from_schema(schema, key="data")
    if not isinstance(data_example, dict):
        data_example = {}
    payload = {"items": [{"type": output_type, "data": data_example}]}
    return "emit(" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ")"


def _build_output_declarations(
    outputs: dict[str, Any],
    plugin_name: str,
) -> dict[str, BlockDeclaration]:
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


def build_block_instructions(metadata: dict) -> str:
    """Build concise tool-first output hints from manifest metadata."""
    outputs = metadata.get("outputs")
    if not outputs or not isinstance(outputs, dict):
        return ""
    parts: list[str] = []
    for output_type, decl in outputs.items():
        if not isinstance(decl, dict):
            continue
        schema = decl.get("schema")
        schema_summary = "data 必须是对象。"
        if isinstance(schema, dict):
            props = schema.get("properties")
            required = [str(k) for k in (schema.get("required") or []) if isinstance(k, str)]
            keys = [str(k) for k in props.keys()][:6] if isinstance(props, dict) else []
            schema_summary = (
                f"required={', '.join(required) if required else '无'}; "
                f"keys={', '.join(keys) if keys else '无'}"
            )
        parts.append(
            "\n".join(
                [
                    f"### {output_type}",
                    f"- schema: {schema_summary}",
                    f"- 调用模板: emit({{\"items\":[{{\"type\":\"{output_type}\",\"data\":{{...}}}}]}})",
                    f"- 简例: {_build_emit_example(output_type, decl)}",
                ]
            )
        )
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

def validate_block(
    block_type: str,
    data: Any,
    declaration: BlockDeclaration | None = None,
) -> list[str]:
    """Validation of emitted blocks using runtime schema + built-in semantics."""
    errors = validate_block_data(block_type, data, declaration)

    if block_type == "character_sheet" and isinstance(data, dict):
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

    if block_type in {"choice", "choices"} and isinstance(data, dict):
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
            if "**" in text or "`" in text:
                errors.append(
                    f"choices.data.options[{idx}] must be plain text without markdown formatting"
                )
    return errors


def _tool_error_payload(
    *,
    tool: str,
    code: str,
    message: str,
    details: str | None = None,
    retryable: bool = True,
) -> dict[str, Any]:
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
    warnings: list[str],
    verbose: bool = False,
) -> dict:
    """Execute a tool call against real GameDB. Returns tool result."""
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}
        warnings.append(f"{name}: invalid JSON args")
        return _tool_error_payload(
            tool=name,
            code="INVALID_ARGUMENTS",
            message="arguments must be valid JSON object",
            retryable=True,
        )

    if verbose:
        args_str = json.dumps(args, ensure_ascii=False)
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        print(f"    tool: {name}({args_str})")

    try:
        if name == "emit":
            return await _handle_emit(
                args,
                game_db,
                blocks,
                errors,
                warnings,
                plugin_name=plugin_name,
                pe=pe,
                plugins_dir=plugins_dir,
            )
        if name == "db_read":
            return await _handle_db_read(args, game_db)
        if name.startswith("db_"):
            return await _handle_db(name, args, game_db)
        errors.append(f"Unknown tool: {name}")
        return _tool_error_payload(
            tool=name,
            code="UNKNOWN_TOOL",
            message=f"unknown tool '{name}'",
            retryable=False,
        )
    except Exception as exc:
        warnings.append(f"Tool {name} error: {exc}")
        return _tool_error_payload(
            tool=name,
            code="EXECUTION_FAILED",
            message=str(exc),
            details=type(exc).__name__,
            retryable=True,
        )


async def _handle_emit(
    args: dict,
    db: GameDB,
    blocks: list[dict],
    errors: list[str],
    warnings: list[str],
    *,
    plugin_name: str,
    pe: PluginEngine,
    plugins_dir: str,
) -> dict:
    writes = args.get("writes", [])
    logs = args.get("logs", [])
    items = args.get("items")
    if not isinstance(items, list):
        items = []

    declared_output_types: set[str] = set()
    declared_output_declarations: dict[str, BlockDeclaration] = {}
    loaded = pe.load(plugin_name, plugins_dir)
    if loaded:
        metadata = loaded.get("metadata", {})
        outputs = metadata.get("outputs") if isinstance(metadata, dict) else None
        if isinstance(outputs, dict):
            declared_output_types = {
                str(name).strip()
                for name in outputs.keys()
                if str(name).strip()
            }
            declared_output_declarations = _build_output_declarations(outputs, plugin_name)

    pending_blocks: list[dict[str, Any]] = []
    strict_errors: list[str] = []
    emitted_types: list[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("type") or item.get("block_type") or "").strip() or "unknown"
        if block_type.startswith("json:"):
            block_type = block_type[5:]
        if block_type not in declared_output_types:
            continue
        data = item.get("data", item.get("payload", {}))
        if not isinstance(data, dict):
            strict_errors.append(f"items[{idx}] ({block_type}): data must be an object")
            continue
        declaration = declared_output_declarations.get(block_type)
        errs = validate_block(
            block_type,
            data,
            declaration if isinstance(declaration, BlockDeclaration) else None,
        )
        if errs:
            strict_errors.extend([f"items[{idx}] ({block_type}): {err}" for err in errs])
            continue
        pending_blocks.append({"type": block_type, "data": data})
        emitted_types.append(block_type)

    if strict_errors:
        warnings.extend(strict_errors)
        return {
            "status": "error",
            "errors": strict_errors,
            "warnings": warnings,
            "text": "EMIT_ERROR: " + "; ".join(strict_errors[:3]),
        }

    written = 0
    for write in writes:
        if not isinstance(write, dict):
            continue
        collection = str(write.get("collection") or "").strip()
        key = str(write.get("key") or "").strip()
        if not collection or not key or "value" not in write:
            warnings.append("emit.writes item ignored: requires collection/key/value")
            continue
        await db.kv_set(collection, key, write["value"])
        written += 1

    for log_entry in logs:
        if isinstance(log_entry, dict):
            collection = str(log_entry.get("collection") or "").strip()
            entry = log_entry.get("entry")
            if not collection or not isinstance(entry, dict):
                warnings.append("emit.logs item ignored: requires collection/object entry")
                continue
            await db.log_append(collection, entry)

    blocks.extend(pending_blocks)

    result: dict[str, Any] = {"status": "ok", "written": written}
    if emitted_types:
        result["emitted"] = emitted_types
    if warnings:
        result["warnings"] = warnings
    return result


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
    system_parts = [SYSTEM_PROMPT, f"## 插件指令 ({name})\n{sanitize_plugin_content(content)}"]
    if block_instructions:
        system_parts.append(f"## 结构化输出参考\n{block_instructions}")

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
        "tool_calls": [], "blocks": [], "errors": [], "warnings": [],
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
                    blocks, result["errors"], result["warnings"], verbose,
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

def positive_int(value: str) -> int:
    """argparse helper for positive integers."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


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
                        help="串行时为插件间延迟；并发时为任务启动错峰延迟（秒）")
    parser.add_argument("-j", "--concurrency", type=positive_int, default=None,
                        help="并发运行的插件数（--all 默认自动并行，其他场景默认 1）")
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
        if r.get("warnings"):
            for warn in r["warnings"]:
                print(f"  WARN   : {warn}")

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

    # Build test plan
    test_plan: list[dict[str, Any]] = []
    for plugin in plugins:
        if run_all:
            mapped_preset = PLUGIN_PRESET_MAP.get(plugin["name"], args.preset)
            p_data = PRESETS[mapped_preset]
            p_narrative = p_data["narrative"]
            p_game_state = p_data["game_state"]
        else:
            mapped_preset = args.preset
            p_narrative = narrative
            p_game_state = game_state
        test_plan.append({
            "plugin": plugin,
            "mapped_preset": mapped_preset,
            "narrative": p_narrative,
            "game_state": p_game_state,
        })

    # Default concurrency:
    # - --all mode: parallel by default to reduce wall-clock test time
    # - targeted mode: sequential by default
    if args.concurrency is None:
        args.concurrency = min(4, max(1, len(test_plan))) if run_all else 1

    # Run tests (parallel when --concurrency > 1)
    ordered_results: list[dict[str, Any] | None] = [None] * len(test_plan)

    if args.concurrency <= 1:
        for i, item in enumerate(test_plan):
            plugin = item["plugin"]
            mapped_preset = item["mapped_preset"]
            print(f"Testing [{plugin['name']}] (preset: {mapped_preset})...", end=" ", flush=True)
            result = await test_one_plugin(
                plugin,
                llm_config,
                item["game_state"],
                item["narrative"],
                db_engine,
                args.plugins_dir,
                args.verbose,
            )
            ordered_results[i] = result
            status = "OK" if result["ok"] else "FAIL"
            print(f"{status} ({result['latency_ms']}ms)")

            # Rate-limit delay between plugins
            if args.delay > 0 and i < len(test_plan) - 1:
                await asyncio.sleep(args.delay)
    else:
        print(f"Running in parallel with concurrency={args.concurrency}")
        semaphore = asyncio.Semaphore(args.concurrency)

        async def run_one(index: int, item: dict[str, Any]) -> tuple[int, str, str, dict[str, Any]]:
            plugin = item["plugin"]
            mapped_preset = item["mapped_preset"]

            # Optional stagger to reduce burst traffic on rate-limited APIs.
            if args.delay > 0:
                await asyncio.sleep(index * args.delay)

            async with semaphore:
                result = await test_one_plugin(
                    plugin,
                    llm_config,
                    item["game_state"],
                    item["narrative"],
                    db_engine,
                    args.plugins_dir,
                    args.verbose,
                )
            return index, plugin["name"], mapped_preset, result

        tasks = [
            asyncio.create_task(run_one(index, item))
            for index, item in enumerate(test_plan)
        ]
        completed = 0
        for task in asyncio.as_completed(tasks):
            index, plugin_name, mapped_preset, result = await task
            ordered_results[index] = result
            completed += 1
            status = "OK" if result["ok"] else "FAIL"
            print(
                f"[{completed}/{len(test_plan)}] "
                f"[{plugin_name}] (preset: {mapped_preset}) {status} ({result['latency_ms']}ms)"
            )

    results = [r for r in ordered_results if r is not None]

    print_results(results)

    await db_engine.dispose()
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
