from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class GameEvent(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="gamesession.id")
    event_type: str  # quest/combat/social/world/system
    name: str
    description: str
    status: str = Field(default="active")  # active/evolved/resolved/ended
    parent_event_id: str | None = Field(default=None, foreign_key="gameevent.id")
    source: str = Field(default="dm")  # dm/plugin:<name>/system
    visibility: str = Field(default="known")  # known/hidden
    metadata_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
