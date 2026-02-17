from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.db.engine import get_session
from backend.app.models.game_event import GameEvent
from backend.app.models.session import GameSession

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/sessions/{session_id}/events", response_model=list[GameEvent])
async def list_events(
    session_id: str,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = select(GameEvent).where(GameEvent.session_id == session_id)
    if status:
        stmt = stmt.where(GameEvent.status == status)
    stmt = stmt.order_by(GameEvent.created_at.asc())  # type: ignore[arg-type]
    result = await session.exec(stmt)
    return list(result.all())


@router.get("/events/{event_id}", response_model=GameEvent)
async def get_event(
    event_id: str,
    session: AsyncSession = Depends(get_session),
):
    event = await session.get(GameEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
