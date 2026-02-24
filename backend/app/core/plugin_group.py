"""Plugin Group loader — discovers and loads group.json files."""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class PluginGroup:
    name: str
    description: str = ""
    shared_prompt: str = ""
    execution_mode: str = "merged"  # "merged" | "parallel"
    plugins: list[str] = field(default_factory=list)
    path: pathlib.Path | None = None


def load_groups(plugins_dir: str = "plugins") -> list[PluginGroup]:
    """Discover and load all group.json files under plugins_dir."""
    base = pathlib.Path(plugins_dir)
    groups: list[PluginGroup] = []
    for group_json in sorted(base.glob("*/group.json")):
        try:
            data = json.loads(group_json.read_text(encoding="utf-8"))
            groups.append(PluginGroup(
                name=data["name"],
                description=data.get("description", ""),
                shared_prompt=data.get("shared_prompt", ""),
                execution_mode=data.get("execution_mode", "merged"),
                plugins=data.get("plugins", []),
                path=group_json.parent,
            ))
        except Exception:
            logger.exception("Failed to load group.json: {}", group_json)
    return groups


def get_group_for_plugin(plugin_name: str, groups: list[PluginGroup]) -> PluginGroup | None:
    """Find which group a plugin belongs to."""
    for g in groups:
        if plugin_name in g.plugins:
            return g
    return None
