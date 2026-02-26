from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StorageLog(SQLModel, table=True):
    __tablename__ = "game_log"  # keep table name for DB compat
    __table_args__ = (
        Index("ix_game_log_session_collection_created", "session_id", "collection", "created_at"),
    )

    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="gamesession.id")
    collection: str
    entry_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=_utcnow)
