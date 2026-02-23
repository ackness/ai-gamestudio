from __future__ import annotations

import asyncio
import copy
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.core.access_key import is_request_authorized
from backend.app.core.config import settings
from backend.app.db.engine import engine
from backend.app.models.session import GameSession

router = APIRouter()

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


def _add_log(session_id: str, direction: str, payload: dict) -> None:
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


# ---------------------------------------------------------------------------
# Debug log endpoints
# ---------------------------------------------------------------------------

@router.get("/api/sessions/{session_id}/debug-log")
async def get_debug_log(session_id: str):
    """Return recent WebSocket events for a session (for the debug panel)."""
    _touch_log_session(session_id)
    _cleanup_log_sessions()
    buf = _session_logs.get(session_id, deque())
    return list(buf)


@router.get("/api/sessions/{session_id}/story-images")
async def get_session_story_images_endpoint(session_id: str):
    """Return story images for a session (for page reload hydration)."""
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    from backend.app.services.image_service import get_session_story_images

    async with SQLModelAsyncSession(engine) as db:
        game_session = await db.get(GameSession, session_id)
        if not game_session:
            return []
        rows = await get_session_story_images(
            db, project_id=game_session.project_id, session_id=session_id
        )
        return [
            {
                "image_id": row.get("image_id"),
                "message_id": row.get("message_id"),
                "image_url": row.get("image_url"),
                "title": row.get("title"),
                "status": "ok" if row.get("image_url") else "error",
                "created_at": row.get("created_at"),
                # Fields for image detail viewer
                "story_background": row.get("story_background"),
                "prompt": row.get("prompt"),
                "continuity_notes": row.get("continuity_notes"),
                "reference_image_ids": row.get("reference_image_ids"),
                "scene_frames": row.get("scene_frames"),
                "layout_preference": row.get("layout_preference"),
                "can_regenerate": True,
                "provider_model": row.get("model"),
                "provider_note": row.get("provider_note"),
                "settings_applied": row.get("runtime_settings"),
                "debug": {
                    "generated_prompt": row.get("generation_prompt"),
                    "enhanced_prompt": row.get("enhanced_prompt"),
                    "world_lore_excerpt": row.get("world_lore_excerpt"),
                    "text_world_state": row.get("text_world_state"),
                    "runtime_settings": row.get("runtime_settings"),
                    "provider_model": row.get("model"),
                    "api_base": row.get("api_base"),
                },
            }
            for row in rows
        ]


@router.get("/api/sessions/{session_id}/debug-prompt")
async def get_debug_prompt(session_id: str):
    """Return the fully assembled prompt messages that would be sent to the LLM.

    This builds the same TurnContext and runs the same assemble_prompt logic
    as a real chat turn, but does NOT call the LLM.  Useful for debugging
    prompt construction, language enforcement, plugin injections, etc.
    """
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    from backend.app.core.game_state import GameStateManager
    from backend.app.core.llm_config import resolve_llm_config
    from backend.app.services.prompt_assembly import assemble_prompt
    from backend.app.services.turn_context import build_turn_context

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        state_mgr = GameStateManager(db, autocommit=False)
        ctx = await build_turn_context(db, session_id, state_mgr)
        if ctx is None:
            return {"error": "Session or project not found"}

        messages = assemble_prompt(ctx, "(debug preview — no user message)", save_user_msg=True)
        config = resolve_llm_config(project=ctx.project)

        return {
            "model": config.model,
            "api_base": config.api_base,
            "source": config.source,
            "enabled_plugins": ctx.enabled_names,
            "messages": [
                {"role": m["role"], "content": m["content"], "length": len(m["content"])}
                for m in messages
            ],
            "total_chars": sum(len(m["content"]) for m in messages),
            "message_count": len(messages),
        }


@router.websocket("/ws/debug-log/{session_id}")
async def websocket_debug_log(websocket: WebSocket, session_id: str):
    """Stream debug log entries in real time."""
    if not is_request_authorized(websocket.headers, websocket.query_params):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    _touch_log_session(session_id)
    _cleanup_log_sessions()
    subs = _log_subscribers.setdefault(session_id, [])
    subs.append(queue)
    try:
        while True:
            entry = await queue.get()
            await websocket.send_json(entry)
    except WebSocketDisconnect:
        pass
    finally:
        subs.remove(queue)
        _touch_log_session(session_id)
        _cleanup_log_sessions()
