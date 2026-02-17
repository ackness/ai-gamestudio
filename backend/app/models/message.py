from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class Message(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="gamesession.id")
    role: str  # user / assistant / system
    content: str
    raw_content: str | None = None
    message_type: str = Field(default="chat")  # chat / narration / system_event
    scene_id: str | None = Field(default=None, foreign_key="scene.id")
    metadata_json: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
