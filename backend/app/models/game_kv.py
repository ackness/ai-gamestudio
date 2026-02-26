from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StorageKV(SQLModel, table=True):
    __tablename__ = "game_kv"  # keep table name for DB compat
    __table_args__ = (UniqueConstraint("session_id", "collection", "key"),)

    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="gamesession.id")
    collection: str
    key: str
    value_json: str = Field(default="{}")
    updated_at: datetime = Field(default_factory=_utcnow)
