"""Plugin Agent tool definitions."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function calling format, LiteLLM compatible)
# ---------------------------------------------------------------------------

PLUGIN_AGENT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "emit",
            "description": "统一输出工具。一次调用可写入状态（writes/logs）并输出一个或多个结构化 item。",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "writes": {
                        "type": "array",
                        "description": "可选：KV 写入列表",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "collection": {"type": "string"},
                                "key": {"type": "string"},
                                "value": {},
                            },
                            "required": ["collection", "key", "value"],
                        },
                    },
                    "logs": {
                        "type": "array",
                        "description": "可选：日志追加列表",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "collection": {"type": "string"},
                                "entry": {"type": "object"},
                            },
                            "required": ["collection", "entry"],
                        },
                    },
                    "items": {
                        "type": "array",
                        "description": "可选：待输出结构列表（仅支持插件 manifest.outputs 声明过的类型）",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string", "description": "可选：输出 ID，用于异步更新同一输出"},
                                "type": {
                                    "type": "string",
                                    "description": "输出类型，如 choices/notification/story_image（必须是插件 manifest.outputs 已声明类型）",
                                },
                                "data": {"type": "object", "description": "输出数据对象"},
                                "meta": {"type": "object", "description": "可选元信息（如 group_id）"},
                                "status": {
                                    "type": "string",
                                    "description": "输出状态，默认 done",
                                    "enum": ["queued", "generating", "done", "failed"],
                                },
                            },
                            "required": ["type", "data"],
                        },
                    },
                    "meta": {"type": "object", "description": "默认元信息，会并入每个 item.meta"},
                },
                "required": [],
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
