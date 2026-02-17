from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class Project(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    name: str
    description: str | None = None
    world_doc: str = ""
    init_prompt: str | None = None
    llm_model: str | None = None
    llm_api_key_ref: str | None = None
    llm_api_key: str | None = None
    llm_api_base: str | None = None
    image_model: str | None = None
    image_api_key_ref: str | None = None
    image_api_key: str | None = None
    image_api_base: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
