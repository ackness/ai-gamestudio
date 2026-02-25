from __future__ import annotations

from backend.app.core.plugin_hooks import (
    DEFAULT_PLUGIN_HOOK,
    normalize_plugin_hooks,
)


def test_normalize_plugin_hooks_empty_default_list_no_recursion() -> None:
    # Regression guard: previously default_hooks=[] triggered infinite recursion.
    out = normalize_plugin_hooks(None, default_hooks=[])
    assert out == []

    # Repeated calls should stay stable and fast.
    for _ in range(100):
        assert normalize_plugin_hooks([], default_hooks=[]) == []


def test_normalize_plugin_hooks_maps_aliases_and_deduplicates() -> None:
    out = normalize_plugin_hooks(["post_narrative", "ui_action", "post_narrative"])
    assert out == ["post_model_output", "frontend_action"]


def test_normalize_plugin_hooks_uses_default_when_input_invalid() -> None:
    out = normalize_plugin_hooks("post_model_output")
    assert out == [DEFAULT_PLUGIN_HOOK]
