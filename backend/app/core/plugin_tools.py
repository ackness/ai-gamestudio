"""Plugin Agent tool definitions (optimized: 14 → 7 tools)."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function calling format, LiteLLM compatible)
# ---------------------------------------------------------------------------

PLUGIN_AGENT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_and_emit",
            "description": "批量写入 DB 并可选输出多个 block 到前端。最常用的复合操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "writes": {
                        "type": "array",
                        "description": "KV 写入列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "collection": {"type": "string"},
                                "key": {"type": "string"},
                                "value": {"description": "任意 JSON 值"},
                            },
                            "required": ["collection", "key", "value"],
                        },
                    },
                    "emits": {
                        "type": "array",
                        "description": "可选：输出多个 block 到前端",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "description": "block 类型"},
                                "data": {"type": "object", "description": "block 数据"},
                            },
                            "required": ["type", "data"],
                        },
                    },
                    "logs": {
                        "type": "array",
                        "description": "可选：追加多条日志",
                        "items": {
                            "type": "object",
                            "properties": {
                                "collection": {"type": "string"},
                                "entry": {"type": "object"},
                            },
                            "required": ["collection", "entry"],
                        },
                    },
                },
                "required": ["writes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emit_block",
            "description": "输出纯展示 block（无需 DB 写入的插件用，如 guide）",
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
    {
        "type": "function",
        "function": {
            "name": "db_read",
            "description": "读取游戏数据（单 key 或整个 collection）。注意：当前游戏状态已在上下文中，仅在需要最新数据时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string"},
                    "key": {"type": ["string", "null"], "description": "指定 key 读取单条；不传则返回 collection 全部"},
                },
                "required": ["collection"],
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
            "name": "execute_script",
            "description": "执行插件脚本能力",
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
]


def get_all_tools() -> list[dict]:
    return PLUGIN_AGENT_TOOLS
