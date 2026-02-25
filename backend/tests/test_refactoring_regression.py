"""Regression tests for refactoring errors caught during backend restructuring.

Covers:
- SessionStateAccessor methods (increment_plugin_trigger_counts, set_block_trigger_counts, etc.)
- plugin_agent re-exports (_handle_emit, _build_block_instructions)
- debug_log_service import (add_debug_log)
- _plugins_to_count helper in chat_service
"""
from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# SessionStateAccessor
# ---------------------------------------------------------------------------


class TestSessionStateAccessorIncrementPluginTriggerCounts:
    def test_returns_valid_json_string(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        result = acc.increment_plugin_trigger_counts(["choices"])
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_increments_count_for_named_plugin(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        result = acc.increment_plugin_trigger_counts(["choices"])
        parsed = json.loads(result)
        assert parsed["plugin_execution_counts"]["choices"] == 1

    def test_increments_existing_count(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({"plugin_execution_counts": {"choices": 3}})
        acc = SessionStateAccessor(state, "sess-1")
        result = acc.increment_plugin_trigger_counts(["choices"])
        parsed = json.loads(result)
        assert parsed["plugin_execution_counts"]["choices"] == 4

    def test_writes_both_canonical_and_legacy_keys(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        result = acc.increment_plugin_trigger_counts(["dice-roll"])
        parsed = json.loads(result)
        assert "plugin_execution_counts" in parsed
        assert "plugin_trigger_counts" in parsed

    def test_handles_empty_plugin_list(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        result = acc.increment_plugin_trigger_counts([])
        parsed = json.loads(result)
        assert parsed.get("plugin_execution_counts") == {}


class TestSessionStateAccessorSetBlockTriggerCounts:
    def test_returns_valid_json_string(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        result = acc.set_block_trigger_counts({"choices": 2})
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_persists_block_counts_under_correct_key(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        result = acc.set_block_trigger_counts({"guide": 1, "choices": 3})
        parsed = json.loads(result)
        assert parsed["block_trigger_counts"]["guide"] == 1
        assert parsed["block_trigger_counts"]["choices"] == 3

    def test_overwrites_previous_block_counts(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({"block_trigger_counts": {"guide": 5}})
        acc = SessionStateAccessor(state, "sess-1")
        result = acc.set_block_trigger_counts({"guide": 1})
        parsed = json.loads(result)
        assert parsed["block_trigger_counts"]["guide"] == 1

    def test_handles_empty_dict(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        result = acc.set_block_trigger_counts({})
        parsed = json.loads(result)
        assert parsed["block_trigger_counts"] == {}


class TestSessionStateAccessorLoadTurnCount:
    def test_returns_zero_for_empty_state(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        assert acc.load_turn_count() == 0

    def test_returns_zero_for_none_state(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor(None, "sess-1")
        assert acc.load_turn_count() == 0

    def test_returns_zero_for_invalid_json(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("not-json", "sess-1")
        assert acc.load_turn_count() == 0

    def test_returns_stored_turn_count(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({"turn_count": 7})
        acc = SessionStateAccessor(state, "sess-1")
        assert acc.load_turn_count() == 7

    def test_clamps_negative_to_zero(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({"turn_count": -3})
        acc = SessionStateAccessor(state, "sess-1")
        assert acc.load_turn_count() == 0


class TestSessionStateAccessorLoadPluginTriggerCounts:
    def test_reads_canonical_key(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({"plugin_execution_counts": {"choices": 2}})
        acc = SessionStateAccessor(state, "sess-1")
        counts = acc.load_plugin_trigger_counts()
        assert counts["choices"] == 2

    def test_falls_back_to_legacy_key(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({"plugin_trigger_counts": {"dice-roll": 5}})
        acc = SessionStateAccessor(state, "sess-1")
        counts = acc.load_plugin_trigger_counts()
        assert counts["dice-roll"] == 5

    def test_canonical_takes_precedence_over_legacy(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({
            "plugin_execution_counts": {"choices": 10},
            "plugin_trigger_counts": {"choices": 1},
        })
        acc = SessionStateAccessor(state, "sess-1")
        counts = acc.load_plugin_trigger_counts()
        assert counts["choices"] == 10

    def test_returns_empty_dict_when_no_counts(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        assert acc.load_plugin_trigger_counts() == {}


class TestSessionStateAccessorLoadBlockTriggerCounts:
    def test_returns_normalized_counts(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({"block_trigger_counts": {"guide": 3, "choices": 1}})
        acc = SessionStateAccessor(state, "sess-1")
        counts = acc.load_block_trigger_counts()
        assert counts["guide"] == 3
        assert counts["choices"] == 1

    def test_returns_empty_dict_when_missing(self):
        from backend.app.services.session_state import SessionStateAccessor

        acc = SessionStateAccessor("{}", "sess-1")
        assert acc.load_block_trigger_counts() == {}

    def test_ignores_non_dict_value(self):
        from backend.app.services.session_state import SessionStateAccessor

        state = json.dumps({"block_trigger_counts": "bad"})
        acc = SessionStateAccessor(state, "sess-1")
        assert acc.load_block_trigger_counts() == {}


# ---------------------------------------------------------------------------
# plugin_agent re-exports
# ---------------------------------------------------------------------------


class TestPluginAgentReExports:
    def test_handle_emit_importable_from_plugin_agent(self):
        # Regression: _handle_emit was moved to plugin_agent_tools but must
        # remain importable from plugin_agent via __all__ re-export.
        from backend.app.services.plugin_agent import _handle_emit  # noqa: F401

        assert callable(_handle_emit)

    def test_build_block_instructions_importable_from_plugin_agent(self):
        # Regression: _build_block_instructions lives in plugin_agent_prompt
        # but must remain importable from plugin_agent via __all__ re-export.
        from backend.app.services.plugin_agent import _build_block_instructions  # noqa: F401

        assert callable(_build_block_instructions)


# ---------------------------------------------------------------------------
# debug_log_service imports
# ---------------------------------------------------------------------------


class TestDebugLogServiceImport:
    def test_add_debug_log_importable(self):
        # Regression: _add_log was previously imported from api/debug_log
        # (layer violation). It must now live in services/debug_log_service.
        from backend.app.services.debug_log_service import add_debug_log  # noqa: F401

        assert callable(add_debug_log)

    def test_add_debug_log_callable_without_error(self):
        from backend.app.services.debug_log_service import add_debug_log

        # Should not raise; just appends to in-memory ring buffer.
        add_debug_log("test-session", "debug", {"type": "test", "msg": "hello"})


# ---------------------------------------------------------------------------
# _plugins_to_count in chat_service
# ---------------------------------------------------------------------------


class TestPluginsToCount:
    def test_reads_plugins_executed_key(self):
        from backend.app.services.chat_service import _plugins_to_count

        summary = {"plugins_executed": ["choices", "dice-roll"]}
        assert _plugins_to_count(summary) == ["choices", "dice-roll"]

    def test_falls_back_to_plugins_run_key(self):
        from backend.app.services.chat_service import _plugins_to_count

        summary = {"plugins_run": ["guide"]}
        assert _plugins_to_count(summary) == ["guide"]

    def test_plugins_executed_takes_precedence_over_plugins_run(self):
        from backend.app.services.chat_service import _plugins_to_count

        summary = {"plugins_executed": ["choices"], "plugins_run": ["guide"]}
        assert _plugins_to_count(summary) == ["choices"]

    def test_returns_empty_list_for_empty_dict(self):
        from backend.app.services.chat_service import _plugins_to_count

        assert _plugins_to_count({}) == []

    def test_returns_empty_list_when_value_is_not_a_list(self):
        from backend.app.services.chat_service import _plugins_to_count

        assert _plugins_to_count({"plugins_executed": "choices"}) == []

    def test_strips_blank_entries(self):
        from backend.app.services.chat_service import _plugins_to_count

        summary = {"plugins_executed": ["choices", "", "  ", "dice-roll"]}
        result = _plugins_to_count(summary)
        assert result == ["choices", "dice-roll"]

    def test_returns_empty_list_for_missing_keys(self):
        from backend.app.services.chat_service import _plugins_to_count

        # Neither key present — should return empty list without raising.
        assert _plugins_to_count({"rounds": 2}) == []
