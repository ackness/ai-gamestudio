from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from backend.app.core.plugin_engine import BlockDeclaration


_BUILTIN_BLOCK_SCHEMAS: dict[str, dict[str, Any]] = {
    "state_update": {
        "type": "object",
        "properties": {
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "character_id": {"type": "string"},
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                        "description": {"type": "string"},
                        "personality": {"type": "string"},
                        "attributes": {"type": "object"},
                        "inventory": {"type": "array"},
                    },
                },
            },
            "world": {
                "type": "object",
                "properties": {
                    "_delete": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    "character_sheet": {
        "type": "object",
        "properties": {
            "character_id": {"type": "string"},
            "name": {"type": "string"},
            "editable_fields": {"type": "array", "items": {"type": "string"}},
            "attributes": {"type": "object"},
            "inventory": {"type": "array"},
            "description": {"type": "string"},
            "role": {"type": "string"},
        },
        "required": ["name"],
    },
    "scene_update": {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "npcs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "character_id": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "role_in_scene": {"type": "string"},
                    },
                },
            },
        },
    },
    "event": {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "event_id": {"type": "string"},
            "parent_event_id": {"type": "string"},
            "event_type": {"type": "string"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "source": {"type": "string"},
            "visibility": {"type": "string"},
            "metadata": {"type": "object"},
        },
        "required": ["action"],
    },
}


def _type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(
            value, float
        )
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _schema_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []

    expected_type = schema.get("type")
    if isinstance(expected_type, str):
        if not _type_matches(value, expected_type):
            errors.append(
                f"{path}: expected {expected_type}, got {_schema_type_name(value)}"
            )
            return errors
    elif isinstance(expected_type, list):
        if not any(_type_matches(value, t) for t in expected_type):
            expected_names = ", ".join(str(t) for t in expected_type)
            errors.append(
                f"{path}: expected one of [{expected_names}], got {_schema_type_name(value)}"
            )
            return errors

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        errors.append(f"{path}: value {value!r} not in enum {enum_values!r}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(
                f"{path}: expected length >= {min_length}, got {len(value)}"
            )
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append(
                f"{path}: expected length <= {max_length}, got {len(value)}"
            )
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and len(pattern) <= 200:
            try:
                compiled = re.compile(pattern)
                if not compiled.search(value[:10000]):
                    errors.append(f"{path}: value does not match pattern {pattern!r}")
            except re.error:
                logger.warning("Invalid schema pattern ignored at {}: {}", path, pattern)

    if ((isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}: expected >= {minimum}, got {value}")
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{path}: expected <= {maximum}, got {value}")

    if isinstance(value, dict):
        required = schema.get("required") or []
        if isinstance(required, list):
            for field in required:
                if isinstance(field, str) and field not in value:
                    errors.append(f"{path}.{field}: required field missing")

        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    errors.extend(
                        _validate_schema(value[key], child_schema, f"{path}.{key}")
                    )

        additional = schema.get("additionalProperties")
        if additional is False and isinstance(properties, dict):
            allowed = set(properties.keys())
            for key in value.keys():
                if key not in allowed:
                    errors.append(f"{path}.{key}: additional property not allowed")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} items")
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path}: expected at most {max_items} items")

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(_validate_schema(item, item_schema, f"{path}[{idx}]"))

    return errors


def _validate_builtin_semantics(block_type: str, data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []

    errors: list[str] = []
    if block_type == "state_update":
        if "characters" not in data and "world" not in data:
            errors.append("$.state_update: either 'characters' or 'world' is required")
        world = data.get("world")
        if world is not None:
            if not isinstance(world, dict):
                errors.append("$.state_update.world: must be an object")
            else:
                delete_keys = world.get("_delete")
                if delete_keys is not None:
                    if not isinstance(delete_keys, list):
                        errors.append("$.state_update.world._delete: must be an array")
                    else:
                        for idx, key in enumerate(delete_keys):
                            if not isinstance(key, str) or not key.strip():
                                errors.append(
                                    f"$.state_update.world._delete[{idx}]: must be a non-empty string"
                                )
                patch_keys = [k for k in world.keys() if k != "_delete"]
                if not patch_keys and not delete_keys and "characters" not in data:
                    errors.append(
                        "$.state_update.world: empty world update (no fields or _delete)"
                    )

    elif block_type == "scene_update":
        action = data.get("action", "move")
        if action not in {"move", "update"}:
            # Auto-normalize unknown action to "move" (matches handler behavior)
            logger.warning("scene_update: unknown action '{}', normalizing to 'move'", action)
            data["action"] = "move"
            action = "move"
        if action == "move" and not str(data.get("name", "")).strip():
            errors.append("$.scene_update.name: required when action=move")

    elif block_type == "event":
        action = data.get("action")
        if action not in {"create", "evolve", "resolve", "end"}:
            errors.append(
                "$.event.action: must be one of create/evolve/resolve/end"
            )
        if action == "create" and not str(data.get("name", "")).strip():
            errors.append("$.event.name: required when action=create")
        if action == "evolve" and not (
            str(data.get("event_id", "")).strip()
            or str(data.get("parent_event_id", "")).strip()
        ):
            errors.append(
                "$.event.event_id: event_id or parent_event_id required when action=evolve"
            )
        if action in {"resolve", "end"} and not str(data.get("event_id", "")).strip():
            errors.append("$.event.event_id: required when action=resolve/end")

    return errors


def validate_block_data(
    block_type: str,
    data: Any,
    declaration: "BlockDeclaration | None" = None,
) -> list[str]:
    """Validate block data against plugin schema and built-in constraints."""
    schema = None
    if declaration:
        if isinstance(declaration.schema, dict):
            schema = declaration.schema
        elif declaration.schema_ref:
            # schema_ref is a string path — resolved schemas would be loaded
            # from ManifestLoader.load_schemas() and injected by the caller.
            # If not resolved, fall back to builtin schemas.
            schema = _BUILTIN_BLOCK_SCHEMAS.get(block_type)
        else:
            schema = _BUILTIN_BLOCK_SCHEMAS.get(block_type)
    else:
        schema = _BUILTIN_BLOCK_SCHEMAS.get(block_type)
    errors: list[str] = []
    if isinstance(schema, dict):
        errors.extend(_validate_schema(data, schema))
    errors.extend(_validate_builtin_semantics(block_type, data))
    return errors
