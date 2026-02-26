"""Debug endpoint: raw database table viewer for a session."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.db.engine import get_session
from backend.app.models.audit_log import AuditLog
from backend.app.models.character import Character
from backend.app.models.game_event import GameEvent
from backend.app.models.game_graph import StorageGraph as GameGraph
from backend.app.models.game_kv import StorageKV as GameKV
from backend.app.models.game_log import StorageLog as GameLog
from backend.app.models.message import Message
from backend.app.models.plugin_storage import PluginStorage
from backend.app.models.scene import Scene
from backend.app.models.scene_npc import SceneNPC
from backend.app.models.session import GameSession

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _row_to_dict(row) -> dict:
    """Convert a SQLModel row to a plain dict, parsing JSON fields."""
    d = {}
    for key in row.__fields__:
        val = getattr(row, key, None)
        if key.endswith("_json") and isinstance(val, str):
            try:
                d[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                d[key] = val
        elif hasattr(val, "isoformat"):
            d[key] = val.isoformat()
        else:
            d[key] = val
    return d


@router.get("/session/{session_id}/tables")
async def get_session_tables(
    session_id: str,
    db: AsyncSession = Depends(get_session),
):
    """Return all raw table data associated with a session."""
    session = await db.get(GameSession, session_id)
    if not session:
        return {"error": "Session not found"}

    project_id = session.project_id

    characters = (await db.exec(
        select(Character).where(Character.session_id == session_id)
    )).all()

    messages = (await db.exec(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )).all()

    scenes = (await db.exec(
        select(Scene).where(Scene.session_id == session_id)
    )).all()

    scene_ids = [s.id for s in scenes]
    scene_npcs = []
    if scene_ids:
        scene_npcs = (await db.exec(
            select(SceneNPC).where(SceneNPC.scene_id.in_(scene_ids))  # type: ignore[attr-defined]
        )).all()

    events = (await db.exec(
        select(GameEvent)
        .where(GameEvent.session_id == session_id)
        .order_by(GameEvent.created_at)
    )).all()

    plugin_storage = (await db.exec(
        select(PluginStorage).where(PluginStorage.project_id == project_id)
    )).all()

    game_logs = (await db.exec(
        select(GameLog)
        .where(GameLog.session_id == session_id)
        .order_by(GameLog.created_at)
    )).all()

    game_kvs = (await db.exec(
        select(GameKV).where(GameKV.session_id == session_id)
    )).all()

    game_graphs = (await db.exec(
        select(GameGraph).where(GameGraph.session_id == session_id)
    )).all()

    audit_logs = (await db.exec(
        select(AuditLog)
        .where(AuditLog.session_id == session_id)
        .order_by(AuditLog.created_at.desc())
    )).all()

    return {
        "session": _row_to_dict(session),
        "tables": {
            "characters": [_row_to_dict(r) for r in characters],
            "messages": [_row_to_dict(r) for r in messages],
            "scenes": [_row_to_dict(r) for r in scenes],
            "scene_npcs": [_row_to_dict(r) for r in scene_npcs],
            "events": [_row_to_dict(r) for r in events],
            "plugin_storage": [_row_to_dict(r) for r in plugin_storage],
            "game_logs": [_row_to_dict(r) for r in game_logs],
            "game_kvs": [_row_to_dict(r) for r in game_kvs],
            "game_graphs": [_row_to_dict(r) for r in game_graphs],
            "audit_logs": [_row_to_dict(r) for r in audit_logs],
        },
    }
