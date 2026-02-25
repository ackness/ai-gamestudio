"""Shared plugin lifecycle hook definitions."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

HOOK_PRE_MODEL_INPUT = "pre_model_input"
HOOK_POST_MODEL_OUTPUT = "post_model_output"
HOOK_FRONTEND_ACTION = "frontend_action"
HOOK_POST_DISPATCH = "post_dispatch"

# Backward-compatible aliases.
_HOOK_ALIASES = {
    "pre_narrative": HOOK_PRE_MODEL_INPUT,
    "post_narrative": HOOK_POST_MODEL_OUTPUT,
    "ui_action": HOOK_FRONTEND_ACTION,
}

DEFAULT_PLUGIN_HOOK = HOOK_POST_MODEL_OUTPUT
KNOWN_PLUGIN_HOOKS = {
    HOOK_PRE_MODEL_INPUT,
    HOOK_POST_MODEL_OUTPUT,
    HOOK_FRONTEND_ACTION,
    HOOK_POST_DISPATCH,
}


def normalize_plugin_hooks(
    raw: Any,
    *,
    default_hooks: Iterable[str] | None = None,
) -> list[str]:
    """Normalize hook declarations into unique lowercase identifiers."""
    defaults = list(default_hooks) if default_hooks is not None else [DEFAULT_PLUGIN_HOOK]

    normalized_defaults: list[str] = []
    for item in defaults:
        hook = str(item or "").strip().lower()
        if hook in _HOOK_ALIASES:
            hook = _HOOK_ALIASES[hook]
        if hook and hook not in normalized_defaults:
            normalized_defaults.append(hook)

    if not isinstance(raw, list):
        return normalized_defaults

    normalized: list[str] = []
    for item in raw:
        hook = str(item or "").strip().lower()
        if hook in _HOOK_ALIASES:
            hook = _HOOK_ALIASES[hook]
        if hook and hook not in normalized:
            normalized.append(hook)

    return normalized or normalized_defaults
