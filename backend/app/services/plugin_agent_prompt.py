"""Plugin Agent — prompt building, sanitization, and schema example generation."""
from __future__ import annotations

import json
import pathlib
from typing import Any

from backend.app.core.plugin_engine import BlockDeclaration
from backend.app.core.plugin_trigger import (
    BLOCK_TRIGGER_ONCE_PER_SESSION,
    normalize_block_trigger_policy,
)

__all__ = [
    "SINGLE_PLUGIN_SYSTEM_PROMPT",
    "_agent_prompt_config",
    "_resolve_prompt_file",
    "_read_prompt_file",
    "_resolve_base_prompt",
    "_sanitize_plugin_prompt",
    "_resolve_output_instruction",
    "_build_tool_instructions",
    "_example_string_for_key",
    "_build_example_from_schema",
    "_build_output_schema_summary",
    "_build_emit_example",
    "_build_output_declarations",
    "_resolve_output_gate",
    "_build_block_instructions",
]

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


def _normalize_prompt_language(session_language: str | None) -> str | None:
    normalized = str(session_language or "").strip().lower()
    if normalized.startswith("zh"):
        return "zh"
    if normalized.startswith("en"):
        return "en"
    return None


def _localized_prompt_rel_paths(rel_path: str | None, session_language: str | None) -> list[str]:
    rel = str(rel_path or "").strip()
    if not rel:
        return []
    lang = _normalize_prompt_language(session_language)
    if not lang:
        return [rel]

    rel_path_obj = pathlib.PurePosixPath(rel)
    filename = rel_path_obj.name
    if not filename:
        return [rel]

    if "." in filename:
        stem, suffix = filename.rsplit(".", 1)
        localized_name = f"{stem}.{lang}.{suffix}"
        fallback_en_name = f"{stem}.en.{suffix}"
    else:
        localized_name = f"{filename}.{lang}"
        fallback_en_name = f"{filename}.en"

    parent = rel_path_obj.parent.as_posix()

    def _join_parent(name: str) -> str:
        if parent in {"", "."}:
            return name
        return f"{parent}/{name}"

    candidates = [_join_parent(localized_name)]
    if lang != "en":
        candidates.append(_join_parent(fallback_en_name))
    candidates.append(rel)

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _resolve_localized_prompt_file(
    plugin_root: pathlib.Path | None,
    rel_path: str | None,
    *,
    session_language: str | None = None,
) -> pathlib.Path | None:
    for candidate_rel in _localized_prompt_rel_paths(rel_path, session_language):
        path = _resolve_prompt_file(plugin_root, candidate_rel)
        if path is not None:
            return path
    return None


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
    *,
    session_language: str | None = None,
) -> str:
    cfg = _agent_prompt_config(metadata)
    base_path = _resolve_localized_prompt_file(
        plugin_root,
        cfg.get("base_file"),
        session_language=session_language,
    )
    if base_path is None:
        base_path = _resolve_localized_prompt_file(
            plugin_root,
            "prompts/agent/base.md",
            session_language=session_language,
        )
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
    session_language: str | None = None,
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

    text = _read_prompt_file(
        _resolve_localized_prompt_file(
            plugin_root,
            candidate_rel,
            session_language=session_language,
        )
    )
    if text:
        return _sanitize_plugin_prompt(text)

    return _sanitize_plugin_prompt(str(output_cfg.get("instruction") or "").strip())


def _build_tool_instructions(
    *,
    plugin_root: pathlib.Path | None,
    metadata: dict[str, Any],
    tools: list[dict[str, Any]],
    session_language: str | None = None,
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
        text = _read_prompt_file(
            _resolve_localized_prompt_file(
                plugin_root,
                rel,
                session_language=session_language,
            )
        )
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
    session_language: str | None = None,
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
            session_language=session_language,
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
