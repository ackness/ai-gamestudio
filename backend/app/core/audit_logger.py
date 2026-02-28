"""AuditLogger: database-backed audit trail for plugin capability invocations."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.audit_log import AuditLog


@dataclass
class AuditEntry:
    invocation_id: str
    plugin: str
    capability: str
    script: str
    args: dict[str, Any] = field(default_factory=dict)
    exit_code: int = 0
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """Database-backed audit logger for plugin invocations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log(self, entry: AuditEntry, *, session_id: str) -> None:
        """Persist an audit entry to the database."""
        try:
            audit_log = AuditLog(
                session_id=session_id,
                invocation_id=entry.invocation_id,
                plugin_name=entry.plugin,
                capability=entry.capability,
                script_path=entry.script,
                args_json=json.dumps(entry.args, ensure_ascii=False),
                exit_code=entry.exit_code,
                duration_ms=entry.duration_ms,
                stdout=entry.stdout[:2000],
                stderr=entry.stderr[:2000],
            )
            self._db.add(audit_log)
            await self._db.commit()
        except Exception:
            logger.warning("Failed to write audit entry for {}.{}", entry.plugin, entry.capability)
            await self._db.rollback()

    async def query(
        self,
        *,
        session_id: str | None = None,
        plugin: str | None = None,
        exit_code: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Query audit logs with optional filters."""
        stmt = select(AuditLog)

        if session_id:
            stmt = stmt.where(AuditLog.session_id == session_id)
        if plugin:
            stmt = stmt.where(AuditLog.plugin_name == plugin)
        if exit_code is not None:
            stmt = stmt.where(AuditLog.exit_code == exit_code)

        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)

        result = await self._db.exec(stmt)
        return list(result.all())
