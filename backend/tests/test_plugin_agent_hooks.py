from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import backend.app.services.plugin_agent as plugin_agent
from backend.app.core.plugin_hooks import DEFAULT_PLUGIN_HOOK


class _DummyPluginEngine:
    def discover(self, plugins_dir: str) -> list[dict[str, Any]]:  # noqa: ARG002
        return [{"name": "state"}, {"name": "guide"}]

    def load(self, name: str, plugins_dir: str) -> dict[str, Any] | None:  # noqa: ARG002
        if name == "state":
            return {"content": "state prompt", "metadata": {"hooks": ["pre_model_input"]}}
        if name == "guide":
            return {"content": "guide prompt", "metadata": {"hooks": ["post_model_output"]}}
        return None


@pytest.mark.asyncio
async def test_run_plugin_agent_filters_plugins_by_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _fake_run_one_plugin(**kwargs: Any) -> tuple[list[dict[str, Any]], int, list[str], dict[str, Any]]:
        plugin_info = kwargs["plugin_info"]
        name = str(plugin_info["name"])
        calls.append(name)
        return (
            [{"type": "notification", "data": {"plugin": name}, "_plugin": name}],
            1,
            ["emit"],
            {"plugin": name, "elapsed_ms": 1},
        )

    monkeypatch.setattr(plugin_agent, "_run_one_plugin", _fake_run_one_plugin)

    blocks, summary = await plugin_agent.run_plugin_agent(
        narrative="narrative",
        game_state={},
        enabled_plugins=["state", "guide"],
        session_id="session-1",
        game_db=SimpleNamespace(db=None, session_id="session-1"),
        pe=_DummyPluginEngine(),
        config=SimpleNamespace(model="test-model", source="test"),
        hook="post_model_output",
        plugins_dir="plugins",
    )

    assert calls == ["guide"]
    assert len(blocks) == 1
    assert summary["hook"] == "post_model_output"
    assert summary["plugins_executed"] == ["guide"]
    assert summary["plugins_emitted"] == ["guide"]


class _NoHookPluginEngine:
    def discover(self, plugins_dir: str) -> list[dict[str, Any]]:  # noqa: ARG002
        return [{"name": "legacy"}]

    def load(self, name: str, plugins_dir: str) -> dict[str, Any] | None:  # noqa: ARG002
        if name == "legacy":
            return {"content": "legacy prompt", "metadata": {}}
        return None


@pytest.mark.asyncio
async def test_run_plugin_agent_defaults_missing_hooks_to_default_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_one_plugin(**kwargs: Any) -> tuple[list[dict[str, Any]], int, list[str], dict[str, Any]]:
        name = str(kwargs["plugin_info"]["name"])
        return ([{"type": "notification", "data": {"plugin": name}, "_plugin": name}], 1, [], {})

    monkeypatch.setattr(plugin_agent, "_run_one_plugin", _fake_run_one_plugin)

    blocks, summary = await plugin_agent.run_plugin_agent(
        narrative="narrative",
        game_state={},
        enabled_plugins=["legacy"],
        session_id="session-2",
        game_db=SimpleNamespace(db=None, session_id="session-2"),
        pe=_NoHookPluginEngine(),
        config=SimpleNamespace(model="test-model", source="test"),
        plugins_dir="plugins",
    )

    assert len(blocks) == 1
    assert summary["hook"] == DEFAULT_PLUGIN_HOOK
    assert summary["plugins_executed"] == ["legacy"]


class _TriggerPolicyPluginEngine:
    def discover(self, plugins_dir: str) -> list[dict[str, Any]]:  # noqa: ARG002
        return [{"name": "memory"}, {"name": "image"}]

    def load(self, name: str, plugins_dir: str) -> dict[str, Any] | None:  # noqa: ARG002
        if name == "memory":
            return {
                "content": "memory prompt",
                "metadata": {
                    "hooks": ["post_model_output"],
                    "trigger": {"mode": "interval", "interval_turns": 3},
                },
            }
        if name == "image":
            return {
                "content": "image prompt",
                "metadata": {
                    "hooks": ["post_model_output"],
                    "trigger": {"mode": "manual"},
                },
            }
        return None


@pytest.mark.asyncio
async def test_run_plugin_agent_respects_interval_and_manual_trigger_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _fake_run_one_plugin(**kwargs: Any) -> tuple[list[dict[str, Any]], int, list[str], dict[str, Any]]:
        name = str(kwargs["plugin_info"]["name"])
        calls.append(name)
        return ([{"type": "notification", "data": {"plugin": name}, "_plugin": name}], 1, [], {})

    monkeypatch.setattr(plugin_agent, "_run_one_plugin", _fake_run_one_plugin)

    # turn=2 should skip memory(interval=3) and image(manual)
    blocks, summary = await plugin_agent.run_plugin_agent(
        narrative="narrative",
        game_state={},
        enabled_plugins=["memory", "image"],
        session_id="session-3",
        game_db=SimpleNamespace(db=None, session_id="session-3"),
        pe=_TriggerPolicyPluginEngine(),
        config=SimpleNamespace(model="test-model", source="test"),
        current_turn=2,
        plugins_dir="plugins",
    )
    assert calls == []
    assert blocks == []
    assert summary["plugins_executed"] == []

    # turn=4 should run memory (1,4,7...) but still skip image(manual)
    calls.clear()
    blocks, summary = await plugin_agent.run_plugin_agent(
        narrative="narrative",
        game_state={},
        enabled_plugins=["memory", "image"],
        session_id="session-4",
        game_db=SimpleNamespace(db=None, session_id="session-4"),
        pe=_TriggerPolicyPluginEngine(),
        config=SimpleNamespace(model="test-model", source="test"),
        current_turn=4,
        plugins_dir="plugins",
    )
    assert calls == ["memory"]
    assert len(blocks) == 1
    assert summary["plugins_executed"] == ["memory"]


@pytest.mark.asyncio
async def test_run_plugin_agent_can_override_manual_trigger_from_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _RuntimeMappedPluginEngine:
        def discover(self, plugins_dir: str) -> list[dict[str, Any]]:  # noqa: ARG002
            return [{"name": "image"}]

        def load(self, name: str, plugins_dir: str) -> dict[str, Any] | None:  # noqa: ARG002
            if name != "image":
                return None
            return {
                "content": "image prompt",
                "metadata": {
                    "hooks": ["post_model_output"],
                    "trigger": {
                        "mode": "manual",
                        "mode_setting_key": "emit_mode",
                        "mode_map": {
                            "manual": "manual",
                            "key_moments": "always",
                        },
                    },
                },
            }

    async def _fake_run_one_plugin(**kwargs: Any) -> tuple[list[dict[str, Any]], int, list[str], dict[str, Any]]:
        name = str(kwargs["plugin_info"]["name"])
        calls.append(name)
        return ([{"type": "notification", "data": {"plugin": name}, "_plugin": name}], 1, [], {})

    monkeypatch.setattr(plugin_agent, "_run_one_plugin", _fake_run_one_plugin)

    # Default manual mode: should not run.
    blocks, summary = await plugin_agent.run_plugin_agent(
        narrative="narrative",
        game_state={},
        enabled_plugins=["image"],
        session_id="session-5",
        game_db=SimpleNamespace(db=None, session_id="session-5"),
        pe=_RuntimeMappedPluginEngine(),
        config=SimpleNamespace(model="test-model", source="test"),
        plugins_dir="plugins",
        runtime_settings_by_plugin={"image": {"emit_mode": "manual"}},
    )
    assert calls == []
    assert blocks == []
    assert summary["plugins_executed"] == []

    # Runtime mode switch to key_moments should enable auto run.
    calls.clear()
    blocks, summary = await plugin_agent.run_plugin_agent(
        narrative="narrative",
        game_state={},
        enabled_plugins=["image"],
        session_id="session-6",
        game_db=SimpleNamespace(db=None, session_id="session-6"),
        pe=_RuntimeMappedPluginEngine(),
        config=SimpleNamespace(model="test-model", source="test"),
        plugins_dir="plugins",
        runtime_settings_by_plugin={"image": {"emit_mode": "key_moments"}},
    )
    assert calls == ["image"]
    assert len(blocks) == 1
    assert summary["plugins_executed"] == ["image"]


def test_build_block_instructions_hides_once_blocks_after_consumed() -> None:
    metadata = {
        "outputs": {
            "character_sheet": {
                "instruction": "create character",
                "trigger": {"mode": "once_per_session"},
            },
            "state_update": {"instruction": "update state"},
        }
    }
    instructions = plugin_agent._build_block_instructions(
        metadata,
        plugin_name="state",
        block_trigger_counts={"character_sheet": 1},
        has_player_character=True,
    )
    assert "character_sheet" not in instructions
    assert "state_update" in instructions


def test_build_block_instructions_hides_character_sheet_when_player_exists() -> None:
    metadata = {
        "outputs": {
            "character_sheet": {"instruction": "create character"},
            "state_update": {"instruction": "update state"},
        }
    }
    instructions = plugin_agent._build_block_instructions(
        metadata,
        plugin_name="state",
        block_trigger_counts={},
        has_player_character=True,
    )
    assert "character_sheet" not in instructions
    assert "state_update" in instructions


def test_build_block_instructions_requires_character_sheet_in_creation_phase() -> None:
    metadata = {
        "outputs": {
            "character_sheet": {"instruction": "create character"},
            "state_update": {"instruction": "update state"},
        }
    }
    instructions = plugin_agent._build_block_instructions(
        metadata,
        plugin_name="state",
        block_trigger_counts={},
        has_player_character=False,
        session_phase="character_creation",
    )
    assert "【强约束】" in instructions
    assert "character_sheet.data.name" in instructions


def test_build_block_instructions_includes_emit_template_and_example() -> None:
    metadata = {
        "outputs": {
            "choices": {
                "instruction": "make a choice",
                "schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "type": {"type": "string", "enum": ["single", "multi"]},
                        "options": {
                            "type": "array",
                            "minItems": 2,
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["prompt", "type", "options"],
                },
            }
        }
    }
    instructions = plugin_agent._build_block_instructions(metadata, plugin_name="guide")
    assert "调用模板" in instructions
    assert "简例" in instructions
    assert "\"type\":\"choices\"" in instructions


@pytest.mark.asyncio
async def test_handle_emit_supports_unified_items_shape() -> None:
    class _DB:
        def __init__(self) -> None:
            self.writes: list[tuple[str, str, Any]] = []
            self.logs: list[tuple[str, Any]] = []

        async def kv_set(self, collection: str, key: str, value: Any) -> None:
            self.writes.append((collection, key, value))

        async def log_append(self, collection: str, entry: Any) -> None:
            self.logs.append((collection, entry))

    db = _DB()
    ctx = SimpleNamespace(game_db=db, blocks=[], plugin_name="state", turn_id="turn-1")
    out = await plugin_agent._handle_emit(
        {
            "writes": [{"collection": "characters", "key": "hero", "value": {"hp": 90}}],
            "logs": [{"collection": "combat", "entry": {"round": 1}}],
            "meta": {"group_id": "grp-1"},
            "items": [
                {"type": "notification", "data": {"content": "x"}},
                {"type": "scene_update", "data": {"action": "move", "name": "酒馆"}},
            ],
        },
        ctx,
    )
    assert out["status"] == "ok"
    assert out["written"] == 1
    assert out["emitted"] == ["notification", "scene_update"]
    assert db.writes == [("characters", "hero", {"hp": 90})]
    assert db.logs == [("combat", {"round": 1})]
    assert len(ctx.blocks) == 2
    assert ctx.blocks[0]["type"] == "notification"
    assert ctx.blocks[0]["data"] == {"content": "x"}
    assert ctx.blocks[0]["version"] == "1.0"
    assert ctx.blocks[0]["status"] == "done"
    assert ctx.blocks[0]["meta"]["plugin"] == "state"
    assert ctx.blocks[0]["meta"]["group_id"] == "grp-1"
    assert ctx.blocks[0]["meta"]["turn_id"] == "turn-1"
    assert ctx.blocks[1]["type"] == "scene_update"
    assert ctx.blocks[1]["data"] == {"action": "move", "name": "酒馆"}
    assert isinstance(ctx.blocks[0]["id"], str) and ctx.blocks[0]["id"]
    assert isinstance(ctx.blocks[1]["id"], str) and ctx.blocks[1]["id"]


@pytest.mark.asyncio
async def test_handle_emit_without_items_is_safe_noop() -> None:
    class _DB:
        async def kv_set(self, collection: str, key: str, value: Any) -> None:  # noqa: ARG002
            return None

        async def log_append(self, collection: str, entry: Any) -> None:  # noqa: ARG002
            return None

    ctx = SimpleNamespace(game_db=_DB(), blocks=[], plugin_name="state", turn_id=None)
    out = await plugin_agent._handle_emit({"type": "state_update", "data": {}}, ctx)
    assert out["status"] == "ok"
    assert out["written"] == 0
    assert out["logged"] == 0
    assert "count" not in out
    assert ctx.blocks == []


@pytest.mark.asyncio
async def test_handle_emit_rejects_character_sheet_missing_name() -> None:
    class _DB:
        def __init__(self) -> None:
            self.writes: list[tuple[str, str, Any]] = []

        async def kv_set(self, collection: str, key: str, value: Any) -> None:  # noqa: ARG002
            self.writes.append((collection, key, value))

        async def log_append(self, collection: str, entry: Any) -> None:  # noqa: ARG002
            return None

    db = _DB()
    ctx = SimpleNamespace(
        game_db=db,
        blocks=[],
        plugin_name="state",
        turn_id="turn-1",
        declared_output_types={"character_sheet"},
    )
    out = await plugin_agent._handle_emit(
        {
            "writes": [{"collection": "characters", "key": "hero", "value": {"hp": 90}}],
            "items": [
                {
                    "type": "character_sheet",
                    "data": {"character_id": "new", "name": None},
                }
            ]
        },
        ctx,
    )
    assert out["status"] == "error"
    assert any("character_sheet.data.name" in err for err in out.get("errors", []))
    assert ctx.blocks == []
    assert db.writes == []


@pytest.mark.asyncio
async def test_handle_emit_rejects_scene_update_missing_name() -> None:
    class _DB:
        async def kv_set(self, collection: str, key: str, value: Any) -> None:  # noqa: ARG002
            return None

        async def log_append(self, collection: str, entry: Any) -> None:  # noqa: ARG002
            return None

    ctx = SimpleNamespace(
        game_db=_DB(),
        blocks=[],
        plugin_name="state",
        turn_id="turn-1",
        declared_output_types={"scene_update"},
    )
    out = await plugin_agent._handle_emit(
        {
            "items": [{"type": "scene_update", "data": {"action": "move", "to": "酒馆"}}],
        },
        ctx,
    )
    assert out["status"] == "error"
    assert any("scene_update.data.name" in err for err in out.get("errors", []))
    assert ctx.blocks == []


@pytest.mark.asyncio
async def test_handle_emit_rejects_choices_with_markdown_merged_options() -> None:
    class _DB:
        async def kv_set(self, collection: str, key: str, value: Any) -> None:  # noqa: ARG002
            return None

        async def log_append(self, collection: str, entry: Any) -> None:  # noqa: ARG002
            return None

    decls = plugin_agent._build_output_declarations(
        {
            "outputs": {
                "choices": {
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "prompt": {"type": "string"},
                            "type": {"type": "string", "enum": ["single", "multi"]},
                            "options": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 6,
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["prompt", "type", "options"],
                    }
                }
            }
        },
        "guide",
    )
    ctx = SimpleNamespace(
        game_db=_DB(),
        blocks=[],
        plugin_name="guide",
        turn_id="turn-1",
        declared_output_types={"choices"},
        declared_output_declarations=decls,
    )
    out = await plugin_agent._handle_emit(
        {
            "items": [
                {
                    "type": "choices",
                    "data": {
                        "prompt": "请选择",
                        "type": "single",
                        "options": [
                            "**选项A** / **选项B** / **选项C**",
                        ],
                    },
                }
            ]
        },
        ctx,
    )
    assert out["status"] == "error"
    assert any("options" in err for err in out.get("errors", []))
    assert ctx.blocks == []


@pytest.mark.asyncio
async def test_handle_emit_filters_undeclared_output_types() -> None:
    class _DB:
        async def kv_set(self, collection: str, key: str, value: Any) -> None:  # noqa: ARG002
            return None

        async def log_append(self, collection: str, entry: Any) -> None:  # noqa: ARG002
            return None

    ctx = SimpleNamespace(
        game_db=_DB(),
        blocks=[],
        plugin_name="state",
        turn_id="turn-1",
        declared_output_types={"scene_update"},
    )
    out = await plugin_agent._handle_emit(
        {
            "items": [
                {"type": "notification", "data": {"content": "x"}},
                {"type": "scene_update", "data": {"action": "move", "name": "酒馆"}},
            ]
        },
        ctx,
    )
    assert out["status"] == "error"
    assert any("undeclared output type: notification" in e for e in out["errors"])


@pytest.mark.asyncio
async def test_handle_emit_ignores_items_when_plugin_declares_no_outputs() -> None:
    class _DB:
        async def kv_set(self, collection: str, key: str, value: Any) -> None:  # noqa: ARG002
            return None

        async def log_append(self, collection: str, entry: Any) -> None:  # noqa: ARG002
            return None

    ctx = SimpleNamespace(
        game_db=_DB(),
        blocks=[],
        plugin_name="database",
        turn_id="turn-1",
        declared_output_types=set(),
    )
    out = await plugin_agent._handle_emit(
        {"items": [{"type": "notification", "data": {"content": "x"}}]},
        ctx,
    )
    assert out["status"] == "error"
    assert any("no outputs" in e for e in out["errors"])
    assert ctx.blocks == []


@pytest.mark.asyncio
async def test_execute_tool_returns_structured_invalid_argument_error() -> None:
    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="emit", arguments="{bad-json"),
    )
    out = await plugin_agent._execute_tool(tool_call, SimpleNamespace())
    assert out["ok"] is False
    assert out["error"]["tool"] == "emit"
    assert out["error"]["code"] == "INVALID_ARGUMENTS"
    assert "TOOL_ERROR [emit]" in out["text"]


@pytest.mark.asyncio
async def test_execute_tool_returns_structured_unknown_tool_error() -> None:
    tool_call = SimpleNamespace(
        function=SimpleNamespace(name="unknown_tool", arguments="{}"),
    )
    out = await plugin_agent._execute_tool(tool_call, SimpleNamespace(game_db=SimpleNamespace()))
    assert out["ok"] is False
    assert out["error"]["tool"] == "unknown_tool"
    assert out["error"]["code"] == "UNKNOWN_TOOL"
    assert out["error"]["retryable"] is False
    assert "TOOL_ERROR [unknown_tool]" in out["text"]
