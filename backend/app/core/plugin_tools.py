"""Plugin Agent tool definitions and execution routing."""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

from backend.app.core.game_db import GameDB

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function calling format, LiteLLM compatible)
# ---------------------------------------------------------------------------

PLUGIN_AGENT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_plugins",
            "description": "列出所有启用的插件及其简要描述",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_plugin",
            "description": "加载插件的完整提示词和指令",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "插件名称"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_script",
            "description": "执行插件脚本",
            "parameters": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string"},
                    "function": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["plugin", "function"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emit_block",
            "description": "输出一个结构化 block 到前端（如 state_update, guide, notification 等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "block 类型"},
                    "data": {"type": "object", "description": "block 数据"},
                },
                "required": ["type", "data"],
            },
        },
    },
]

GAME_DB_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "db_kv_get",
            "description": "从游戏数据库获取键值数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string", "description": "命名空间，如 character.attributes"},
                    "key": {"type": "string"},
                },
                "required": ["collection", "key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "db_kv_set",
            "description": "写入键值数据到游戏数据库",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "key": {"type": "string"},
                    "value": {"type": "object"},
                },
                "required": ["collection", "key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "db_kv_query",
            "description": "查询某个 collection 下的所有键值",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "filter_key": {"type": "string", "description": "可选的 key 模糊匹配"},
                },
                "required": ["collection"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "db_graph_add",
            "description": "添加关系边（NPC关系、阵营关系等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_id": {"type": "string"},
                    "to_id": {"type": "string"},
                    "relation": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["from_id", "to_id", "relation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "db_graph_query",
            "description": "查询关系图",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "relation": {"type": "string"},
                    "direction": {"type": "string", "enum": ["out", "in", "both"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "db_log_append",
            "description": "追加日志条目（战斗记录、骰子历史等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "entry": {"type": "object"},
                },
                "required": ["collection", "entry"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "db_log_query",
            "description": "查询日志",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["collection"],
            },
        },
    },
]


def get_all_tools() -> list[dict]:
    return PLUGIN_AGENT_TOOLS + GAME_DB_TOOLS
