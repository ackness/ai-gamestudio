from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.config import settings
from backend.app.core.plugin_registry import get_plugin_engine
from backend.app.db.engine import get_session
from backend.app.models.project import Project
from backend.app.services.plugin_service import (
    get_enabled_plugins,
    toggle_plugin,
)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("")
async def list_plugins():
    """List all available plugins found in the plugins directory."""
    engine = get_plugin_engine()
    plugins = engine.discover(settings.PLUGINS_DIR)
    return plugins


class ToggleBody(BaseModel):
    project_id: str
    enabled: bool


@router.post("/{plugin_name}/toggle")
async def toggle_plugin_endpoint(
    plugin_name: str,
    body: ToggleBody,
    session: AsyncSession = Depends(get_session),
):
    """Enable or disable a plugin for a specific project."""
    # Verify plugin exists
    pe = get_plugin_engine()
    available = pe.discover(settings.PLUGINS_DIR)
    names = [p["name"] for p in available]
    if plugin_name not in names:
        raise HTTPException(status_code=404, detail="Plugin not found")

    try:
        await toggle_plugin(
            session,
            project_id=body.project_id,
            plugin_name=plugin_name,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "plugin": plugin_name, "enabled": body.enabled}


@router.get("/enabled/{project_id}")
async def list_enabled_plugins(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List plugins enabled for a specific project."""
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    enabled = await get_enabled_plugins(session, project_id, world_doc=project.world_doc)
    return enabled


@router.get("/block-schemas")
async def get_block_schemas(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Return UI schemas for all block types declared by enabled plugins.

    Used by the frontend to drive generic schema-based block rendering.
    """
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    enabled = await get_enabled_plugins(
        session,
        project_id,
        world_doc=project.world_doc,
    )
    enabled_names = [p["plugin_name"] for p in enabled]

    pe = get_plugin_engine()
    try:
        declarations = pe.get_block_declarations(enabled_names, settings.PLUGINS_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    schemas: dict[str, dict] = {}
    for block_type, decl in declarations.items():
        entry: dict = {}
        if decl.ui:
            entry.update(decl.ui)
        entry["requires_response"] = decl.requires_response
        entry["plugin_name"] = decl.plugin_name
        if decl.schema:
            entry["schema"] = decl.schema
        schemas[block_type] = entry

    return schemas


@router.get("/block-conflicts")
async def get_block_conflicts(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Return block type conflicts among enabled plugins for a project."""
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    enabled = await get_enabled_plugins(
        session,
        project_id,
        world_doc=project.world_doc,
    )
    enabled_names = [p["plugin_name"] for p in enabled]

    pe = get_plugin_engine()
    conflicts = pe.get_block_conflicts(enabled_names, settings.PLUGINS_DIR)
    return conflicts
