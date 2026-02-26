from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StorageGraph(SQLModel, table=True):
    __tablename__ = "game_graph"  # keep table name for DB compat
    __table_args__ = (UniqueConstraint("session_id", "from_id", "to_id", "relation"),)

    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="gamesession.id")
    from_id: str
    to_id: str
    relation: str
    data_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=_utcnow)
