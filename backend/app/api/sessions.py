from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.db.engine import get_session
from backend.app.models.message import Message
from backend.app.models.project import Project
from backend.app.models.session import GameSession
from backend.app.services.archive_service import ensure_archive_initialized
from backend.app.services.data_cleanup import delete_session_data

router = APIRouter(prefix="/api", tags=["sessions"])


class SessionCreate(BaseModel):
    id: str | None = None  # optional: caller may supply existing UUID to upsert after cold start


@router.post("/projects/{project_id}/sessions", response_model=GameSession)
async def create_session(
    project_id: str,
    body: SessionCreate = SessionCreate(),
    session: AsyncSession = Depends(get_session),
):
    # Verify project exists
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # If a specific ID is provided, upsert: return existing session or create with that ID.
    if body.id:
        existing = await session.get(GameSession, body.id)
        if existing:
            return existing

    game_session = GameSession(
        **({"id": body.id} if body.id else {}),
        project_id=project_id,
    )
    session.add(game_session)
    await session.commit()
    await session.refresh(game_session)

    # Initialize archive metadata for this session.
    await ensure_archive_initialized(session, project_id=project_id, session_id=game_session.id)
    await session.refresh(game_session)

    return game_session


@router.get("/projects/{project_id}/sessions", response_model=list[GameSession])
async def list_sessions(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    stmt = (
        select(GameSession)
        .where(GameSession.project_id == project_id)
        .order_by(GameSession.created_at.desc())  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    return list(result.all())


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    await delete_session_data(
        session,
        session_id=session_id,
        project_id=game_session.project_id,
        autocommit=True,
    )
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    # Verify session exists
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())  # type: ignore[arg-type]
        .limit(limit)
    )
    result = await session.exec(stmt)
    messages = list(result.all())

    # Re-extract blocks from raw_content so the frontend can render them.
    from backend.app.core.block_parser import extract_blocks

    # Block types that are infrastructure (already applied to DB), not UI.
    _INFRA_BLOCK_TYPES = {"state_update"}

    enriched = []
    for msg in messages:
        d = msg.model_dump()
        d["created_at"] = msg.created_at.isoformat() if msg.created_at else None
        blocks = []
        metadata_blocks: list[dict] = []
        if msg.metadata_json:
            try:
                metadata = json.loads(msg.metadata_json)
                raw_meta_blocks = metadata.get("blocks")
                if isinstance(raw_meta_blocks, list):
                    for item in raw_meta_blocks:
                        if not isinstance(item, dict):
                            continue
                        block_type = item.get("type")
                        if not isinstance(block_type, str):
                            continue
                        if block_type in _INFRA_BLOCK_TYPES:
                            continue
                        metadata_blocks.append(
                            {
                                "type": block_type,
                                "data": item.get("data"),
                                "block_id": item.get("block_id"),
                            }
                        )
            except Exception:
                metadata_blocks = []
        if metadata_blocks:
            blocks = metadata_blocks
        elif msg.raw_content:
            raw_blocks = extract_blocks(msg.raw_content)
            blocks = [
                {
                    "type": b["type"],
                    "data": b["data"],
                    "block_id": f"{msg.id}:{idx}",
                }
                for idx, b in enumerate(raw_blocks)
                if b["type"] not in _INFRA_BLOCK_TYPES
            ]
        d["blocks"] = blocks
        enriched.append(d)
    return enriched


@router.get("/sessions/{session_id}/state")
async def get_session_state(
    session_id: str,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        game_state = json.loads(game_session.game_state_json or "{}")
    except Exception:
        game_state = {}
    if not isinstance(game_state, dict):
        game_state = {}

    world_state = game_state.get("world_state", {})
    if not isinstance(world_state, dict):
        world_state = {}

    turn_count_raw = game_state.get("turn_count", 0)
    try:
        turn_count = int(turn_count_raw)
    except Exception:
        turn_count = 0

    return {
        "world": world_state,
        "turn_count": turn_count,
    }
