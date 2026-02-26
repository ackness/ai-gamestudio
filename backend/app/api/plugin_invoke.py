"""API route for independent plugin invocation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.game_db import GameDB
from backend.app.core.llm_config import resolve_llm_config, resolve_plugin_llm_config
from backend.app.core.plugin_engine import PluginEngine
from backend.app.db.engine import get_session
from backend.app.models.project import Project
from backend.app.models.session import GameSession
from backend.app.services.plugin_agent import invoke_single_plugin
from backend.app.services.plugin_service import get_enabled_plugins
from backend.app.services.runtime_settings_service import resolve_runtime_settings

router = APIRouter()


class PluginInvokeRequest(BaseModel):
    context: dict = Field(default_factory=dict)
    llm_overrides: dict | None = None


@router.post("/chat/{session_id}/plugin/{plugin_name}")
async def invoke_plugin(
    session_id: str,
    plugin_name: str,
    body: PluginInvokeRequest,
    db: SQLModelAsyncSession = Depends(get_session),
):
    game_session = await db.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    project = await db.get(Project, game_session.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    enabled_plugins = await get_enabled_plugins(
        db,
        project_id=project.id,
        world_doc=project.world_doc,
    )
    enabled_names = [item["plugin_name"] for item in enabled_plugins]
    resolved_settings = await resolve_runtime_settings(
        db,
        project_id=project.id,
        session_id=session_id,
        enabled_plugins=enabled_names,
    )
    runtime_settings_by_plugin = (
        resolved_settings.get("by_plugin")
        if isinstance(resolved_settings.get("by_plugin"), dict)
        else {}
    )
    plugin_runtime_settings = (
        runtime_settings_by_plugin.get(plugin_name, {})
        if isinstance(runtime_settings_by_plugin, dict)
        else {}
    )

    pe = PluginEngine()
    game_db = GameDB(db, session_id)
    main_config = resolve_llm_config(project=project, overrides=body.llm_overrides)
    config = resolve_plugin_llm_config(main_config, overrides=body.llm_overrides)
    blocks = await invoke_single_plugin(
        plugin_name=plugin_name,
        context=body.context,
        session_id=session_id,
        game_db=game_db,
        pe=pe,
        config=config,
        runtime_settings=(
            plugin_runtime_settings
            if isinstance(plugin_runtime_settings, dict)
            else {}
        ),
    )
    return {"blocks": blocks}
