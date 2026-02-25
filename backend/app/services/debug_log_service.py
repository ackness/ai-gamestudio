from __future__ import annotations

import asyncio
import copy
from collections import deque
from datetime import datetime, timezone

from backend.app.core.config import settings

# ---------------------------------------------------------------------------
# In-memory conversation log ring buffer (per session, kept for debug panel)
# ---------------------------------------------------------------------------
_MAX_LOG_ENTRIES = 200
_MAX_LOG_SESSIONS = max(1, int(settings.MAX_LOG_SESSIONS or 200))
_LOG_TTL_SECONDS = max(60, int(settings.LOG_TTL_MINUTES or 30) * 60)
_session_logs: dict[str, deque[dict]] = {}
_log_subscribers: dict[str, list[asyncio.Queue]] = {}
_session_last_active_at: dict[str, datetime] = {}


def _drop_log_session(session_id: str) -> None:
    _session_logs.pop(session_id, None)
    _session_last_active_at.pop(session_id, None)
    if not _log_subscribers.get(session_id):
        _log_subscribers.pop(session_id, None)


def _touch_log_session(session_id: str) -> None:
    _session_last_active_at[session_id] = datetime.now(timezone.utc)


def _cleanup_log_sessions() -> None:
    now = datetime.now(timezone.utc)

    stale_ids = []
    for sid, last_active in list(_session_last_active_at.items()):
        if _log_subscribers.get(sid):
            continue
        age = (now - last_active).total_seconds()
        if age >= _LOG_TTL_SECONDS:
            stale_ids.append(sid)
    for sid in stale_ids:
        _drop_log_session(sid)

    if len(_session_logs) <= _MAX_LOG_SESSIONS:
        return

    candidates = [
        sid for sid in _session_logs.keys() if not _log_subscribers.get(sid)
    ]
    candidates.sort(
        key=lambda sid: _session_last_active_at.get(sid, datetime(1970, 1, 1, tzinfo=timezone.utc))
    )
    while len(_session_logs) > _MAX_LOG_SESSIONS and candidates:
        sid = candidates.pop(0)
        _drop_log_session(sid)


def add_debug_log(session_id: str, direction: str, payload: dict) -> None:
    """Append an entry to the session's debug log and notify subscribers."""
    safe_payload = copy.deepcopy(payload)
    llm_overrides = safe_payload.get("llm_overrides")
    if isinstance(llm_overrides, dict) and llm_overrides.get("api_key"):
        llm_overrides["api_key"] = "***"
    image_overrides = safe_payload.get("image_overrides")
    if isinstance(image_overrides, dict) and image_overrides.get("api_key"):
        image_overrides["api_key"] = "***"
    _touch_log_session(session_id)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "dir": direction,
        "payload": safe_payload,
    }
    buf = _session_logs.setdefault(session_id, deque(maxlen=_MAX_LOG_ENTRIES))
    buf.append(entry)
    for q in _log_subscribers.get(session_id, []):
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            pass
    _cleanup_log_sessions()
