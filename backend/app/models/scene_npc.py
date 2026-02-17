from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class SceneNPC(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    scene_id: str = Field(foreign_key="scene.id")
    character_id: str = Field(foreign_key="character.id")
    role_in_scene: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
