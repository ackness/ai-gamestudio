from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.db.engine import get_session
from backend.app.models.project import Project
from backend.app.services.plugin_service import get_enabled_plugins
from backend.app.services.runtime_settings_service import (
    get_runtime_settings_schema,
    patch_runtime_settings,
    resolve_runtime_settings,
)

router = APIRouter(prefix="/api/runtime-settings", tags=["runtime-settings"])


class RuntimeSettingsPatchBody(BaseModel):
    project_id: str
    session_id: str | None = None
    scope: Literal["project", "session"] = "project"
    values: dict[str, Any]


def _group_schema_by_plugin(schema_fields: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for field in schema_fields:
        plugin_name = str(field.get("plugin_name") or "")
        key = str(field.get("key") or "")
        if not plugin_name or not key:
            continue
        grouped.setdefault(plugin_name, []).append(key)
    return grouped


@router.get("/schema")
async def get_settings_schema(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    enabled = await get_enabled_plugins(
        session,
        project_id,
        world_doc=project.world_doc,
    )
    enabled_names = [item["plugin_name"] for item in enabled]
    schema_fields = get_runtime_settings_schema(enabled_names)
    return {
        "fields": schema_fields,
        "by_plugin": _group_schema_by_plugin(schema_fields),
        "enabled_plugins": enabled_names,
    }


@router.get("")
async def get_runtime_settings(
    project_id: str,
    session_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    enabled = await get_enabled_plugins(
        session,
        project_id,
        world_doc=project.world_doc,
    )
    enabled_names = [item["plugin_name"] for item in enabled]

    resolved = await resolve_runtime_settings(
        session,
        project_id=project_id,
        session_id=session_id,
        enabled_plugins=enabled_names,
    )
    return {
        "values": resolved["values"],
        "by_plugin": resolved["by_plugin"],
        "project_overrides": resolved["project_overrides"],
        "session_overrides": resolved["session_overrides"],
    }


@router.patch("")
async def patch_runtime_settings_endpoint(
    body: RuntimeSettingsPatchBody,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    enabled = await get_enabled_plugins(
        session,
        body.project_id,
        world_doc=project.world_doc,
    )
    enabled_names = [item["plugin_name"] for item in enabled]

    try:
        await patch_runtime_settings(
            session,
            project_id=body.project_id,
            session_id=body.session_id,
            enabled_plugins=enabled_names,
            scope=body.scope,
            values=body.values,
            autocommit=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resolved = await resolve_runtime_settings(
        session,
        project_id=body.project_id,
        session_id=body.session_id,
        enabled_plugins=enabled_names,
    )
    return {
        "ok": True,
        "values": resolved["values"],
        "by_plugin": resolved["by_plugin"],
        "project_overrides": resolved["project_overrides"],
        "session_overrides": resolved["session_overrides"],
    }
