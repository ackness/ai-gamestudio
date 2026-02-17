from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class GameSession(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    status: str = Field(default="active")  # active / paused / ended
    phase: str = Field(default="init")  # init / character_creation / playing / ended
    game_state_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
