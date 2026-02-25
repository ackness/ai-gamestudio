"""Integration tests for manifest-based plugin system (schema v1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.core.plugin_engine import PluginEngine
from backend.tests.constants import CURRENT_PLUGIN_IDS, PLUGINS_DIR


@pytest.fixture
def engine():
    PluginEngine.clear_cache()
    return PluginEngine()


class TestManifestIntegration:
    def test_all_plugins_discoverable(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        names = {p["name"] for p in plugins}
        assert CURRENT_PLUGIN_IDS.issubset(names)

    def test_all_plugins_validate_clean(self, engine: PluginEngine):
        results = engine.validate(PLUGINS_DIR)
        for r in results:
            assert r["errors"] == [], f"Plugin '{r['plugin']}' has validation errors: {r['errors']}"

    def test_manifest_json_files_exist(self):
        for manifest in Path(PLUGINS_DIR).glob("**/manifest.json"):
            assert manifest.is_file()

    def test_manifest_json_valid_json_and_schema(self):
        for manifest in Path(PLUGINS_DIR).glob("**/manifest.json"):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            assert data["schema_version"] == "1.0"
            assert data["name"] == manifest.parent.name

    def test_all_declared_outputs_define_schema(self):
        for manifest in Path(PLUGINS_DIR).glob("**/manifest.json"):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            outputs = data.get("outputs", {})
            if not isinstance(outputs, dict):
                continue
            for output_type, output_cfg in outputs.items():
                assert isinstance(output_cfg, dict), (
                    f"{manifest}: outputs.{output_type} must be an object"
                )
                assert "schema" in output_cfg, (
                    f"{manifest}: outputs.{output_type} must define schema"
                )
                schema = output_cfg.get("schema")
                assert isinstance(schema, (dict, str)), (
                    f"{manifest}: outputs.{output_type}.schema must be object or path"
                )

    def test_discover_includes_capabilities(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        combat = next(p for p in plugins if p["name"] == "combat")
        assert "dice.roll" in combat["capabilities"]

    def test_discover_includes_version(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        for p in plugins:
            assert p["version"], f"Plugin '{p['name']}' has no version"


class TestPromptInjectionConsistency:
    def test_database_injects_at_world_state(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(["database"], context={}, plugins_dir=PLUGINS_DIR)
        ws = [i for i in injections if i["position"] == "world-state"]
        assert len(ws) == 1
        assert ws[0]["priority"] == 100

    def test_state_injects_at_character(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(
            ["state"],
            context={"player": {"name": "Hero", "description": "Brave"}, "npcs": []},
            plugins_dir=PLUGINS_DIR,
        )
        char = [i for i in injections if i["position"] == "character"]
        assert len(char) == 1
        assert char[0]["priority"] == 10

    def test_all_builtin_plugin_templates_render_without_jinja_markers(
        self,
        engine: PluginEngine,
    ):
        all_plugins = sorted(CURRENT_PLUGIN_IDS)
        context = {
            "project": {"id": "proj", "name": "Demo", "description": "test"},
            "player": {
                "id": "player-1",
                "name": "Hero",
                "role": "player",
                "description": "Brave adventurer",
                "attributes": {"hp": 100},
                "inventory": ["sword"],
            },
            "npcs": [{"id": "npc-1", "name": "Guide", "role": "npc"}],
            "characters": [
                {"id": "player-1", "name": "Hero", "role": "player"},
                {"id": "npc-1", "name": "Guide", "role": "npc"},
            ],
            "current_scene": {"id": "scene-1", "name": "Tavern", "description": "Busy and warm"},
            "scene_npcs": [{"character_id": "npc-1", "name": "Guide", "role_in_scene": "host"}],
            "active_events": [
                {
                    "id": "evt-1",
                    "event_type": "quest",
                    "name": "Find the map",
                    "description": "A clue awaits",
                    "status": "active",
                }
            ],
            "world_state": {"project_name": "Demo"},
            "compression_summary": "Earlier the party reached town.",
            "archive": {"has_snapshot": False},
            "memories": [{"timestamp": "t1", "content": "Met the innkeeper"}],
            "story_images": [{"image_id": "img-1", "title": "Tavern", "prompt": "A cozy tavern"}],
            "runtime_settings": {
                "guide": {"guide_mode": "guide"},
                "image": {"emit_mode": "manual"},
                "state": {"narrative_tone": "neutral"},
                "event": {"quest_complexity": "standard", "show_rewards": "preview"},
                "codex": {"codex_detail": "detailed"},
                "social": {"relationship_depth": "rich", "reputation_visibility": "fuzzy"},
            },
            "storage": {
                "flat": {
                    "active-effects": [],
                    "active-quests": [{"id": "q1", "name": "Find map"}],
                    "faction-standings": {},
                },
                "by_plugin": {
                    "codex": {"codex-entries": []},
                    "social": {"npc-relationships": []},
                    "event": {"active-quests": [{"id": "q1", "name": "Find map"}]},
                    "combat": {"active-effects": []},
                },
            },
            "storage_by_plugin": {
                "codex": {"codex-entries": []},
                "social": {"npc-relationships": []},
            },
        }

        injections = engine.get_prompt_injections(all_plugins, context=context, plugins_dir=PLUGINS_DIR)
        assert injections, "expected prompt injections for builtin plugins"
        for injection in injections:
            content = str(injection.get("content", ""))
            assert "{{" not in content
            assert "{%" not in content


class TestBlockDeclarationConsistency:
    def test_state_declares_expected_types(self, engine: PluginEngine):
        decls = engine.get_block_declarations(["state"], PLUGINS_DIR)
        expected = {"state_update", "character_sheet", "scene_update", "notification"}
        assert expected.issubset(set(decls.keys()))

    def test_guide_declares_choices(self, engine: PluginEngine):
        decls = engine.get_block_declarations(["guide"], PLUGINS_DIR)
        assert "choices" in decls
        assert decls["choices"].requires_response is True

    def test_combat_declares_dice_result(self, engine: PluginEngine):
        decls = engine.get_block_declarations(["combat"], PLUGINS_DIR)
        assert "dice_result" in decls
        assert decls["dice_result"].schema is not None
        assert "dice" in decls["dice_result"].schema.get("properties", {})

    def test_image_declares_story_image(self, engine: PluginEngine):
        decls = engine.get_block_declarations(["image"], PLUGINS_DIR)
        assert "story_image" in decls
        assert decls["story_image"].requires_response is True


class TestDependencyResolution:
    def test_database_before_state(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(["state", "database"], PLUGINS_DIR)
        assert ordered.index("database") < ordered.index("state")

    def test_state_before_combat(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(["combat", "state", "database"], PLUGINS_DIR)
        assert ordered.index("database") < ordered.index("state")
        assert ordered.index("state") < ordered.index("combat")

    def test_database_before_memory(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(["memory", "database"], PLUGINS_DIR)
        assert ordered.index("database") < ordered.index("memory")


class TestCapabilityDeclarations:
    def test_combat_dice_roll_capability(self, engine: PluginEngine):
        caps = engine.get_capability_declarations(["combat"], PLUGINS_DIR)
        assert any(
            c["capability_id"] == "dice.roll"
            and c["plugin"] == "combat"
            and c["result_block_type"] == "dice_result"
            for c in caps
        )

    def test_plugins_without_capabilities_return_empty(self, engine: PluginEngine):
        caps = engine.get_capability_declarations(["database"], PLUGINS_DIR)
        assert caps == []
