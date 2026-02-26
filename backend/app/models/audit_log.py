from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_session_created", "session_id", "created_at"),
        Index("ix_audit_log_plugin", "plugin_name"),
        Index("ix_audit_log_exit_code", "exit_code"),
    )

    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="gamesession.id")
    invocation_id: str = Field(unique=True)
    plugin_name: str
    capability: str
    script_path: str
    args_json: str = Field(default="{}")
    exit_code: int = 0
    duration_ms: int = 0
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    created_at: datetime = Field(default_factory=_utcnow)
