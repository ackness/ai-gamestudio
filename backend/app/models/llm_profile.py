from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class LlmProfile(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    name: str
    model: str
    api_key_ref: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
