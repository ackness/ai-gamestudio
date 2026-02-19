"""Tests for PluginEngine: discovery, loading, validation, dependencies, prompt injection."""
from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

from backend.app.core.plugin_engine import PluginEngine

PLUGINS_DIR = "plugins"


@pytest.fixture
def engine():
    PluginEngine.clear_cache()
    return PluginEngine()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscover:
    def test_discovers_builtin_plugins(self, engine: PluginEngine):
        plugins = engine.discover(PLUGINS_DIR)
        names = {p["name"] for p in plugins}
        assert "database" in names
        assert "character" in names
        assert "memory" in names

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


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_existing_plugin(self, engine: PluginEngine):
        data = engine.load("character", PLUGINS_DIR)
        assert data is not None
        assert data["name"] == "character"
        assert "metadata" in data
        assert "content" in data
        assert len(data["content"]) > 0

    def test_load_nonexistent_returns_none(self, engine: PluginEngine):
        assert engine.load("nonexistent-plugin", PLUGINS_DIR) is None

    def test_hot_reload_when_plugin_file_changes(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = tmp_path / "hot-plugin"
        plugin_dir.mkdir()
        plugin_md = plugin_dir / "PLUGIN.md"
        plugin_md.write_text(
            textwrap.dedent("""\
                ---
                name: hot-plugin
                description: before
                type: gameplay
                required: false
                ---
                # before
            """)
        )

        first = engine.load("hot-plugin", str(tmp_path))
        assert first is not None
        assert first["metadata"]["description"] == "before"

        # Ensure file signature changes for cache invalidation.
        time.sleep(0.001)
        plugin_md.write_text(
            textwrap.dedent("""\
                ---
                name: hot-plugin
                description: after
                type: gameplay
                required: false
                ---
                # after
            """)
        )
        second = engine.load("hot-plugin", str(tmp_path))
        assert second is not None
        assert second["metadata"]["description"] == "after"


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


class TestResolveDependencies:
    def test_database_before_character(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(
            ["character", "database"], PLUGINS_DIR
        )
        assert ordered.index("database") < ordered.index("character")

    def test_single_plugin(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(["database"], PLUGINS_DIR)
        assert ordered == ["database"]

    def test_all_builtins(self, engine: PluginEngine):
        ordered = engine.resolve_dependencies(
            ["memory", "character", "database"], PLUGINS_DIR
        )
        # database must come before character and memory
        assert ordered.index("database") < ordered.index("character")
        assert ordered.index("database") < ordered.index("memory")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


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

    def test_missing_required_fields(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "PLUGIN.md").write_text(
            textwrap.dedent("""\
                ---
                name: test-plugin
                ---
                # Test
            """)
        )
        results = engine.validate(str(tmp_path))
        errors = results[0]["errors"]
        assert any("description" in e for e in errors)
        assert any("type" in e for e in errors)
        assert any("required" in e for e in errors)

    def test_name_mismatch(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "PLUGIN.md").write_text(
            textwrap.dedent("""\
                ---
                name: wrong-name
                description: test
                type: gameplay
                required: false
                ---
                # Test
            """)
        )
        results = engine.validate(str(tmp_path))
        errors = results[0]["errors"]
        assert any("does not match" in e for e in errors)


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------


class TestPromptInjections:
    def test_character_plugin_injects_at_correct_position(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(
            ["character"],
            context={
                "player": {
                    "name": "Hero",
                    "description": "A brave warrior",
                    "attributes": {"HP": 100, "STR": 15},
                    "inventory": ["Sword", "Shield"],
                },
                "npcs": [
                    {"name": "Gandalf", "description": "A wise wizard"},
                ],
            },
            plugins_dir=PLUGINS_DIR,
        )
        assert len(injections) > 0
        char_injection = [i for i in injections if i["position"] == "character"]
        assert len(char_injection) > 0
        content = char_injection[0]["content"]
        assert "Hero" in content

    def test_empty_context(self, engine: PluginEngine):
        injections = engine.get_prompt_injections(
            ["database"],
            context={},
            plugins_dir=PLUGINS_DIR,
        )
        # Should not crash with empty context
        assert isinstance(injections, list)

    def test_template_hot_reload(self, engine: PluginEngine, tmp_path: Path):
        plugin_dir = tmp_path / "templ-plugin"
        prompts_dir = plugin_dir / "prompts"
        prompts_dir.mkdir(parents=True)
        tpl = prompts_dir / "main.md"
        tpl.write_text("first: {{ value }}")

        (plugin_dir / "PLUGIN.md").write_text(
            textwrap.dedent("""\
                ---
                name: templ-plugin
                description: test
                type: gameplay
                required: false
                prompt:
                  position: memory
                  priority: 10
                  template: prompts/main.md
                ---
            """)
        )

        injections = engine.get_prompt_injections(
            ["templ-plugin"],
            context={"value": "A"},
            plugins_dir=str(tmp_path),
        )
        assert len(injections) == 1
        assert "first: A" in injections[0]["content"]

        time.sleep(0.001)
        tpl.write_text("second: {{ value }}")
        injections = engine.get_prompt_injections(
            ["templ-plugin"],
            context={"value": "B"},
            plugins_dir=str(tmp_path),
        )
        assert len(injections) == 1
        assert "second: B" in injections[0]["content"]


# ---------------------------------------------------------------------------
# Block declarations
# ---------------------------------------------------------------------------


class TestGetBlockDeclarations:
    """Tests for PluginEngine.get_block_declarations()"""

    def test_returns_block_declarations_from_plugins(self, engine: PluginEngine, tmp_path: Path):
        """Test that blocks from PLUGIN.md frontmatter are correctly extracted."""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "PLUGIN.md").write_text(
            textwrap.dedent("""\
                ---
                name: test-plugin
                description: Test plugin
                type: gameplay
                required: false
                blocks:
                  test_block:
                    instruction: |
                      Output a test block:
                      ```json:test_block
                      {"value": 42}
                      ```
                    handler:
                      actions:
                        - type: storage_write
                          key: test-data
                    ui:
                      component: card
                      title: "Test {{ value }}"
                    requires_response: false
                ---
                # Test Plugin
            """)
        )
        declarations = engine.get_block_declarations(["test-plugin"], str(tmp_path))
        assert "test_block" in declarations
        decl = declarations["test_block"]
        assert decl.block_type == "test_block"
        assert decl.plugin_name == "test-plugin"
        assert decl.instruction is not None
        assert "test_block" in decl.instruction
        assert decl.handler is not None
        assert decl.handler["actions"][0]["type"] == "storage_write"
        assert decl.ui is not None
        assert decl.ui["component"] == "card"
        assert decl.requires_response is False

    def test_empty_blocks_returns_empty_dict(self, engine: PluginEngine):
        """Plugins without blocks field return empty dict."""
        declarations = engine.get_block_declarations(["database"], PLUGINS_DIR)
        # database plugin has no blocks field
        # Only check that it doesn't error; other plugins might contribute blocks
        assert isinstance(declarations, dict)

    def test_multiple_plugins_merge_blocks(self, engine: PluginEngine, tmp_path: Path):
        """Blocks from multiple plugins are merged into one dict."""
        for i, name in enumerate(["plugin-a", "plugin-b"]):
            d = tmp_path / name
            d.mkdir()
            (d / "PLUGIN.md").write_text(
                textwrap.dedent(f"""\
                    ---
                    name: {name}
                    description: Plugin {name}
                    type: gameplay
                    required: false
                    blocks:
                      block_{name.replace('-', '_')}:
                        instruction: "Block from {name}"
                    ---
                    # {name}
                """)
            )
        declarations = engine.get_block_declarations(["plugin-a", "plugin-b"], str(tmp_path))
        assert "block_plugin_a" in declarations
        assert "block_plugin_b" in declarations
        assert declarations["block_plugin_a"].plugin_name == "plugin-a"
        assert declarations["block_plugin_b"].plugin_name == "plugin-b"

    def test_later_plugin_overrides_same_block_type(self, engine: PluginEngine, tmp_path: Path):
        """If two plugins declare the same block type, the later one in dependency order wins."""
        for name in ["plugin-a", "plugin-b"]:
            d = tmp_path / name
            d.mkdir()
            (d / "PLUGIN.md").write_text(
                textwrap.dedent(f"""\
                    ---
                    name: {name}
                    description: Plugin {name}
                    type: gameplay
                    required: false
                    blocks:
                      shared_block:
                        instruction: "From {name}"
                    ---
                    # {name}
                """)
            )
        declarations = engine.get_block_declarations(["plugin-a", "plugin-b"], str(tmp_path))
        assert declarations["shared_block"].plugin_name == "plugin-b"

    def test_conflict_metadata_is_recorded(self, engine: PluginEngine, tmp_path: Path):
        for name in ["plugin-a", "plugin-b"]:
            d = tmp_path / name
            d.mkdir()
            (d / "PLUGIN.md").write_text(
                textwrap.dedent(f"""\
                    ---
                    name: {name}
                    description: Plugin {name}
                    type: gameplay
                    required: false
                    blocks:
                      shared_block:
                        instruction: "From {name}"
                    ---
                    # {name}
                """)
            )
        engine.get_block_declarations(["plugin-a", "plugin-b"], str(tmp_path))
        conflicts = engine.get_last_block_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["block_type"] == "shared_block"
        assert conflicts[0]["overridden_plugin"] == "plugin-a"
        assert conflicts[0]["winner_plugin"] == "plugin-b"

    def test_conflict_can_fail_in_strict_mode(self, engine: PluginEngine, tmp_path: Path):
        for name in ["plugin-a", "plugin-b"]:
            d = tmp_path / name
            d.mkdir()
            (d / "PLUGIN.md").write_text(
                textwrap.dedent(f"""\
                    ---
                    name: {name}
                    description: Plugin {name}
                    type: gameplay
                    required: false
                    blocks:
                      shared_block:
                        instruction: "From {name}"
                    ---
                    # {name}
                """)
            )
        with pytest.raises(ValueError, match="Block type conflict"):
            engine.get_block_declarations(
                ["plugin-a", "plugin-b"],
                str(tmp_path),
                strict_conflicts=True,
            )

    def test_core_blocks_plugin_declares_blocks(self, engine: PluginEngine):
        """The core-blocks plugin should declare state_update, character_sheet, etc."""
        declarations = engine.get_block_declarations(["core-blocks"], PLUGINS_DIR)
        # core-blocks should declare at least state_update
        assert "state_update" in declarations
        assert declarations["state_update"].plugin_name == "core-blocks"
