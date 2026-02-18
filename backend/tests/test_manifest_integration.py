"""Integration tests for V2 manifest-based plugin system."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.core.plugin_engine import PluginEngine

PLUGINS_DIR = "plugins"

ALL_PLUGINS = [
    "archive",
    "auto-guide",
    "character",
    "choices",
    "core-blocks",
    "database",
    "dice-roll",
    "memory",
    "story-image",
]


@pytest.fixture
def engine():
    PluginEngine.clear_cache()
    return PluginEngine()


class TestManifestIntegration:
    """All 9 builtin plugins load from manifest.json correctly."""

    def test_all_plugins_discoverable(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        names = {p["name"] for p in plugins}
        for name in ALL_PLUGINS:
            assert name in names, f"Plugin '{name}' not discovered"

    def test_all_plugins_have_manifest_source(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        for p in plugins:
            assert p["manifest_source"] == "manifest", (
                f"Plugin '{p['name']}' has manifest_source='{p['manifest_source']}'"
            )

    def test_all_plugins_validate_clean(self, engine: PluginEngine):
        results = engine.validate(PLUGINS_DIR)
        for r in results:
            assert r["errors"] == [], (
                f"Plugin '{r['plugin']}' has validation errors: {r['errors']}"
            )

    def test_manifest_json_files_exist(self):
        for name in ALL_PLUGINS:
            manifest = Path(PLUGINS_DIR) / name / "manifest.json"
            assert manifest.is_file(), f"Missing manifest.json for '{name}'"

    def test_manifest_json_valid_json(self):
        for name in ALL_PLUGINS:
            manifest = Path(PLUGINS_DIR) / name / "manifest.json"
            data = json.loads(manifest.read_text())
            assert data["schema_version"] == "2.0"
            assert data["name"] == name

    def test_discover_includes_capabilities(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        dice_roll = next(p for p in plugins if p["name"] == "dice-roll")
        assert "dice.roll" in dice_roll["capabilities"]

    def test_discover_includes_version(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        for p in plugins:
            assert p["version"], f"Plugin '{p['name']}' has no version"


class TestPromptInjectionConsistency:
    """Prompt injections produce same positions/priorities as before."""

    def test_database_injects_at_world_state(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(
            ["database"], context={}, plugins_dir=PLUGINS_DIR
        )
        assert len(injections) >= 1
        ws = [i for i in injections if i["position"] == "world-state"]
        assert len(ws) == 1
        assert ws[0]["priority"] == 100

    def test_character_injects_at_character(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(
            ["character"],
            context={
                "player": {"name": "Hero", "description": "Brave"},
                "npcs": [],
            },
            plugins_dir=PLUGINS_DIR,
        )
        char = [i for i in injections if i["position"] == "character"]
        assert len(char) == 1
        assert char[0]["priority"] == 10

    def test_core_blocks_injects_at_system(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(
            ["core-blocks"], context={}, plugins_dir=PLUGINS_DIR
        )
        sys_inj = [i for i in injections if i["position"] == "system"]
        assert len(sys_inj) == 1
        assert sys_inj[0]["priority"] == 95


class TestBlockDeclarationConsistency:
    """Block declarations from manifest match expected types."""

    def test_core_blocks_declares_expected_types(self, engine: PluginEngine):
        decls = engine.get_block_declarations(["core-blocks"], PLUGINS_DIR)
        expected = {"state_update", "character_sheet", "scene_update", "event", "notification"}
        assert expected == set(decls.keys())

    def test_choices_declares_choices(self, engine: PluginEngine):
        decls = engine.get_block_declarations(["choices"], PLUGINS_DIR)
        assert "choices" in decls
        assert decls["choices"].requires_response is True

    def test_dice_roll_declares_dice_result(self, engine: PluginEngine):
        decls = engine.get_block_declarations(["dice-roll"], PLUGINS_DIR)
        assert "dice_result" in decls
        assert decls["dice_result"].schema is not None
        assert "dice" in decls["dice_result"].schema.get("properties", {})

    def test_story_image_declares_story_image(self, engine: PluginEngine):
        decls = engine.get_block_declarations(["story-image"], PLUGINS_DIR)
        assert "story_image" in decls
        assert decls["story_image"].requires_response is True


class TestDependencyResolutionUnchanged:
    """Dependency ordering is preserved from V1."""

    def test_database_before_character(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(
            ["character", "database", "core-blocks"], PLUGINS_DIR
        )
        assert ordered.index("database") < ordered.index("character")
        assert ordered.index("core-blocks") < ordered.index("character")

    def test_database_before_memory(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(
            ["memory", "database"], PLUGINS_DIR
        )
        assert ordered.index("database") < ordered.index("memory")


class TestV1FallbackStillWorks:
    """V1 plugins without manifest.json still load correctly."""

    def test_v1_plugin_loads(self, engine: PluginEngine, tmp_path: Path):
        import textwrap

        plugin_dir = tmp_path / "v1-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "PLUGIN.md").write_text(
            textwrap.dedent("""\
                ---
                name: v1-plugin
                description: A V1 plugin
                type: gameplay
                required: false
                ---
                # V1 Plugin
            """)
        )
        data = engine.load("v1-plugin", str(tmp_path))
        assert data is not None
        assert data["manifest_source"] == "v1_fallback"
        assert data["manifest"] is None
        assert data["metadata"]["type"] == "gameplay"

    def test_v1_plugin_discovered(self, engine: PluginEngine, tmp_path: Path):
        import textwrap

        plugin_dir = tmp_path / "v1-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "PLUGIN.md").write_text(
            textwrap.dedent("""\
                ---
                name: v1-plugin
                description: A V1 plugin
                type: gameplay
                required: false
                ---
                # V1 Plugin
            """)
        )
        plugins = engine.discover(str(tmp_path))
        assert len(plugins) == 1
        assert plugins[0]["manifest_source"] == "v1_fallback"


class TestCapabilityDeclarations:
    """Capability declarations extracted from manifests."""

    def test_dice_roll_capability(self, engine: PluginEngine):
        caps = engine.get_capability_declarations(["dice-roll"], PLUGINS_DIR)
        assert len(caps) == 1
        assert caps[0]["capability_id"] == "dice.roll"
        assert caps[0]["plugin"] == "dice-roll"
        assert caps[0]["result_block_type"] == "dice_result"

    def test_plugins_without_capabilities_return_empty(self, engine: PluginEngine):
        caps = engine.get_capability_declarations(["database"], PLUGINS_DIR)
        assert caps == []
