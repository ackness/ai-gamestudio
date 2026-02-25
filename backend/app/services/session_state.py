from __future__ import annotations

import json
from typing import Any

from backend.app.core.json_utils import safe_json_loads


class SessionStateAccessor:
    """Parses game_state_json once and provides typed accessors for session state fields."""

    def __init__(self, game_state_json: str | None, session_id: str) -> None:
        raw = safe_json_loads(
            game_state_json,
            fallback={},
            context=f"GameSession state ({session_id})",
        )
        self._state: dict[str, Any] = raw if isinstance(raw, dict) else {}

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def load_turn_count(self) -> int:
        """Return current session turn count."""
        try:
            return max(0, int(self._state.get("turn_count", 0) or 0))
        except Exception:
            return 0

    def load_plugin_trigger_counts(self) -> dict[str, int]:
        """Load canonical/legacy plugin trigger counters."""
        counts = _normalize_plugin_counts(self._state.get("plugin_execution_counts"))
        if counts:
            return counts
        return _normalize_plugin_counts(self._state.get("plugin_trigger_counts"))

    def load_block_trigger_counts(self) -> dict[str, int]:
        """Load per-block trigger counters."""
        return _normalize_plugin_counts(self._state.get("block_trigger_counts"))

    # ------------------------------------------------------------------
    # Write helpers (return updated JSON string, do not mutate in place)
    # ------------------------------------------------------------------

    def increment_plugin_trigger_counts(self, plugins_counted: list[str]) -> str:
        """Increment per-plugin execution counters in canonical + legacy keys."""
        state = dict(self._state)
        counts = _normalize_plugin_counts(state.get("plugin_execution_counts"))
        if not counts:
            counts = _normalize_plugin_counts(state.get("plugin_trigger_counts"))
        for pname in plugins_counted:
            counts[pname] = int(counts.get(pname, 0) or 0) + 1
        state["plugin_execution_counts"] = counts
        state["plugin_trigger_counts"] = counts
        return json.dumps(state)

    def set_block_trigger_counts(self, block_trigger_counts: dict[str, int]) -> str:
        """Persist per-block trigger counters into session state JSON."""
        state = dict(self._state)
        state["block_trigger_counts"] = _normalize_plugin_counts(block_trigger_counts)
        return json.dumps(state)


# ------------------------------------------------------------------
# Module-level helpers (shared with chat_service helpers)
# ------------------------------------------------------------------


def _normalize_plugin_counts(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            counts[name] = max(0, int(value))
        except Exception:
            continue
    return counts
