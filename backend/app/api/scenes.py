from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.db.engine import get_session
from backend.app.models.scene import Scene
from backend.app.models.scene_npc import SceneNPC
from backend.app.models.session import GameSession

router = APIRouter(prefix="/api", tags=["scenes"])


@router.get("/sessions/{session_id}/scenes", response_model=list[Scene])
async def list_scenes(
    session_id: str,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(Scene)
        .where(Scene.session_id == session_id)
        .order_by(Scene.created_at.asc())  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    return list(result.all())


@router.get("/sessions/{session_id}/scenes/current", response_model=Scene | None)
async def get_current_scene(
    session_id: str,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = select(Scene).where(
        Scene.session_id == session_id, Scene.is_current == True  # noqa: E712
    )
    result = await session.exec(stmt)
    return result.first()


@router.get("/scenes/{scene_id}/npcs", response_model=list[SceneNPC])
async def get_scene_npcs(
    scene_id: str,
    session: AsyncSession = Depends(get_session),
):
    scene = await session.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    stmt = select(SceneNPC).where(SceneNPC.scene_id == scene_id)
    result = await session.exec(stmt)
    return list(result.all())
