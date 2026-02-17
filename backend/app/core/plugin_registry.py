from __future__ import annotations

from backend.app.core.plugin_engine import PluginEngine

_PLUGIN_ENGINE = PluginEngine()


def get_plugin_engine() -> PluginEngine:
    """Return the process-wide plugin engine (with metadata/template caches)."""
    return _PLUGIN_ENGINE
