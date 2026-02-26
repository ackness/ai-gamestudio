"""Tests for AuditLogger (database-backed)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.audit_logger import AuditEntry, AuditLogger


class TestAuditLogger:
    @pytest.mark.asyncio
    async def test_log_and_query(self, db_session: AsyncSession, sample_session):
        audit = AuditLogger(db_session)
        entry = AuditEntry(
            invocation_id="abc123",
            plugin="dice-roll",
            capability="dice.roll",
            script="scripts/roll.py",
            args={"expr": "2d6+3"},
            exit_code=0,
            duration_ms=42,
            stdout='{"dice": "2d6+3", "result": 11}',
            stderr="",
        )
        await audit.log(entry, session_id=sample_session.id)

        results = await audit.query(session_id=sample_session.id)
        assert len(results) == 1
        assert results[0].plugin_name == "dice-roll"
        assert results[0].capability == "dice.roll"
        assert results[0].exit_code == 0

    @pytest.mark.asyncio
    async def test_query_filter_by_plugin(self, db_session: AsyncSession, sample_session):
        audit = AuditLogger(db_session)
        for i, plugin in enumerate(["dice-roll", "other-plugin", "dice-roll"]):
            await audit.log(
                AuditEntry(
                    invocation_id=f"x{i}",
                    plugin=plugin,
                    capability="test",
                    script="test.py",
                ),
                session_id=sample_session.id,
            )

        dice_entries = await audit.query(plugin="dice-roll")
        assert len(dice_entries) == 2
        assert all(e.plugin_name == "dice-roll" for e in dice_entries)

    @pytest.mark.asyncio
    async def test_query_respects_limit(self, db_session: AsyncSession, sample_session):
        audit = AuditLogger(db_session)
        for i in range(10):
            await audit.log(
                AuditEntry(
                    invocation_id=f"lim{i}",
                    plugin="test",
                    capability="test",
                    script="test.py",
                ),
                session_id=sample_session.id,
            )

        results = await audit.query(session_id=sample_session.id, limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_empty(self, db_session: AsyncSession, sample_session):
        audit = AuditLogger(db_session)
        results = await audit.query(session_id=sample_session.id)
        assert results == []

    @pytest.mark.asyncio
    async def test_entry_has_timestamp(self, db_session: AsyncSession, sample_session):
        audit = AuditLogger(db_session)
        entry = AuditEntry(
            invocation_id="t1",
            plugin="test",
            capability="test",
            script="test.py",
        )
        await audit.log(entry, session_id=sample_session.id)
        results = await audit.query(session_id=sample_session.id)
        assert len(results) == 1
        assert results[0].created_at is not None

    @pytest.mark.asyncio
    async def test_query_filter_by_exit_code(self, db_session: AsyncSession, sample_session):
        audit = AuditLogger(db_session)
        await audit.log(
            AuditEntry(invocation_id="ok1", plugin="test", capability="t", script="t.py", exit_code=0),
            session_id=sample_session.id,
        )
        await audit.log(
            AuditEntry(invocation_id="fail1", plugin="test", capability="t", script="t.py", exit_code=1),
            session_id=sample_session.id,
        )

        ok = await audit.query(session_id=sample_session.id, exit_code=0)
        assert len(ok) == 1
        assert ok[0].exit_code == 0

        failed = await audit.query(session_id=sample_session.id, exit_code=1)
        assert len(failed) == 1
        assert failed[0].exit_code == 1
