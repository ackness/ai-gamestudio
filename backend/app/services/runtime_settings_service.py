from __future__ import annotations

import json
import re
from typing import Any, Literal

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.config import settings
from backend.app.core.plugin_registry import get_plugin_engine
from backend.app.services.plugin_service import storage_get, storage_set

RUNTIME_SETTINGS_PLUGIN = "runtime-settings"
_PROJECT_KEY = "project"
_SESSION_PREFIX = "session:"
_SUPPORTED_TYPES = {"string", "number", "integer", "boolean", "enum"}
_SUPPORTED_SCOPES = {"project", "session", "both"}
_TPL_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _session_key(session_id: str) -> str:
    return f"{_SESSION_PREFIX}{session_id}"


def _normalize_field_type(raw: Any) -> str:
    value = str(raw or "string").strip().lower()
    if value == "int":
        value = "integer"
    if value not in _SUPPORTED_TYPES:
        return "string"
    return value


def _normalize_scope(raw: Any) -> str:
    value = str(raw or "project").strip().lower()
    if value not in _SUPPORTED_SCOPES:
        return "project"
    return value


def _normalize_options(raw: Any) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return options
    for item in raw:
        if isinstance(item, str):
            options.append({"label": item, "value": item})
        elif isinstance(item, dict):
            value = item.get("value")
            label = item.get("label")
            if value is None:
                continue
            options.append(
                {
                    "label": str(label if label is not None else value),
                    "value": value,
                }
            )
    return options


def _normalize_runtime_settings_fields(
    plugin_name: str,
    raw_fields: Any,
) -> list[dict[str, Any]]:
    if not isinstance(raw_fields, dict):
        return []

    fields: list[dict[str, Any]] = []
    for field_name, raw_cfg in raw_fields.items():
        if not isinstance(field_name, str) or not field_name.strip():
            continue
        cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
        field_type = _normalize_field_type(cfg.get("type"))
        options = _normalize_options(cfg.get("options"))
        key = f"{plugin_name}.{field_name}"
        label = str(cfg.get("label") or field_name.replace("_", " ").title())
        description = str(cfg.get("description") or "").strip()
        scope = _normalize_scope(cfg.get("scope"))
        component = str(cfg.get("component") or "").strip().lower()
        if not component:
            component = "select" if field_type == "enum" else "input"
            if field_type == "boolean":
                component = "toggle"
        order = 0
        try:
            order = int(cfg.get("order", 0))
        except Exception:
            order = 0

        affects = cfg.get("affects")
        normalized_affects = (
            [str(item).strip() for item in affects if str(item).strip()]
            if isinstance(affects, list)
            else []
        )

        field: dict[str, Any] = {
            "key": key,
            "plugin_name": plugin_name,
            "field": field_name,
            "type": field_type,
            "label": label,
            "description": description,
            "scope": scope,
            "component": component,
            "order": order,
            "affects": normalized_affects,
        }
        if options:
            field["options"] = options
        for numeric_key in ("min", "max", "step"):
            if numeric_key in cfg:
                field[numeric_key] = cfg[numeric_key]
        if "default" in cfg:
            field["default"] = cfg.get("default")
        fields.append(field)

    fields.sort(key=lambda item: (int(item.get("order", 0)), str(item["key"])))
    return fields


def get_runtime_settings_schema(
    enabled_plugins: list[str],
    plugins_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Collect runtime settings schema declared by enabled plugins."""
    pe = get_plugin_engine()
    plugins_dir = plugins_dir or settings.PLUGINS_DIR
    ordered = pe.resolve_dependencies(enabled_plugins, plugins_dir)

    schema_fields: list[dict[str, Any]] = []
    for name in ordered:
        plugin_data = pe.load(name, plugins_dir)
        if not plugin_data:
            continue
        metadata = plugin_data.get("metadata")
        if not isinstance(metadata, dict):
            continue
        extensions = metadata.get("extensions")
        if not isinstance(extensions, dict):
            continue
        runtime_settings = extensions.get("runtime_settings")
        if not isinstance(runtime_settings, dict):
            continue
        raw_fields = runtime_settings.get("fields")
        schema_fields.extend(_normalize_runtime_settings_fields(name, raw_fields))

    schema_fields.sort(
        key=lambda item: (
            enabled_plugins.index(item["plugin_name"])
            if item["plugin_name"] in enabled_plugins
            else 10_000,
            int(item.get("order", 0)),
            str(item["key"]),
        )
    )
    return schema_fields


def _schema_map(schema_fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(field["key"]): field for field in schema_fields}


def _defaults_from_schema(schema_fields: list[dict[str, Any]]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for field in schema_fields:
        if "default" in field:
            defaults[str(field["key"])] = field.get("default")
    return defaults


def _normalize_number(value: Any, *, integer: bool) -> float | int:
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric value")
    if isinstance(value, (int, float)):
        return int(value) if integer else float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError("empty numeric value")
        if integer:
            return int(raw)
        return float(raw)
    raise ValueError("numeric value expected")


def normalize_runtime_setting_value(field: dict[str, Any], value: Any) -> Any:
    """Normalize and validate a value against one schema field."""
    field_type = str(field.get("type") or "string")
    if field_type == "string":
        if isinstance(value, str):
            result: Any = value
        else:
            result = str(value)
    elif field_type == "boolean":
        if isinstance(value, bool):
            result = value
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                result = True
            elif lowered in {"false", "0", "no", "off"}:
                result = False
            else:
                raise ValueError(f"invalid boolean value: {value!r}")
        else:
            raise ValueError(f"invalid boolean value: {value!r}")
    elif field_type == "integer":
        result = _normalize_number(value, integer=True)
    elif field_type == "number":
        result = _normalize_number(value, integer=False)
    elif field_type == "enum":
        options = field.get("options")
        allowed = (
            {item.get("value") for item in options if isinstance(item, dict)}
            if isinstance(options, list)
            else set()
        )
        result = value
        if isinstance(value, str):
            result = value.strip()
        if allowed and result not in allowed:
            raise ValueError(f"value {result!r} not in enum {sorted(allowed)!r}")
    else:
        result = value

    if isinstance(result, (int, float)) and not isinstance(result, bool):
        if "min" in field and result < float(field["min"]):
            raise ValueError(f"value {result} < min {field['min']}")
        if "max" in field and result > float(field["max"]):
            raise ValueError(f"value {result} > max {field['max']}")

    return result


def _filter_known_values(
    raw_values: Any,
    field_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw_values, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw_values.items():
        if not isinstance(key, str) or key not in field_map:
            continue
        out[key] = value
    return out


async def resolve_runtime_settings(
    db: AsyncSession,
    *,
    project_id: str,
    enabled_plugins: list[str],
    session_id: str | None = None,
) -> dict[str, Any]:
    """Return effective runtime settings with schema and merged values."""
    schema_fields = get_runtime_settings_schema(enabled_plugins)
    field_map = _schema_map(schema_fields)
    defaults = _defaults_from_schema(schema_fields)

    project_raw = await storage_get(
        db,
        project_id,
        RUNTIME_SETTINGS_PLUGIN,
        _PROJECT_KEY,
    )
    project_overrides = _filter_known_values(project_raw, field_map)

    session_overrides: dict[str, Any] = {}
    if session_id:
        session_raw = await storage_get(
            db,
            project_id,
            RUNTIME_SETTINGS_PLUGIN,
            _session_key(session_id),
        )
        session_overrides = _filter_known_values(session_raw, field_map)

    merged = dict(defaults)
    merged.update(project_overrides)
    merged.update(session_overrides)

    normalized_merged: dict[str, Any] = {}
    for key, value in merged.items():
        field = field_map.get(key)
        if not field:
            continue
        try:
            normalized_merged[key] = normalize_runtime_setting_value(field, value)
        except Exception:
            logger.warning("Invalid runtime setting value ignored: {}={}", key, value)

    by_plugin: dict[str, dict[str, Any]] = {}
    for full_key, value in normalized_merged.items():
        plugin_name, _, field_name = full_key.partition(".")
        by_plugin.setdefault(plugin_name, {})[field_name] = value

    return {
        "schema_fields": schema_fields,
        "values": normalized_merged,
        "by_plugin": by_plugin,
        "project_overrides": project_overrides,
        "session_overrides": session_overrides,
    }


async def patch_runtime_settings(
    db: AsyncSession,
    *,
    project_id: str,
    enabled_plugins: list[str],
    scope: Literal["project", "session"],
    values: dict[str, Any],
    session_id: str | None = None,
    autocommit: bool = True,
) -> dict[str, Any]:
    """Patch project/session runtime setting overrides."""
    schema_fields = get_runtime_settings_schema(enabled_plugins)
    field_map = _schema_map(schema_fields)

    if scope == "session" and not session_id:
        raise ValueError("session_id required when scope=session")

    key = _PROJECT_KEY if scope == "project" else _session_key(str(session_id))
    current_raw = await storage_get(db, project_id, RUNTIME_SETTINGS_PLUGIN, key)
    current = current_raw if isinstance(current_raw, dict) else {}

    next_values = dict(current)
    for setting_key, setting_value in values.items():
        if setting_key not in field_map:
            raise ValueError(f"Unknown runtime setting key: {setting_key}")
        field = field_map[setting_key]
        field_scope = str(field.get("scope") or "project")
        if field_scope != "both" and field_scope != scope:
            raise ValueError(
                f"Setting '{setting_key}' does not support scope '{scope}'"
            )

        if setting_value is None:
            next_values.pop(setting_key, None)
            continue

        normalized = normalize_runtime_setting_value(field, setting_value)
        next_values[setting_key] = normalized

    await storage_set(
        db,
        project_id,
        RUNTIME_SETTINGS_PLUGIN,
        key,
        next_values,
        autocommit=autocommit,
    )

    return next_values


def render_settings_template(template: str, variables: dict[str, Any]) -> str:
    """Render a tiny {{ var }} template used by user runtime settings."""

    def _repl(match: re.Match[str]) -> str:
        name = match.group(1)
        value = variables.get(name, "")
        return str(value if value is not None else "")

    return _TPL_VAR_RE.sub(_repl, template)


def build_runtime_settings_prompt_block(resolved: dict[str, Any]) -> str | None:
    """Build a compact prompt section so DM obeys user runtime settings."""
    schema_fields = resolved.get("schema_fields")
    merged_values = resolved.get("values")
    if not isinstance(schema_fields, list) or not isinstance(merged_values, dict):
        return None
    if not schema_fields:
        return None

    field_map = _schema_map([f for f in schema_fields if isinstance(f, dict)])
    lines: list[str] = []
    for full_key, value in merged_values.items():
        field = field_map.get(full_key)
        if not field:
            continue
        label = str(field.get("label") or full_key)
        affects = field.get("affects")
        affects_text = (
            f" (affects: {', '.join(str(x) for x in affects)})"
            if isinstance(affects, list) and affects
            else ""
        )
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False)
        else:
            value_text = str(value)
        lines.append(f"- {label} = {value_text}{affects_text}")

    if not lines:
        return None

    return (
        "## Runtime Settings (User-Defined)\n"
        "Follow these settings in this turn for narration, choices, and generated assets.\n"
        + "\n".join(lines[:40])
    )
