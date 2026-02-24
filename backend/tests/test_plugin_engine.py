"""Tests for PluginEngine: discovery, loading, validation, dependencies, prompt injection."""
from __future__ import annotations

import json
import textwrap
import time
from pathlib import Path

import pytest

from backend.app.core.plugin_engine import PluginEngine

PLUGINS_DIR = "plugins"
CURRENT_PLUGINS = {
    "database",
    "state",
    "event",
    "memory",
    "guide",
    "codex",
    "image",
    "combat",
    "inventory",
    "social",
}


@pytest.fixture
def engine():
    PluginEngine.clear_cache()
    return PluginEngine()


def _write_plugin(
    root: Path,
    name: str,
    *,
    plugin_md: str = "# plugin",
    blocks: dict | None = None,
    prompt: dict | None = None,
    capabilities: dict | None = None,
) -> Path:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "PLUGIN.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: {name} plugin
            type: gameplay
            required: false
            ---
            {plugin_md}
            """
        )
    )
    manifest = {
        "schema_version": "1.0",
        "name": name,
        "version": "1.0.0",
        "type": "gameplay",
        "required": False,
        "description": f"{name} plugin",
        "dependencies": [],
        "blocks": blocks or {},
        "capabilities": capabilities or {},
    }
    if prompt:
        manifest["prompt"] = prompt
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return plugin_dir


class TestDiscover:
    def test_discovers_current_builtin_plugins(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        names = {p["name"] for p in plugins}
        assert CURRENT_PLUGINS.issubset(names)

    def test_returns_required_metadata_fields(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        for p in plugins:
            assert "name" in p
            assert "description" in p
            assert "type" in p
            assert "path" in p

    def test_empty_dir_returns_empty(self, engine: PluginEngine, tmp_path: Path):
        assert engine.discover(str(tmp_path)) == []

    def test_nonexistent_dir_returns_empty(self, engine: PluginEngine):
        assert engine.discover("/nonexistent/path") == []

    def test_marks_plugins_with_script_capabilities(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        by_name = {p["name"]: p for p in plugins}
        assert by_name["combat"]["has_script_capability"] is True


class TestLoad:
    def test_load_existing_plugin(self, engine: PluginEngine):
        data = engine.load("state", PLUGINS_DIR)
        assert data is not None
        assert data["name"] == "state"
        assert "metadata" in data
        assert "content" in data
        assert len(data["content"]) > 0
        assert data["manifest"] is not None

    def test_load_nonexistent_returns_none(self, engine: PluginEngine):
        assert engine.load("nonexistent-plugin", PLUGINS_DIR) is None

    def test_load_requires_manifest(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = tmp_path / "no-manifest"
        plugin_dir.mkdir()
        (plugin_dir / "PLUGIN.md").write_text(
            "---\nname: no-manifest\ndescription: test\ntype: gameplay\nrequired: false\n---\n# Test\n"
        )
        assert engine.load("no-manifest", str(tmp_path)) is None

    def test_hot_reload_when_plugin_file_changes(self, engine: PluginEngine, tmp_path: Path):
        _write_plugin(tmp_path, "hot-plugin", plugin_md="# before")
        first = engine.load("hot-plugin", str(tmp_path))
        assert first is not None
        assert "before" in first["content"]

        time.sleep(0.001)
        (tmp_path / "hot-plugin" / "PLUGIN.md").write_text(
            "---\nname: hot-plugin\ndescription: hot-plugin plugin\ntype: gameplay\nrequired: false\n---\n# after\n"
        )
        second = engine.load("hot-plugin", str(tmp_path))
        assert second is not None
        assert "after" in second["content"]


class TestResolveDependencies:
    def test_database_before_state(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(["state", "database"], PLUGINS_DIR)
        assert ordered.index("database") < ordered.index("state")

    def test_state_before_combat(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(["combat", "state", "database"], PLUGINS_DIR)
        assert ordered.index("state") < ordered.index("combat")
        assert ordered.index("database") < ordered.index("state")

    def test_single_plugin(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(["database"], PLUGINS_DIR)
        assert ordered == ["database"]


class TestValidate:
    def test_builtin_plugins_pass(self, engine: PluginEngine):
        results = engine.validate(PLUGINS_DIR)
        for r in results:
            assert r["errors"] == [], f"Plugin {r['plugin']} has errors: {r['errors']}"

    def test_missing_plugin_md(self, engine: PluginEngine, tmp_path: Path):
        (tmp_path / "bad-plugin").mkdir()
        results = engine.validate(str(tmp_path))
        assert len(results) == 1
        assert "Missing PLUGIN.md" in results[0]["errors"]

    def test_missing_manifest_json(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = tmp_path / "bad-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "PLUGIN.md").write_text(
            "---\nname: bad-plugin\ndescription: bad\ntype: gameplay\nrequired: false\n---\n# bad\n"
        )
        results = engine.validate(str(tmp_path))
        assert "Missing manifest.json" in results[0]["errors"]

    def test_validate_rejects_script_path_traversal(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = _write_plugin(
            tmp_path,
            "evil-plugin",
            capabilities={
                "evil.run": {
                    "description": "Escape",
                    "implementation": {"type": "script", "script": "../../etc/passwd"},
                }
            },
        )
        assert plugin_dir.exists()
        results = engine.validate(str(tmp_path))
        errors = results[0]["errors"]
        assert any("escapes plugin directory" in e for e in errors)

    def test_validate_rejects_template_path_traversal(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = _write_plugin(
            tmp_path,
            "evil-tmpl",
            prompt={"position": "system", "priority": 1, "template": "../../../etc/passwd"},
        )
        assert plugin_dir.exists()
        results = engine.validate(str(tmp_path))
        errors = results[0]["errors"]
        assert any("escapes plugin directory" in e for e in errors)


class TestPromptInjections:
    def test_state_plugin_injects_at_character(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(
            ["state"],
            context={
                "player": {"name": "Hero", "description": "A brave warrior"},
                "npcs": [],
            },
            plugins_dir=PLUGINS_DIR,
        )
        assert len(injections) > 0
        char_injection = [i for i in injections if i["position"] == "character"]
        assert len(char_injection) > 0

    def test_database_injects_world_state(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(["database"], context={}, plugins_dir=PLUGINS_DIR)
        assert any(i["position"] == "world-state" for i in injections)

    def test_template_hot_reload(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = _write_plugin(
            tmp_path,
            "templ-plugin",
            prompt={"position": "memory", "priority": 10, "template": "prompts/main.md"},
        )
        prompts_dir = plugin_dir / "prompts"
        prompts_dir.mkdir(parents=True)
        tpl = prompts_dir / "main.md"
        tpl.write_text("first: {{ value }}")

        injections = engine.get_prompt_injections(
            ["templ-plugin"], context={"value": "A"}, plugins_dir=str(tmp_path)
        )
        assert len(injections) == 1
        assert "first: A" in injections[0]["content"]

        time.sleep(0.001)
        tpl.write_text("second: {{ value }}")
        injections = engine.get_prompt_injections(
            ["templ-plugin"], context={"value": "B"}, plugins_dir=str(tmp_path)
        )
        assert len(injections) == 1
        assert "second: B" in injections[0]["content"]


class TestGetBlockDeclarations:
    def test_state_declares_core_blocks(self, engine: PluginEngine):
        declarations = engine.get_block_declarations(["state"], PLUGINS_DIR)
        assert "state_update" in declarations
        assert "character_sheet" in declarations
        assert declarations["state_update"].plugin_name == "state"

    def test_guide_declares_choices(self, engine: PluginEngine):
        declarations = engine.get_block_declarations(["guide"], PLUGINS_DIR)
        assert "choices" in declarations
        assert declarations["choices"].requires_response is True

    def test_conflict_metadata_is_recorded(self, engine: PluginEngine, tmp_path: Path):
        _write_plugin(tmp_path, "plugin-a", blocks={"shared_block": {"instruction": "A"}})
        _write_plugin(tmp_path, "plugin-b", blocks={"shared_block": {"instruction": "B"}})

        engine.get_block_declarations(["plugin-a", "plugin-b"], str(tmp_path))
        conflicts = engine.get_last_block_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["block_type"] == "shared_block"
        assert conflicts[0]["overridden_plugin"] == "plugin-a"
        assert conflicts[0]["winner_plugin"] == "plugin-b"

    def test_conflict_can_fail_in_strict_mode(self, engine: PluginEngine, tmp_path: Path):
        _write_plugin(tmp_path, "plugin-a", blocks={"shared_block": {"instruction": "A"}})
        _write_plugin(tmp_path, "plugin-b", blocks={"shared_block": {"instruction": "B"}})

        with pytest.raises(ValueError, match="Block type conflict"):
            engine.get_block_declarations(
                ["plugin-a", "plugin-b"],
                str(tmp_path),
                strict_conflicts=True,
            )
