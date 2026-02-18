"""Tests for AuditLogger."""
from __future__ import annotations

from pathlib import Path

from backend.app.core.audit_logger import AuditEntry, AuditLogger


class TestAuditLogger:
    def test_log_and_query(self, tmp_path: Path):
        audit = AuditLogger(str(tmp_path))
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
        audit.log(entry)

        results = audit.query()
        assert len(results) == 1
        assert results[0]["plugin"] == "dice-roll"
        assert results[0]["capability"] == "dice.roll"
        assert results[0]["exit_code"] == 0

    def test_query_filter_by_plugin(self, tmp_path: Path):
        audit = AuditLogger(str(tmp_path))
        for plugin in ["dice-roll", "other-plugin", "dice-roll"]:
            audit.log(
                AuditEntry(
                    invocation_id="x",
                    plugin=plugin,
                    capability="test",
                    script="test.py",
                )
            )

        dice_entries = audit.query(plugin="dice-roll")
        assert len(dice_entries) == 2
        assert all(e["plugin"] == "dice-roll" for e in dice_entries)

    def test_query_respects_limit(self, tmp_path: Path):
        audit = AuditLogger(str(tmp_path))
        for i in range(10):
            audit.log(
                AuditEntry(
                    invocation_id=str(i),
                    plugin="test",
                    capability="test",
                    script="test.py",
                )
            )

        results = audit.query(limit=3)
        assert len(results) == 3

    def test_query_empty_dir(self, tmp_path: Path):
        audit = AuditLogger(str(tmp_path / "nonexistent"))
        assert audit.query() == []

    def test_entry_has_timestamp(self, tmp_path: Path):
        audit = AuditLogger(str(tmp_path))
        entry = AuditEntry(
            invocation_id="t1",
            plugin="test",
            capability="test",
            script="test.py",
        )
        audit.log(entry)
        results = audit.query()
        assert len(results) == 1
        assert results[0]["timestamp"]  # Auto-generated
