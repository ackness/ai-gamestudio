from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.db.engine import get_session
from backend.app.models.project import Project
from backend.app.models.session import GameSession
from backend.app.services.archive_service import (
    create_archive_summary,
    list_archive_versions,
    restore_archive_version,
)

router = APIRouter(prefix="/api", tags=["archive"])


class SummarizeBody(BaseModel):
    reason: str | None = None


class RestoreBody(BaseModel):
    mode: Literal["hard", "fork"] = "fork"


@router.get("/sessions/{session_id}/archives")
async def get_archives(
    session_id: str,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    versions = await list_archive_versions(
        session,
        project_id=game_session.project_id,
        session_id=session_id,
    )
    return versions


@router.post("/sessions/{session_id}/archives/summarize")
async def summarize_archive(
    session_id: str,
    body: SummarizeBody,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    project = await session.get(Project, game_session.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    created = await create_archive_summary(
        session,
        project=project,
        game_session=game_session,
        trigger="manual",
        reason=body.reason,
    )
    return created


@router.post("/sessions/{session_id}/archives/{version}/restore")
async def restore_archive(
    session_id: str,
    version: int,
    body: RestoreBody | None = None,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        restored = await restore_archive_version(
            session,
            project_id=game_session.project_id,
            session_id=session_id,
            version=version,
            mode=(body.mode if body else "fork"),
        )
    except ValueError as exc:
        status_code = 400 if "mode" in str(exc).lower() else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return restored
