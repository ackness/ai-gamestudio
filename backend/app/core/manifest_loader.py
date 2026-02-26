"""ManifestLoader: parse and validate plugin manifest.json (schema v1)."""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from backend.app.core.plugin_engine import NAME_RE
from backend.app.core.plugin_hooks import (
    DEFAULT_PLUGIN_HOOK,
    KNOWN_PLUGIN_HOOKS,
    normalize_plugin_hooks,
)
from backend.app.core.plugin_trigger import (
    validate_block_trigger_policy,
    normalize_plugin_trigger_policy,
    validate_plugin_trigger_policy,
)

PLUGIN_SCHEMA_VERSION = "1.0"
MANIFEST_REQUIRED_FIELDS = {
    "schema_version",
    "name",
    "version",
    "type",
    "required",
    "description",
}


@dataclass
class PluginManifest:
    schema_version: str
    name: str
    version: str
    type: str  # "global" | "gameplay"
    required: bool
    description: str
    dependencies: list[str] = field(default_factory=list)
    prompt: dict[str, Any] | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    events: dict[str, Any] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)
    i18n: dict[str, dict[str, str]] = field(default_factory=dict)
    default_enabled: bool = False
    supersedes: list[str] = field(default_factory=list)
    max_triggers: int | None = None  # None = unlimited; per-session trigger limit
    hooks: list[str] = field(default_factory=lambda: [DEFAULT_PLUGIN_HOOK])
    trigger: dict[str, Any] = field(default_factory=lambda: normalize_plugin_trigger_policy(None))


def load_manifest(plugin_dir: pathlib.Path) -> PluginManifest | None:
    """Load and parse a manifest.json from a plugin directory.

    Returns None if manifest.json doesn't exist.
    Raises ValueError if the file exists but is invalid.
    """
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        return None

    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read manifest.json: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in manifest.json: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("manifest.json must be a JSON object")

    errors = validate_manifest(data, plugin_dir.name)
    if errors:
        raise ValueError(
            f"Invalid manifest.json for '{plugin_dir.name}': {'; '.join(errors)}"
        )

    return PluginManifest(
        schema_version=data["schema_version"],
        name=data["name"],
        version=data["version"],
        type=data["type"],
        required=bool(data["required"]),
        description=data["description"],
        dependencies=data.get("dependencies", []),
        prompt=data.get("prompt"),
        capabilities=data.get("capabilities") or {},
        outputs=data.get("outputs") or {},
        events=data.get("events") or {},
        storage=data.get("storage") or {},
        permissions=data.get("permissions") or {},
        extensions=data.get("extensions") or {},
        i18n=data.get("i18n") or {},
        default_enabled=bool(data.get("default_enabled", False)),
        supersedes=data.get("supersedes") or [],
        max_triggers=data.get("max_triggers"),
        hooks=normalize_plugin_hooks(data.get("hooks")),
        trigger=normalize_plugin_trigger_policy(data.get("trigger")),
    )


def validate_manifest(data: dict[str, Any], plugin_dir_name: str) -> list[str]:
    """Validate manifest data against plugin schema v1 rules.

    Returns a list of error strings (empty means valid).
    """
    errors: list[str] = []

    # Check required fields
    for field_name in MANIFEST_REQUIRED_FIELDS:
        if field_name not in data:
            errors.append(f"Missing required field: {field_name}")

    if errors:
        return errors  # Can't continue if required fields missing

    # schema_version must match the current schema
    if data.get("schema_version") != PLUGIN_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be '{PLUGIN_SCHEMA_VERSION}', got '{data.get('schema_version')}'"
        )

    # name must match directory
    if data.get("name") != plugin_dir_name:
        errors.append(
            f"name '{data.get('name')}' does not match directory '{plugin_dir_name}'"
        )

    # name format validation
    name = data.get("name", "")
    if name and not NAME_RE.match(name):
        errors.append(
            f"name '{name}' must be lowercase alphanumeric + hyphens, "
            "not starting/ending with hyphen"
        )

    # type validation
    if data.get("type") not in ("global", "gameplay"):
        errors.append(f"type must be 'global' or 'gameplay', got '{data.get('type')}'")

    # required must be boolean
    if not isinstance(data.get("required"), bool):
        errors.append("required must be a boolean")

    # hooks are optional but must be a non-empty array of known hook names when provided
    hooks = data.get("hooks")
    if hooks is not None:
        if not isinstance(hooks, list):
            errors.append("hooks must be an array")
        else:
            normalized = normalize_plugin_hooks(hooks, default_hooks=[])
            if not normalized:
                errors.append("hooks must contain at least one hook name")
            else:
                unknown = [h for h in normalized if h not in KNOWN_PLUGIN_HOOKS]
                if unknown:
                    errors.append(
                        "hooks contains unknown values: " + ", ".join(sorted(set(unknown)))
                    )

    errors.extend(validate_plugin_trigger_policy(data.get("trigger")))

    # Validate optional output-level trigger/instruction-file declarations.
    outputs = data.get("outputs")
    if outputs is not None:
        if not isinstance(outputs, dict):
            errors.append("outputs must be an object")
        else:
            for output_type, output_cfg in outputs.items():
                if not isinstance(output_cfg, dict):
                    continue
                output_path = f"outputs.{output_type}"
                errors.extend(
                    validate_block_trigger_policy(
                        output_cfg.get("trigger"),
                        path=f"{output_path}.trigger",
                    )
                )
                if "instruction_file" in output_cfg:
                    rel = str(output_cfg.get("instruction_file") or "").strip()
                    if not rel:
                        errors.append(f"{output_path}.instruction_file must be a non-empty string")

    # Validate optional agent prompt module config.
    extensions = data.get("extensions")
    if isinstance(extensions, dict) and "agent_prompt" in extensions:
        ap = extensions.get("agent_prompt")
        if not isinstance(ap, dict):
            errors.append("extensions.agent_prompt must be an object")
        else:
            base_file = ap.get("base_file")
            if base_file is not None and not str(base_file).strip():
                errors.append("extensions.agent_prompt.base_file must be a non-empty string")
            for key in ("output_files", "tool_files"):
                mapping = ap.get(key)
                if mapping is None:
                    continue
                if not isinstance(mapping, dict):
                    errors.append(f"extensions.agent_prompt.{key} must be an object")
                    continue
                for name, rel in mapping.items():
                    if not str(name or "").strip():
                        errors.append(f"extensions.agent_prompt.{key} keys must be non-empty strings")
                        continue
                    if not str(rel or "").strip():
                        errors.append(
                            f"extensions.agent_prompt.{key}.{name} must be a non-empty string"
                        )

    # Validate storage config (collections / shared_reads)
    storage = data.get("storage")
    if isinstance(storage, dict):
        collections = storage.get("collections")
        if collections is not None:
            if not isinstance(collections, dict):
                errors.append("storage.collections must be an object")
            else:
                _VALID_COL_TYPES = {"kv", "log", "graph"}
                _VALID_COL_SCOPES = {"session", "project"}
                for col_name, col_def in collections.items():
                    prefix = f"storage.collections.{col_name}"
                    if not isinstance(col_def, dict):
                        errors.append(f"{prefix} must be an object")
                        continue
                    col_type = col_def.get("type", "kv")
                    if col_type not in _VALID_COL_TYPES:
                        errors.append(
                            f"{prefix}.type must be one of {sorted(_VALID_COL_TYPES)}, got '{col_type}'"
                        )
                    col_scope = col_def.get("scope", "session")
                    if col_scope not in _VALID_COL_SCOPES:
                        errors.append(
                            f"{prefix}.scope must be one of {sorted(_VALID_COL_SCOPES)}, got '{col_scope}'"
                        )
                    col_schema = col_def.get("schema")
                    if col_schema is not None and not isinstance(col_schema, dict):
                        errors.append(f"{prefix}.schema must be an object")

        shared_reads = storage.get("shared_reads")
        if shared_reads is not None:
            if not isinstance(shared_reads, list):
                errors.append("storage.shared_reads must be an array")
            else:
                for i, sr in enumerate(shared_reads):
                    if not isinstance(sr, str) or ":" not in sr:
                        errors.append(
                            f"storage.shared_reads[{i}] must be a 'ns:collection' string"
                        )

    return errors


def manifest_to_metadata(manifest: PluginManifest) -> dict[str, Any]:
    """Convert a PluginManifest into the runtime metadata shape."""
    metadata: dict[str, Any] = {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "type": manifest.type,
        "required": manifest.required,
        "dependencies": manifest.dependencies,
    }

    # Prompt config
    if manifest.prompt:
        metadata["prompt"] = manifest.prompt

    # Capabilities — pass through for plugin_use dispatch
    if manifest.capabilities:
        metadata["capabilities"] = manifest.capabilities

    # Outputs — pass through as-is.
    if manifest.outputs:
        metadata["outputs"] = manifest.outputs

    # Events — pass through
    if manifest.events:
        metadata["events"] = manifest.events

    # Storage — pass through
    if manifest.storage:
        metadata["storage"] = manifest.storage

    # Extensions — runtime settings are normalized into fields dict.
    if manifest.extensions:
        extensions = dict(manifest.extensions)
        rt = extensions.get("runtime_settings")
        if isinstance(rt, dict):
            settings_list = rt.get("settings")
            if isinstance(settings_list, list):
                # Convert array [{key: "pacing", type: "enum", ...}]
                # to dict {"pacing": {type: "enum", ...}}
                fields: dict[str, Any] = {}
                for setting in settings_list:
                    if isinstance(setting, dict) and "key" in setting:
                        key = setting["key"]
                        field_data = {
                            k: v for k, v in setting.items() if k != "key"
                        }
                        fields[key] = field_data
                extensions["runtime_settings"] = {"fields": fields}
        metadata["extensions"] = extensions

    # i18n — localized display names and descriptions
    if manifest.i18n:
        metadata["i18n"] = manifest.i18n

    # default_enabled and supersedes — pass through for plugin_service
    if manifest.default_enabled:
        metadata["default_enabled"] = manifest.default_enabled
    if manifest.supersedes:
        metadata["supersedes"] = manifest.supersedes
    if manifest.max_triggers is not None:
        metadata["max_triggers"] = manifest.max_triggers
    metadata["hooks"] = list(manifest.hooks or [DEFAULT_PLUGIN_HOOK])
    metadata["trigger"] = normalize_plugin_trigger_policy(manifest.trigger)

    return metadata


def load_schemas(plugin_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Load schema files from a plugin's schemas/ directory.

    Strategy:
    1. Index-first: load schemas/index.yaml or schemas/index.json
    2. Scan-fallback: scan schemas/blocks/, schemas/ui/, schemas/capabilities/

    Returns a dict mapping schema name to parsed schema dict.
    """
    schemas_dir = plugin_dir / "schemas"
    if not schemas_dir.is_dir():
        return {}

    schemas: dict[str, dict[str, Any]] = {}

    # Try index file first
    index = _try_load_index(schemas_dir)
    if index is not None:
        for category, entries in index.items():
            if not isinstance(entries, dict):
                continue
            for schema_name, schema_path in entries.items():
                if not isinstance(schema_path, str):
                    continue
                full_path = plugin_dir / schema_path
                parsed = _load_schema_file(full_path)
                if parsed is not None:
                    schemas[schema_name] = parsed
        return schemas

    # Scan fallback
    for subdir in ("blocks", "ui", "capabilities"):
        scan_dir = schemas_dir / subdir
        if not scan_dir.is_dir():
            continue
        for file_path in sorted(scan_dir.iterdir()):
            if file_path.suffix in (".json", ".yaml", ".yml"):
                schema_name = file_path.stem
                parsed = _load_schema_file(file_path)
                if parsed is not None:
                    if schema_name in schemas:
                        logger.warning(
                            "Schema name conflict: '{}' already loaded, skipping {}",
                            schema_name,
                            file_path,
                        )
                    else:
                        schemas[schema_name] = parsed

    return schemas


def _try_load_index(schemas_dir: pathlib.Path) -> dict[str, Any] | None:
    """Try to load schemas/index.yaml or schemas/index.json."""
    for name in ("index.yaml", "index.yml", "index.json"):
        index_path = schemas_dir / name
        if index_path.is_file():
            return _load_schema_file(index_path)
    return None


def _load_schema_file(file_path: pathlib.Path) -> dict[str, Any] | None:
    """Load a JSON or YAML schema file."""
    if not file_path.is_file():
        logger.warning("Schema file not found: {}", file_path)
        return None

    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Cannot read schema file: {}", file_path)
        return None

    try:
        if file_path.suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                logger.warning("PyYAML not installed, cannot load {}", file_path)
                return None
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
    except Exception:
        logger.warning("Failed to parse schema file: {}", file_path)
        return None

    if not isinstance(data, dict):
        logger.warning("Schema file must be an object: {}", file_path)
        return None

    return data
