"""SchemaRegistry — plugin storage schema registration, validation, and access control.

Plugins declare their storage collections in manifest.json under `storage.collections`.
At load time, PluginEngine calls `registry.register(plugin_name, storage_config)` to
register each plugin's collections, schemas, and shared_reads.

Write operations are validated against registered schemas (if any).
Cross-plugin access is controlled: own collections are read/write, shared_reads are
read-only, everything else is denied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class CollectionMeta:
    """Metadata for a single registered collection."""

    owner: str  # plugin namespace that owns this collection
    type: str  # "kv" | "log" | "graph"
    scope: str  # "session" | "project"
    schema: dict | None = None  # optional JSON-Schema-like validation
    indexes: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


class SchemaRegistry:
    """Manages plugin storage schema registration, validation, and access control."""

    def __init__(self) -> None:
        # ns -> collection_name -> CollectionMeta
        self._collections: dict[str, dict[str, CollectionMeta]] = {}
        # ns -> set of "target_ns:collection" strings (read-only access)
        self._shared_reads: dict[str, set[str]] = {}

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, plugin_name: str, storage_config: dict) -> None:
        """Register a plugin's storage collections and shared_reads.

        Called by PluginEngine during plugin loading.
        """
        collections = storage_config.get("collections", {})
        plugin_cols: dict[str, CollectionMeta] = {}

        for col_name, col_def in collections.items():
            meta = CollectionMeta(
                owner=plugin_name,
                type=col_def.get("type", "kv"),
                scope=col_def.get("scope", "session"),
                schema=col_def.get("schema"),
                indexes=col_def.get("indexes", []),
            )
            plugin_cols[col_name] = meta

        self._collections[plugin_name] = plugin_cols

        # Parse shared_reads: list of "ns:collection" strings
        shared = storage_config.get("shared_reads", [])
        self._shared_reads[plugin_name] = set(shared)

        logger.debug(
            "SchemaRegistry: registered {} collections for '{}', shared_reads={}",
            len(plugin_cols), plugin_name, len(shared),
        )

    # ── Backward compat: convert legacy storage.keys to collections ───────

    def register_legacy_keys(self, plugin_name: str, keys: list[str]) -> None:
        """Auto-register legacy `storage.keys` as KV session collections."""
        plugin_cols: dict[str, CollectionMeta] = {}
        for key in keys:
            plugin_cols[key] = CollectionMeta(
                owner=plugin_name, type="kv", scope="session",
            )
        self._collections[plugin_name] = plugin_cols
        self._shared_reads.setdefault(plugin_name, set())

    # ── Validation ────────────────────────────────────────────────────────

    def validate_write(self, ns: str, collection: str, data: Any) -> ValidationResult:
        """Validate data against the registered schema for ns:collection.

        Returns ok=True if no schema is registered (permissive by default).
        """
        meta = self.get_collection_meta(ns, collection)
        if not meta or not meta.schema:
            return ValidationResult(ok=True)

        errors = self._check_schema(meta.schema, data)
        return ValidationResult(ok=len(errors) == 0, errors=errors)

    def _check_schema(self, schema: dict, data: Any) -> list[str]:
        """Lightweight schema validation (required fields + type checks)."""
        errors: list[str] = []
        if not isinstance(data, dict):
            return [f"expected object, got {type(data).__name__}"]

        for field_name, field_def in schema.items():
            if not isinstance(field_def, dict):
                continue
            required = field_def.get("required", False)
            if required and field_name not in data:
                errors.append(f"missing required field '{field_name}'")
                continue
            if field_name not in data:
                continue
            val = data[field_name]
            expected_type = field_def.get("type")
            if expected_type and not self._type_ok(expected_type, val):
                errors.append(
                    f"field '{field_name}': expected {expected_type}, "
                    f"got {type(val).__name__}"
                )
            if expected_type == "enum":
                allowed = field_def.get("values", [])
                if allowed and val not in allowed:
                    errors.append(
                        f"field '{field_name}': value '{val}' not in {allowed}"
                    )
        return errors

    @staticmethod
    def _type_ok(expected: str, value: Any) -> bool:
        mapping = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "object": dict,
            "array": list,
            "enum": str,  # enum values are strings
        }
        py_type = mapping.get(expected)
        if py_type is None:
            return True  # unknown type → skip
        return isinstance(value, py_type)

    # ── Access control ────────────────────────────────────────────────────

    def check_access(
        self, caller_ns: str, target_ns: str, collection: str, *, write: bool = False,
    ) -> bool:
        """Check if caller_ns can access target_ns:collection.

        Rules:
        - Own collections: read + write
        - shared_reads grant: read only
        - Everything else: denied
        """
        # Own namespace — always allowed
        if caller_ns == target_ns:
            return True

        # Write to another namespace — always denied
        if write:
            return False

        # Read from another namespace — check shared_reads
        shared = self._shared_reads.get(caller_ns, set())
        return f"{target_ns}:{collection}" in shared

    # ── Query ─────────────────────────────────────────────────────────────

    def get_collection_meta(self, ns: str, collection: str) -> CollectionMeta | None:
        """Get metadata for a specific collection."""
        cols = self._collections.get(ns, {})
        return cols.get(collection)

    def get_all_schemas(self) -> dict:
        """Return all registered schemas, keyed by ns:collection."""
        result: dict[str, Any] = {}
        for ns, cols in self._collections.items():
            for col_name, meta in cols.items():
                key = f"{ns}:{col_name}"
                result[key] = {
                    "owner": meta.owner,
                    "type": meta.type,
                    "scope": meta.scope,
                    "schema": meta.schema,
                    "indexes": meta.indexes,
                }
        return result

    def get_plugin_collections(self, plugin_name: str) -> dict[str, CollectionMeta]:
        """Return all collections registered by a specific plugin."""
        return dict(self._collections.get(plugin_name, {}))
