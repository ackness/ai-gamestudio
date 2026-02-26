"""Plugin Agent — tool context and tool execution."""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone
from typing import Any
import uuid

from loguru import logger

from backend.app.core.block_validation import validate_block_data
from backend.app.core.llm_config import ResolvedLlmConfig
from backend.app.core.network_safety import ensure_safe_api_base
from backend.app.core.plugin_engine import BlockDeclaration
from backend.app.core.script_runner import PythonScriptRunner
from backend.app.core.storage_port import Scope

__all__ = [
    "_ToolContext",
    "_build_call_kwargs",
    "_tool_error_response",
    "_execute_tool",
    "OUTPUT_VERSION",
    "KNOWN_OUTPUT_STATUS",
    "MARKDOWN_OPTION_PATTERNS",
    "_normalize_output_type",
    "_normalize_output_status",
    "_normalize_output_meta",
    "_normalize_choice_options",
    "_normalize_output_data",
    "_collect_emit_items",
    "_build_output_item",
    "_validate_emit_item_data",
    "_handle_emit",
    "_handle_db_read",
    "_handle_execute_script",
]

OUTPUT_VERSION = "1.0"
KNOWN_OUTPUT_STATUS = {"queued", "generating", "done", "failed"}
MARKDOWN_OPTION_PATTERNS = (
    r"\*\*",
    r"`",
    r"^\s*[-*]\s+",
    r"^\s*\d+[.)]\s+",
)


class _ToolContext:
    __slots__ = (
        "session_id",
        "game_db",
        "storage",
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
        # Ensure storage/game_db defaults so callers can pass either
        if not hasattr(self, "storage"):
            self.storage = None
        if not hasattr(self, "game_db"):
            self.game_db = None


def _build_call_kwargs(config: ResolvedLlmConfig, messages: list, tools: list, *, reasoning_effort: str | None = "none") -> dict:
    kw: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
        "drop_params": True,  # auto-drop unsupported params across providers
    }
    # Reasoning control: default "none" disables thinking for plugin calls
    enable_thinking = bool(reasoning_effort and reasoning_effort != "none")
    if enable_thinking:
        kw["reasoning_effort"] = reasoning_effort
    # Also pass enable_thinking via extra_body for OpenAI-compatible APIs (Qwen, etc.)
    kw["extra_body"] = {"enable_thinking": enable_thinking}
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
        strict_errors.append("plugin declares no outputs; do NOT call emit with items")
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
            strict_errors.append(
                f"undeclared output type: {output_type}; allowed types: {sorted(declared_output_types) if declared_output_types else 'none'}"
            )
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

    ns = ctx.plugin_name
    written = 0
    for w in writes:
        if not isinstance(w, dict):
            continue
        if getattr(ctx, "storage", None):
            await ctx.storage.kv_set(Scope.SESSION, ns, w["collection"], w["key"], w["value"])
        else:
            await ctx.game_db.kv_set(w["collection"], w["key"], w["value"])
        written += 1

    logged = 0
    for log_entry in logs:
        if isinstance(log_entry, dict):
            if getattr(ctx, "storage", None):
                await ctx.storage.log_append(Scope.SESSION, ns, log_entry["collection"], log_entry["entry"])
            else:
                await ctx.game_db.log_append(log_entry["collection"], log_entry["entry"])
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
    ns = ctx.plugin_name
    if getattr(ctx, "storage", None):
        if key:
            val = await ctx.storage.kv_get(Scope.SESSION, ns, collection, key)
            return val if val is not None else {"_empty": True}
        return await ctx.storage.kv_query(Scope.SESSION, ns, collection)
    else:
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
                ns = ctx.plugin_name
                if getattr(ctx, "storage", None):
                    await ctx.storage.log_append(Scope.SESSION, ns, args["collection"], args["entry"])
                else:
                    await ctx.game_db.log_append(args["collection"], args["entry"])
                return {"status": "ok"}
            case "db_log_query":
                ns = ctx.plugin_name
                if getattr(ctx, "storage", None):
                    return await ctx.storage.log_query(Scope.SESSION, ns, args["collection"], limit=args.get("limit", 10))
                else:
                    return await ctx.game_db.log_query(args["collection"], args.get("limit", 10))
            case "db_graph_add":
                ns = ctx.plugin_name
                if getattr(ctx, "storage", None):
                    await ctx.storage.graph_add(Scope.SESSION, ns, args["from_id"], args["to_id"], args["relation"], args.get("data"))
                else:
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
