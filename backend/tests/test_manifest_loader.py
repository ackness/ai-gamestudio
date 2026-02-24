"""Tests for ManifestLoader: load, validate, and convert manifest.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.core.manifest_loader import (
    PluginManifest,
    load_manifest,
    load_schemas,
    manifest_to_metadata,
    validate_manifest,
)


def _write_manifest(plugin_dir: Path, data: dict) -> Path:
    manifest_path = plugin_dir / "manifest.json"
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return manifest_path


def _minimal_manifest(name: str = "test-plugin", **overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "name": name,
        "version": "1.0.0",
        "type": "gameplay",
        "required": False,
        "description": "A test plugin.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_returns_none_when_no_manifest(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        assert load_manifest(plugin_dir) is None

    def test_loads_valid_manifest(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        _write_manifest(plugin_dir, _minimal_manifest())
        manifest = load_manifest(plugin_dir)
        assert manifest is not None
        assert isinstance(manifest, PluginManifest)
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.type == "gameplay"
        assert manifest.required is False

    def test_raises_on_invalid_json(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text("{bad json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_manifest(plugin_dir)

    def test_raises_on_missing_required_fields(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        _write_manifest(plugin_dir, {"schema_version": "1.0"})
        with pytest.raises(ValueError, match="Missing required field"):
            load_manifest(plugin_dir)

    def test_raises_on_wrong_schema_version(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        data = _minimal_manifest()
        data["schema_version"] = "2.0"
        _write_manifest(plugin_dir, data)
        with pytest.raises(ValueError, match="schema_version must be '1.0'"):
            load_manifest(plugin_dir)

    def test_raises_on_name_mismatch(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        data = _minimal_manifest(name="wrong-name")
        _write_manifest(plugin_dir, data)
        with pytest.raises(ValueError, match="does not match directory"):
            load_manifest(plugin_dir)

    def test_loads_full_manifest_with_all_fields(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        data = _minimal_manifest()
        data.update({
            "dependencies": ["core-blocks"],
            "prompt": {"position": "pre-response", "priority": 50},
            "capabilities": {"test.run": {"description": "test"}},
            "blocks": {"test_block": {"instruction": "do something"}},
            "events": {"emit": ["test-done"], "listen": []},
            "storage": {"keys": ["data"]},
            "permissions": {"network": False},
            "extensions": {"custom": {"key": "value"}},
        })
        _write_manifest(plugin_dir, data)
        manifest = load_manifest(plugin_dir)
        assert manifest is not None
        assert manifest.dependencies == ["core-blocks"]
        assert manifest.prompt == {"position": "pre-response", "priority": 50}
        assert "test.run" in manifest.capabilities
        assert "test_block" in manifest.blocks
        assert manifest.events["emit"] == ["test-done"]
        assert manifest.storage["keys"] == ["data"]
        assert manifest.permissions["network"] is False
        assert manifest.extensions["custom"]["key"] == "value"


# ---------------------------------------------------------------------------
# validate_manifest
# ---------------------------------------------------------------------------


class TestValidateManifest:
    def test_valid_manifest_returns_empty(self):
        errors = validate_manifest(_minimal_manifest(), "test-plugin")
        assert errors == []

    def test_missing_required_fields(self):
        errors = validate_manifest({"schema_version": "1.0"}, "test-plugin")
        assert len(errors) > 0
        assert any("Missing required field" in e for e in errors)

    def test_wrong_schema_version(self):
        data = _minimal_manifest()
        data["schema_version"] = "2.0"
        errors = validate_manifest(data, "test-plugin")
        assert any("schema_version" in e for e in errors)

    def test_name_mismatch(self):
        data = _minimal_manifest(name="other-name")
        errors = validate_manifest(data, "test-plugin")
        assert any("does not match" in e for e in errors)

    def test_invalid_name_format(self):
        data = _minimal_manifest(name="BadName")
        errors = validate_manifest(data, "BadName")
        assert any("must be lowercase" in e for e in errors)

    def test_invalid_type(self):
        data = _minimal_manifest()
        data["type"] = "unknown"
        errors = validate_manifest(data, "test-plugin")
        assert any("type must be" in e for e in errors)

    def test_required_not_boolean(self):
        data = _minimal_manifest()
        data["required"] = "yes"
        errors = validate_manifest(data, "test-plugin")
        assert any("boolean" in e for e in errors)


# ---------------------------------------------------------------------------
# manifest_to_metadata
# ---------------------------------------------------------------------------


class TestManifestToMetadata:
    def test_basic_conversion(self):
        manifest = PluginManifest(
            schema_version="1.0",
            name="test-plugin",
            version="1.0.0",
            type="gameplay",
            required=False,
            description="A test plugin.",
            dependencies=["dep-a"],
            prompt={"position": "world-state", "priority": 50},
        )
        meta = manifest_to_metadata(manifest)
        assert meta["name"] == "test-plugin"
        assert meta["version"] == "1.0.0"
        assert meta["type"] == "gameplay"
        assert meta["required"] is False
        assert meta["dependencies"] == ["dep-a"]
        assert meta["prompt"]["position"] == "world-state"

    def test_blocks_pass_through(self):
        manifest = PluginManifest(
            schema_version="1.0",
            name="test-plugin",
            version="1.0.0",
            type="gameplay",
            required=False,
            description="test",
            blocks={"my_block": {"instruction": "do it"}},
        )
        meta = manifest_to_metadata(manifest)
        assert meta["blocks"]["my_block"]["instruction"] == "do it"

    def test_blocks_with_inline_schema(self):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        manifest = PluginManifest(
            schema_version="1.0",
            name="test-plugin",
            version="1.0.0",
            type="gameplay",
            required=False,
            description="test",
            blocks={"my_block": {"schema": schema}},
        )
        meta = manifest_to_metadata(manifest)
        assert meta["blocks"]["my_block"]["schema"] == schema

    def test_blocks_with_schema_path_string(self):
        """Schema as a string path should pass through as-is."""
        manifest = PluginManifest(
            schema_version="1.0",
            name="test-plugin",
            version="1.0.0",
            type="gameplay",
            required=False,
            description="test",
            blocks={"my_block": {"schema": "schemas/blocks/my_block.yaml"}},
        )
        meta = manifest_to_metadata(manifest)
        assert meta["blocks"]["my_block"]["schema"] == "schemas/blocks/my_block.yaml"

    def test_runtime_settings_array_to_dict_conversion(self):
        """Runtime settings array should be normalized to fields dict."""
        manifest = PluginManifest(
            schema_version="1.0",
            name="test-plugin",
            version="1.0.0",
            type="gameplay",
            required=False,
            description="test",
            extensions={
                "runtime_settings": {
                    "settings": [
                        {
                            "key": "pacing",
                            "type": "enum",
                            "default": "balanced",
                            "options": ["slow", "balanced", "fast"],
                            "affects": ["story"],
                        },
                        {
                            "key": "risk_bias",
                            "type": "enum",
                            "default": "balanced",
                            "options": ["safe", "balanced", "dangerous"],
                        },
                    ]
                }
            },
        )
        meta = manifest_to_metadata(manifest)
        rt = meta["extensions"]["runtime_settings"]
        assert "fields" in rt
        assert "settings" not in rt
        assert "pacing" in rt["fields"]
        assert rt["fields"]["pacing"]["type"] == "enum"
        assert rt["fields"]["pacing"]["default"] == "balanced"
        assert "key" not in rt["fields"]["pacing"]  # key stripped
        assert "risk_bias" in rt["fields"]

    def test_extensions_without_runtime_settings_pass_through(self):
        manifest = PluginManifest(
            schema_version="1.0",
            name="test-plugin",
            version="1.0.0",
            type="gameplay",
            required=False,
            description="test",
            extensions={"custom_ext": {"foo": "bar"}},
        )
        meta = manifest_to_metadata(manifest)
        assert meta["extensions"]["custom_ext"]["foo"] == "bar"

    def test_empty_extensions(self):
        manifest = PluginManifest(
            schema_version="1.0",
            name="test-plugin",
            version="1.0.0",
            type="gameplay",
            required=False,
            description="test",
        )
        meta = manifest_to_metadata(manifest)
        assert "extensions" not in meta


# ---------------------------------------------------------------------------
# load_schemas
# ---------------------------------------------------------------------------


class TestLoadSchemas:
    def test_returns_empty_when_no_schemas_dir(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        assert load_schemas(plugin_dir) == {}

    def test_scan_fallback_loads_json(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        blocks_dir = plugin_dir / "schemas" / "blocks"
        blocks_dir.mkdir(parents=True)
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        (blocks_dir / "my_block.json").write_text(json.dumps(schema))
        result = load_schemas(plugin_dir)
        assert "my_block" in result
        assert result["my_block"]["type"] == "object"

    def test_index_loading(self, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        schemas_dir = plugin_dir / "schemas"
        blocks_dir = schemas_dir / "blocks"
        blocks_dir.mkdir(parents=True)
        schema = {"type": "object"}
        (blocks_dir / "test_block.json").write_text(json.dumps(schema))
        index = {"blocks": {"test_block": "schemas/blocks/test_block.json"}}
        (schemas_dir / "index.json").write_text(json.dumps(index))
        result = load_schemas(plugin_dir)
        assert "test_block" in result
