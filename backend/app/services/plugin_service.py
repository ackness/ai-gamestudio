from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.config import settings
from backend.app.core.plugin_registry import get_plugin_engine
from backend.app.models.plugin_storage import PluginStorage
from backend.app.models.project import Project

# We use PluginStorage with a special key "_enabled" to track plugin on/off state.
_ENABLED_KEY = "_enabled"


async def get_enabled_plugins(
    session: AsyncSession,
    project_id: str,
    world_doc: str | None = None,
) -> list[dict[str, Any]]:
    """Return enabled plugins for a project.

    Required plugins are always treated as enabled, even if no toggle record exists.
    Plugins declared in world_doc frontmatter are enabled by default but can be
    explicitly disabled by the user.
    """
    pe = get_plugin_engine()
    discovered = pe.discover(settings.PLUGINS_DIR)
    discovered_map = {p["name"]: p for p in discovered}
    required_names = {p["name"] for p in discovered if p.get("required")}
    default_enabled_names = {p["name"] for p in discovered if p.get("default_enabled")}

    # Parse world_doc frontmatter for default plugins
    world_default_names: set[str] = set()
    if world_doc:
        try:
            import frontmatter as fm

            parsed = fm.loads(world_doc)
            plugins_list = parsed.metadata.get("plugins", [])
            if isinstance(plugins_list, list):
                world_default_names = {str(p) for p in plugins_list}
        except Exception:
            pass

    stmt = select(PluginStorage).where(
        PluginStorage.project_id == project_id,
        PluginStorage.key == _ENABLED_KEY,
    )
    result = await session.exec(stmt)
    rows = list(result.all())
    enabled_names: set[str] = (
        set(required_names)
        | {name for name in world_default_names if name in discovered_map}
        | {name for name in default_enabled_names if name in discovered_map}
    )
    explicitly_user_enabled: set[str] = set()
    explicitly_disabled: set[str] = set()
    for row in rows:
        data = json.loads(row.value_json)
        if data.get("enabled"):
            enabled_names.add(row.plugin_name)
            explicitly_user_enabled.add(row.plugin_name)
            explicitly_disabled.discard(row.plugin_name)
        else:
            explicitly_disabled.add(row.plugin_name)
            # Required plugins cannot be disabled by storage toggle.
            if row.plugin_name in required_names:
                enabled_names.add(row.plugin_name)
            # World-default and default_enabled plugins CAN be explicitly disabled.
            elif row.plugin_name in world_default_names or row.plugin_name in default_enabled_names:
                enabled_names.discard(row.plugin_name)

    # Auto-enable dependencies of effective enabled plugins.
    auto_enabled_names: set[str] = set()
    queue = list(enabled_names)
    while queue:
        plugin_name = queue.pop(0)
        metadata = discovered_map.get(plugin_name) or {}
        dependencies = metadata.get("dependencies", []) or []
        for dep in dependencies:
            if dep in discovered_map and dep not in enabled_names:
                enabled_names.add(dep)
                auto_enabled_names.add(dep)
                queue.append(dep)

    # Apply supersedes: if a plugin is enabled and supersedes others,
    # remove superseded plugins unless user explicitly enabled them.
    for plugin_name in list(enabled_names):
        meta = discovered_map.get(plugin_name) or {}
        for superseded in meta.get("supersedes", []):
            if superseded in enabled_names and superseded not in explicitly_user_enabled:
                enabled_names.discard(superseded)
                logger.debug(
                    "Plugin '{}' superseded by '{}', suppressing from active set",
                    superseded,
                    plugin_name,
                )

    enabled: list[dict[str, Any]] = [
        {
            "plugin_name": name,
            "enabled": True,
            "required": name in required_names,
            "auto_enabled": name in auto_enabled_names,
            "explicitly_disabled": name in explicitly_disabled,
            "dependencies": list(
                (discovered_map.get(name) or {}).get("dependencies", []) or []
            ),
            "required_by": sorted(
                [
                    other
                    for other in enabled_names
                    if other != name
                    and name
                    in (
                        (discovered_map.get(other) or {}).get("dependencies", [])
                        or []
                    )
                ]
            ),
        }
        for name in sorted(enabled_names)
    ]
    return enabled


async def toggle_plugin(
    session: AsyncSession,
    project_id: str,
    plugin_name: str,
    enabled: bool,
) -> None:
    """Enable or disable a plugin for a project."""
    pe = get_plugin_engine()
    discovered = pe.discover(settings.PLUGINS_DIR)
    required_names = {p["name"] for p in discovered if p.get("required")}
    discovered_names = {p["name"] for p in discovered}
    if plugin_name not in discovered_names:
        raise ValueError(f"Plugin '{plugin_name}' not found")

    if plugin_name in required_names and not enabled:
        raise ValueError(f"Plugin '{plugin_name}' is required and cannot be disabled")

    project = await session.get(Project, project_id)
    if not project:
        raise ValueError(f"Project '{project_id}' not found")

    if not enabled:
        enabled_plugins = await get_enabled_plugins(
            session,
            project_id=project_id,
            world_doc=project.world_doc,
        )
        enabled_names = {item["plugin_name"] for item in enabled_plugins}
        dependents: list[str] = []
        for name in enabled_names:
            if name == plugin_name:
                continue
            loaded = pe.load(name, settings.PLUGINS_DIR)
            if not loaded:
                continue
            deps = loaded["metadata"].get("dependencies", []) or []
            if plugin_name in deps:
                dependents.append(name)
        if dependents:
            dep_list = ", ".join(sorted(dependents))
            raise ValueError(
                f"Plugin '{plugin_name}' is required by enabled plugin(s): {dep_list}"
            )

    stmt = select(PluginStorage).where(
        PluginStorage.project_id == project_id,
        PluginStorage.plugin_name == plugin_name,
        PluginStorage.key == _ENABLED_KEY,
    )
    result = await session.exec(stmt)
    row = result.first()

    if row:
        row.value_json = json.dumps({"enabled": enabled})
        session.add(row)
    else:
        row = PluginStorage(
            project_id=project_id,
            plugin_name=plugin_name,
            key=_ENABLED_KEY,
            value_json=json.dumps({"enabled": enabled}),
        )
        session.add(row)
    await session.commit()


async def storage_get(
    session: AsyncSession,
    project_id: str,
    plugin_name: str,
    key: str,
) -> Any:
    """Read a plugin storage value."""
    stmt = select(PluginStorage).where(
        PluginStorage.project_id == project_id,
        PluginStorage.plugin_name == plugin_name,
        PluginStorage.key == key,
    )
    result = await session.exec(stmt)
    row = result.first()
    if not row:
        return None
    return json.loads(row.value_json)


async def storage_set(
    session: AsyncSession,
    project_id: str,
    plugin_name: str,
    key: str,
    value: Any,
    *,
    autocommit: bool = True,
) -> None:
    """Write a plugin storage value."""
    stmt = select(PluginStorage).where(
        PluginStorage.project_id == project_id,
        PluginStorage.plugin_name == plugin_name,
        PluginStorage.key == key,
    )
    result = await session.exec(stmt)
    row = result.first()

    value_json = json.dumps(value)
    if row:
        row.value_json = value_json
        session.add(row)
    else:
        row = PluginStorage(
            project_id=project_id,
            plugin_name=plugin_name,
            key=key,
            value_json=value_json,
        )
        session.add(row)
    if autocommit:
        await session.commit()
    else:
        await session.flush()
