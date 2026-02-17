from __future__ import annotations

import uuid

from sqlmodel import Field, SQLModel, UniqueConstraint


def _new_id() -> str:
    return str(uuid.uuid4())


class PluginStorage(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("project_id", "plugin_name", "key"),
    )

    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str
    plugin_name: str
    key: str
    value_json: str = Field(default="{}")
