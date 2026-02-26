"""Tests for SchemaRegistry — registration, validation, access control."""
from __future__ import annotations

import pytest

from backend.app.core.schema_registry import SchemaRegistry, ValidationResult


@pytest.fixture
def registry() -> SchemaRegistry:
    r = SchemaRegistry()
    r.register("core-character", {
        "collections": {
            "characters": {
                "type": "kv",
                "scope": "session",
                "schema": {
                    "name": {"type": "string", "required": True},
                    "role": {"type": "enum", "values": ["player", "npc"]},
                    "attributes": {"type": "object"},
                },
            },
            "character-templates": {
                "type": "kv",
                "scope": "project",
            },
        },
    })
    r.register("combat", {
        "collections": {
            "combat-log": {"type": "log", "scope": "session"},
            "active-combat": {"type": "kv", "scope": "session"},
        },
        "shared_reads": ["core-character:characters"],
    })
    return r


# ── Registration ──────────────────────────────────────────────────────────


def test_register_creates_collections(registry: SchemaRegistry):
    meta = registry.get_collection_meta("core-character", "characters")
    assert meta is not None
    assert meta.type == "kv"
    assert meta.scope == "session"
    assert meta.schema is not None


def test_register_no_schema(registry: SchemaRegistry):
    meta = registry.get_collection_meta("core-character", "character-templates")
    assert meta is not None
    assert meta.schema is None


def test_get_all_schemas(registry: SchemaRegistry):
    schemas = registry.get_all_schemas()
    assert "core-character:characters" in schemas
    assert "combat:combat-log" in schemas
    assert schemas["core-character:characters"]["type"] == "kv"


def test_get_plugin_collections(registry: SchemaRegistry):
    cols = registry.get_plugin_collections("combat")
    assert "combat-log" in cols
    assert "active-combat" in cols


def test_register_legacy_keys():
    r = SchemaRegistry()
    r.register_legacy_keys("state", ["characters", "inventories"])
    meta = r.get_collection_meta("state", "characters")
    assert meta is not None
    assert meta.type == "kv"
    assert meta.scope == "session"


# ── Validation ────────────────────────────────────────────────────────────


def test_validate_write_passes(registry: SchemaRegistry):
    result = registry.validate_write("core-character", "characters", {
        "name": "Alice", "role": "player",
    })
    assert result.ok is True
    assert result.errors == []


def test_validate_write_missing_required(registry: SchemaRegistry):
    result = registry.validate_write("core-character", "characters", {
        "role": "player",
    })
    assert result.ok is False
    assert any("name" in e for e in result.errors)


def test_validate_write_bad_enum(registry: SchemaRegistry):
    result = registry.validate_write("core-character", "characters", {
        "name": "Bob", "role": "villain",
    })
    assert result.ok is False
    assert any("role" in e for e in result.errors)


def test_validate_write_bad_type(registry: SchemaRegistry):
    result = registry.validate_write("core-character", "characters", {
        "name": 123,
    })
    assert result.ok is False
    assert any("name" in e for e in result.errors)


def test_validate_write_no_schema_passes(registry: SchemaRegistry):
    result = registry.validate_write("core-character", "character-templates", {
        "anything": "goes",
    })
    assert result.ok is True


def test_validate_write_unknown_collection_passes(registry: SchemaRegistry):
    result = registry.validate_write("unknown-plugin", "unknown-col", {"x": 1})
    assert result.ok is True


def test_validate_write_non_dict_fails(registry: SchemaRegistry):
    result = registry.validate_write("core-character", "characters", "not a dict")
    assert result.ok is False


# ── Access control ────────────────────────────────────────────────────────


def test_access_own_namespace_read(registry: SchemaRegistry):
    assert registry.check_access("combat", "combat", "combat-log", write=False) is True


def test_access_own_namespace_write(registry: SchemaRegistry):
    assert registry.check_access("combat", "combat", "active-combat", write=True) is True


def test_access_shared_read_allowed(registry: SchemaRegistry):
    # combat declared shared_reads: ["core-character:characters"]
    assert registry.check_access("combat", "core-character", "characters", write=False) is True


def test_access_shared_read_write_denied(registry: SchemaRegistry):
    # shared_reads only grants read, not write
    assert registry.check_access("combat", "core-character", "characters", write=True) is False


def test_access_cross_ns_no_grant_denied(registry: SchemaRegistry):
    # core-character has no shared_reads for combat collections
    assert registry.check_access("core-character", "combat", "combat-log", write=False) is False


def test_access_cross_ns_write_always_denied(registry: SchemaRegistry):
    assert registry.check_access("core-character", "combat", "combat-log", write=True) is False


def test_access_unregistered_ns_denied(registry: SchemaRegistry):
    assert registry.check_access("unknown", "combat", "combat-log", write=False) is False
