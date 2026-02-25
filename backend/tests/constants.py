from __future__ import annotations

PLUGINS_DIR = "plugins"

CURRENT_PLUGIN_IDS = {
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

REQUIRED_PLUGIN_IDS = {"database", "state", "event"}

RUNTIME_STATE_KEYS = {
    "narrative_tone": "state.narrative_tone",
    "pacing": "state.pacing",
    "response_length": "state.response_length",
}

RUNTIME_IMAGE_KEYS = {
    "reference_count": "image.reference_count",
    "prompt_template": "image.prompt_template",
}

