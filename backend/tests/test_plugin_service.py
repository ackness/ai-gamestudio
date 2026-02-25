from __future__ import annotations

import pytest

from backend.app.core.plugin_engine import PluginEngine
from backend.app.services.plugin_service import get_enabled_plugins, toggle_plugin
from backend.tests.constants import REQUIRED_PLUGIN_IDS


@pytest.mark.asyncio
async def test_required_plugins_enabled_by_default(db_session, sample_project):
    enabled = await get_enabled_plugins(db_session, sample_project.id)
    names = {item["plugin_name"] for item in enabled}

    assert REQUIRED_PLUGIN_IDS.issubset(names)


@pytest.mark.asyncio
async def test_required_plugin_cannot_be_disabled(db_session, sample_project):
    with pytest.raises(ValueError):
        await toggle_plugin(
            db_session,
            project_id=sample_project.id,
            plugin_name="database",
            enabled=False,
        )


@pytest.mark.asyncio
async def test_auto_enable_dependencies_and_required_by(
    db_session,
    sample_project,
    monkeypatch: pytest.MonkeyPatch,
):
    discovered = [
        {
            "name": "database",
            "description": "base",
            "type": "global",
            "required": True,
            "dependencies": [],
            "path": "plugins/database",
        },
        {
            "name": "addon",
            "description": "addon",
            "type": "gameplay",
            "required": False,
            "dependencies": ["helper"],
            "path": "plugins/addon",
        },
        {
            "name": "helper",
            "description": "helper",
            "type": "gameplay",
            "required": False,
            "dependencies": [],
            "path": "plugins/helper",
        },
    ]
    monkeypatch.setattr(PluginEngine, "discover", lambda self, _: discovered)

    sample_project.world_doc = "---\nplugins:\n  - addon\n---\n# Test World"
    db_session.add(sample_project)
    await db_session.commit()

    enabled = await get_enabled_plugins(
        db_session,
        sample_project.id,
        world_doc=sample_project.world_doc,
    )
    by_name = {item["plugin_name"]: item for item in enabled}
    assert by_name["addon"]["auto_enabled"] is False
    assert by_name["helper"]["auto_enabled"] is True
    assert by_name["helper"]["required_by"] == ["addon"]


@pytest.mark.asyncio
async def test_disable_plugin_blocked_when_required_by_enabled(
    db_session,
    sample_project,
    monkeypatch: pytest.MonkeyPatch,
):
    discovered = [
        {
            "name": "database",
            "description": "base",
            "type": "global",
            "required": False,
            "dependencies": [],
            "path": "plugins/database",
        },
        {
            "name": "addon",
            "description": "addon",
            "type": "gameplay",
            "required": False,
            "dependencies": ["helper"],
            "path": "plugins/addon",
        },
        {
            "name": "helper",
            "description": "helper",
            "type": "gameplay",
            "required": False,
            "dependencies": [],
            "path": "plugins/helper",
        },
    ]

    def _fake_load(self, plugin_name: str, plugins_dir: str | None = None):
        for p in discovered:
            if p["name"] == plugin_name:
                return {"name": plugin_name, "metadata": {"dependencies": p["dependencies"]}}
        return None

    monkeypatch.setattr(PluginEngine, "discover", lambda self, _: discovered)
    monkeypatch.setattr(PluginEngine, "load", _fake_load)

    # Explicitly enable addon so helper is required transitively.
    await toggle_plugin(
        db_session,
        project_id=sample_project.id,
        plugin_name="addon",
        enabled=True,
    )

    with pytest.raises(ValueError, match="required by enabled plugin"):
        await toggle_plugin(
            db_session,
            project_id=sample_project.id,
            plugin_name="helper",
            enabled=False,
        )
