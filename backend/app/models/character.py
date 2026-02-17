from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class Character(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="gamesession.id")
    name: str
    role: str = Field(default="npc")  # player / npc
    description: str | None = None
    personality: str | None = None
    attributes_json: str = Field(default="{}")
    inventory_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
