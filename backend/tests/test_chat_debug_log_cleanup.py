from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.api import debug_log as chat


@pytest.fixture(autouse=True)
def _clear_debug_log_state():
    chat._session_logs.clear()
    chat._log_subscribers.clear()
    chat._session_last_active_at.clear()
    yield
    chat._session_logs.clear()
    chat._log_subscribers.clear()
    chat._session_last_active_at.clear()


def test_cleanup_removes_stale_sessions(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "_LOG_TTL_SECONDS", 1)
    monkeypatch.setattr(chat, "_MAX_LOG_SESSIONS", 10)

    chat._add_log("session-a", "recv", {"type": "message"})
    chat._session_last_active_at["session-a"] = datetime.now(timezone.utc) - timedelta(
        seconds=5
    )

    chat._cleanup_log_sessions()

    assert "session-a" not in chat._session_logs
    assert "session-a" not in chat._session_last_active_at


def test_cleanup_enforces_max_sessions(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "_LOG_TTL_SECONDS", 99999)
    monkeypatch.setattr(chat, "_MAX_LOG_SESSIONS", 2)

    chat._add_log("s1", "recv", {"n": 1})
    chat._session_last_active_at["s1"] = datetime.now(timezone.utc) - timedelta(
        seconds=10
    )
    chat._add_log("s2", "recv", {"n": 2})
    chat._add_log("s3", "recv", {"n": 3})

    assert len(chat._session_logs) <= 2
    assert "s1" not in chat._session_logs


def test_cleanup_keeps_sessions_with_subscribers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "_LOG_TTL_SECONDS", 1)
    monkeypatch.setattr(chat, "_MAX_LOG_SESSIONS", 10)

    chat._add_log("live", "recv", {"type": "message"})
    chat._session_last_active_at["live"] = datetime.now(timezone.utc) - timedelta(
        seconds=5
    )
    chat._log_subscribers["live"] = [asyncio.Queue()]

    chat._cleanup_log_sessions()

    assert "live" in chat._session_logs
