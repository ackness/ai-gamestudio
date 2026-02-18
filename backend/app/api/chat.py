from __future__ import annotations

import asyncio
import copy
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Protocol

from loguru import logger

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.core.block_parser import strip_blocks
from backend.app.core.config import settings
from backend.app.core.game_state import GameStateManager
from backend.app.db.engine import engine
from backend.app.models.session import GameSession
from backend.app.services.chat_service import process_message

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
        "dir": direction,  # "send" (backend→frontend) or "recv" (frontend→backend)
        "payload": safe_payload,
    }
    buf = _session_logs.setdefault(session_id, deque(maxlen=_MAX_LOG_ENTRIES))
    buf.append(entry)
    # Push to any live subscribers
    for q in _log_subscribers.get(session_id, []):
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            pass
    _cleanup_log_sessions()


class EventSink(Protocol):
    async def send_json(self, data: dict[str, Any]) -> None: ...


class HttpEventCollector:
    """Collect backend events and return them in one HTTP response."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        self.events.append(data)


def _extract_llm_overrides(data: dict[str, Any]) -> dict[str, str] | None:
    raw = data.get("llm_overrides")
    if not isinstance(raw, dict):
        return None

    model = str(raw.get("model") or "").strip()
    api_key = str(raw.get("api_key") or "").strip()
    api_base = str(raw.get("api_base") or "").strip()

    overrides: dict[str, str] = {}
    if model:
        overrides["model"] = model
    if api_key:
        overrides["api_key"] = api_key
    if api_base:
        overrides["api_base"] = api_base
    return overrides or None


def _extract_image_overrides(data: dict[str, Any]) -> dict[str, str] | None:
    raw = data.get("image_overrides")
    if not isinstance(raw, dict):
        return None

    model = str(raw.get("model") or "").strip()
    api_key = str(raw.get("api_key") or "").strip()
    api_base = str(raw.get("api_base") or "").strip()

    overrides: dict[str, str] = {}
    if model:
        overrides["model"] = model
    if api_key:
        overrides["api_key"] = api_key
    if api_base:
        overrides["api_base"] = api_base
    return overrides or None


async def _stream_process_message(
    sink: EventSink,
    session_id: str,
    content: str,
    *,
    save_user_msg: bool = True,
    save_assistant_msg: bool = True,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Run process_message and stream results to a transport sink."""
    full_response = ""
    pending_blocks: list[dict] = []
    turn_id: str | None = None
    saved_message_id: str | None = None

    async for event in process_message(
        session_id,
        content,
        save_user_msg=save_user_msg,
        save_assistant_msg=save_assistant_msg,
        llm_overrides=llm_overrides,
        image_overrides=image_overrides,
    ):
        event_turn_id = event.get("turn_id")
        if isinstance(event_turn_id, str) and event_turn_id:
            turn_id = event_turn_id

        if event["type"] == "chunk":
            full_response += event["content"]
            await sink.send_json(
                {
                    "type": "chunk",
                    "content": event["content"],
                    "turn_id": turn_id,
                }
            )
        elif event["type"] == "error":
            _add_log(session_id, "send", event)
            await sink.send_json(event)
            return
        elif event["type"] == "_message_saved":
            saved_message_id = event.get("message_id")
        else:
            pending_blocks.append(event)

    if turn_id is None:
        turn_id = str(uuid.uuid4())

    # Send done event with blocks stripped (blocks are forwarded separately below)
    clean_content = strip_blocks(full_response)
    done_event: dict[str, Any] = {
        "type": "done",
        "content": clean_content,
        "turn_id": turn_id,
        "has_blocks": bool(pending_blocks),
    }
    if saved_message_id:
        done_event["message_id"] = saved_message_id
    _add_log(
        session_id,
        "send",
        {
            "type": "done",
            "turn_id": turn_id,
            "content_length": len(full_response),
            "preview": full_response[:300],
        },
    )
    await sink.send_json(done_event)

    # Forward all collected blocks to the client
    for block in pending_blocks:
        block_event = {
            "type": block["type"],
            "data": block["data"],
            "block_id": block.get("block_id"),
            "turn_id": block.get("turn_id", turn_id),
        }
        _add_log(session_id, "send", block_event)
        await sink.send_json(block_event)

    turn_end_event = {"type": "turn_end", "turn_id": turn_id}
    _add_log(session_id, "send", turn_end_event)
    await sink.send_json(turn_end_event)


# ---------------------------------------------------------------------------
# Force trigger: hidden prompt to force LLM to output specific block types
# ---------------------------------------------------------------------------
_FORCE_TRIGGER_PROMPTS: dict[str, str] = {
    "guide": (
        "请根据当前场景、角色状态和最近的对话内容，"
        "直接输出一个 json:guide 代码块，为玩家提供行动建议。"
        "不要输出任何叙事文字或解释，只输出代码块本身。\n\n"
        "格式：\n"
        "```json:guide\n"
        '{"categories": [{"style": "safe", "label": "稳妥", "suggestions": ["建议1"]}, ...]}\n'
        "```"
    ),
    "state_update": (
        "请根据最近的叙事内容，检查角色属性和物品是否需要更新。"
        "如果有变化，输出一个 json:state_update 代码块。"
        "不要输出叙事文字，只输出代码块。"
    ),
    "scene_update": (
        "请根据当前叙事内容，输出一个 json:scene_update 代码块描述当前场景。"
        "不要输出叙事文字，只输出代码块。"
    ),
    "story_image": (
        "请根据当前场景、角色状态和最近剧情，直接输出一个 json:story_image 代码块用于生成配图。"
        "不要输出任何叙事文字或解释，只输出代码块本身。\n\n"
        "格式：\n"
        "```json:story_image\n"
        '{'
        '"title":"场景配图",'
        '"story_background":"近期剧情背景（1-3句）",'
        '"prompt":"当前镜头画面描述",'
        '"continuity_notes":"人物/道具连续性提示",'
        '"reference_image_ids":[],'
        '"layout_preference":"auto",'
        '"scene_frames":[]'
        "}\n"
        "```"
    ),
}


async def _handle_force_trigger(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle force trigger — send hidden prompt to force specific block output."""
    block_type = data.get("block_type", "")
    prompt = _FORCE_TRIGGER_PROMPTS.get(block_type)
    if not prompt:
        await sink.send_json(
            {"type": "error", "content": f"Unknown trigger type: {block_type}"}
        )
        return

    logger.debug("Force trigger [{}] for session {}", block_type, session_id)

    await _stream_process_message(
        sink,
        session_id,
        prompt,
        save_user_msg=False,
        save_assistant_msg=False,
        llm_overrides=llm_overrides,
        image_overrides=image_overrides,
    )


async def _handle_generate_message_image(
    sink: EventSink,
    session_id: str,
    data: dict,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle per-message image generation — no LLM round-trip."""
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    from backend.app.models.message import Message
    from backend.app.services.image_service import generate_message_image

    message_id = data.get("message_id", "")
    if not message_id:
        await sink.send_json(
            {"type": "error", "content": "message_id is required"}
        )
        return

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        msg = await db.get(Message, message_id)
        if not msg or msg.session_id != session_id or msg.role != "assistant":
            await sink.send_json(
                {
                    "type": "message_image",
                    "message_id": message_id,
                    "data": {
                        "status": "error",
                        "message_id": message_id,
                        "error": "Invalid message_id",
                    },
                }
            )
            return

        game_session = await db.get(GameSession, session_id)
        if not game_session:
            await sink.send_json(
                {"type": "error", "content": "Session not found"}
            )
            return

        # Send loading event
        loading_event = {"type": "message_image_loading", "message_id": message_id}
        _add_log(session_id, "send", loading_event)
        await sink.send_json(loading_event)

        # Load recent assistant messages for context
        context_rows = list(
            (
                await db.exec(
                    select(Message)
                    .where(
                        Message.session_id == session_id,
                        Message.role == "assistant",
                        Message.created_at < msg.created_at,
                    )
                    .order_by(Message.created_at.desc())  # type: ignore[arg-type]
                    .limit(5)
                )
            ).all()
        )
        context_messages = [
            row.content for row in reversed(context_rows) if row.content.strip()
        ]

        try:
            result = await generate_message_image(
                db,
                project_id=game_session.project_id,
                session_id=session_id,
                message_id=message_id,
                message_content=msg.content,
                context_messages=context_messages,
                autocommit=True,
                image_overrides=image_overrides,
            )

            image_event = {
                "type": "message_image",
                "message_id": message_id,
                "data": result,
            }
            _add_log(session_id, "send", image_event)
            await sink.send_json(image_event)
        except Exception:
            logger.exception("Error generating message image for {}", message_id)
            error_event = {
                "type": "message_image",
                "message_id": message_id,
                "data": {
                    "status": "error",
                    "message_id": message_id,
                    "error": "Image generation failed",
                },
            }
            _add_log(session_id, "send", error_event)
            await sink.send_json(error_event)


async def _session_exists(session_id: str) -> bool:
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    async with SQLModelAsyncSession(engine) as session:
        game_session = await session.get(GameSession, session_id)
        return bool(game_session)


async def _dispatch_incoming_message(
    sink: EventSink,
    session_id: str,
    data: dict[str, Any],
) -> None:
    msg_type = str(data.get("type", "message"))
    llm_overrides = _extract_llm_overrides(data)
    image_overrides = _extract_image_overrides(data)

    try:
        if msg_type == "message":
            content = str(data.get("content", "")).strip()
            if not content:
                await sink.send_json({"type": "error", "content": "Empty message"})
                return
            await _stream_process_message(
                sink,
                session_id,
                content,
                llm_overrides=llm_overrides,
                image_overrides=image_overrides,
            )
        elif msg_type == "init_game":
            await _handle_init_game(
                sink,
                session_id,
                data,
                llm_overrides=llm_overrides,
                image_overrides=image_overrides,
            )
        elif msg_type == "form_submit":
            await _handle_form_submit(
                sink,
                session_id,
                data,
                llm_overrides=llm_overrides,
                image_overrides=image_overrides,
            )
        elif msg_type == "character_edit":
            await _handle_character_edit(
                sink,
                session_id,
                data,
                llm_overrides=llm_overrides,
                image_overrides=image_overrides,
            )
        elif msg_type == "scene_switch":
            await _handle_scene_switch(
                sink,
                session_id,
                data,
                llm_overrides=llm_overrides,
                image_overrides=image_overrides,
            )
        elif msg_type == "confirm":
            await _handle_confirm(
                sink,
                session_id,
                data,
                llm_overrides=llm_overrides,
                image_overrides=image_overrides,
            )
        elif msg_type == "block_response":
            await _handle_block_response(
                sink,
                session_id,
                data,
                llm_overrides=llm_overrides,
                image_overrides=image_overrides,
            )
        elif msg_type == "force_trigger":
            await _handle_force_trigger(
                sink,
                session_id,
                data,
                llm_overrides=llm_overrides,
                image_overrides=image_overrides,
            )
        elif msg_type == "generate_message_image":
            await _handle_generate_message_image(
                sink,
                session_id,
                data,
                image_overrides=image_overrides,
            )
        else:
            await sink.send_json(
                {"type": "error", "content": f"Unknown message type: {msg_type}"}
            )
    except Exception:
        logger.exception("Error processing {} message", msg_type)
        await sink.send_json(
            {"type": "error", "content": "Internal server error"}
        )


@router.post("/api/chat/{session_id}/command")
async def chat_command(session_id: str, data: dict[str, Any]):
    """HTTP fallback for chat commands (Vercel-compatible, no WebSocket required)."""
    if not await _session_exists(session_id):
        return {"events": [{"type": "error", "content": "Session not found"}]}

    payload = data if isinstance(data, dict) else {}
    _add_log(session_id, "recv", payload)

    collector = HttpEventCollector()
    await _dispatch_incoming_message(collector, session_id, payload)
    return {"events": collector.events}


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    if not await _session_exists(session_id):
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "content": "Invalid JSON"}
                )
                continue
            if not isinstance(data, dict):
                await websocket.send_json(
                    {"type": "error", "content": "Invalid payload"}
                )
                continue

            _add_log(session_id, "recv", data)
            await _dispatch_incoming_message(websocket, session_id, data)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session {}", session_id)
        _touch_log_session(session_id)
        _cleanup_log_sessions()


DEFAULT_INIT_PROMPT = (
    "玩家开始了一场新游戏。请根据世界观文档生成一段沉浸式的开场叙事。"
    "在叙事末尾包含一个 json:character_sheet 代码块用于角色创建，"
    "其中 editable_fields 需包含 'name'。"
    "同时包含一个 json:scene_update 代码块来建立起始场景。"
)


async def _handle_init_game(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle game initialization — transition to character_creation or playing."""
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
    from backend.app.models.project import Project

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        game_session = await db.get(GameSession, session_id)
        if not game_session:
            await sink.send_json({"type": "error", "content": "Session not found"})
            return

        project = await db.get(Project, game_session.project_id)
        if not project:
            await sink.send_json({"type": "error", "content": "Project not found"})
            return

        init_prompt = project.init_prompt or DEFAULT_INIT_PROMPT

        # Transition phase
        game_session.phase = "character_creation"
        game_session.updated_at = datetime.now(timezone.utc)
        db.add(game_session)
        await db.commit()

    # Notify frontend of phase change
    phase_event = {"type": "phase_change", "data": {"phase": "character_creation"}}
    _add_log(session_id, "send", phase_event)
    await sink.send_json(phase_event)

    # Trigger DM to generate opening narration
    await _stream_process_message(
        sink,
        session_id,
        init_prompt,
        llm_overrides=llm_overrides,
        image_overrides=image_overrides,
    )


async def _handle_form_submit(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle form submission — may trigger character creation or other actions."""
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    form_id = data.get("form_id", "")
    values = data.get("values", {})

    if form_id == "character_creation":
        # Character creation form — create character and transition phase
        async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
            state_mgr = GameStateManager(db)
            game_session = await db.get(GameSession, session_id)
            if not game_session:
                await sink.send_json({"type": "error", "content": "Session not found"})
                return

            # Create character
            char = await state_mgr.upsert_character(
                session_id,
                {
                    "name": values.get("name", "Unknown"),
                    "role": "player",
                    **{k: v for k, v in values.items() if k != "name"},
                },
            )

            # Transition to playing
            game_session.phase = "playing"
            game_session.updated_at = datetime.now(timezone.utc)
            db.add(game_session)
            await db.commit()

            # Notify frontend
            await sink.send_json(
                {"type": "phase_change", "data": {"phase": "playing"}}
            )
            await sink.send_json(
                {"type": "state_update", "data": {"characters": [{"id": char.id, "name": char.name, "role": char.role}]}}
            )

        # Trigger DM to begin the adventure
        formatted = ", ".join(f"{k}={v}" for k, v in values.items())
        content = f"【角色创建完成】{formatted}。请开始冒险叙事。"
        await _stream_process_message(
            sink,
            session_id,
            content,
            llm_overrides=llm_overrides,
            image_overrides=image_overrides,
        )
    else:
        # Generic form submission — format as user message
        formatted = ", ".join(f"{k}={v}" for k, v in values.items())
        content = f"【表单提交】{form_id}: {formatted}"
        await _stream_process_message(
            sink,
            session_id,
            content,
            llm_overrides=llm_overrides,
            image_overrides=image_overrides,
        )


async def _handle_character_edit(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle character edits — no LLM call, direct DB update."""
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    character_id = data.get("character_id")
    changes = data.get("changes", {})

    if not character_id:
        await sink.send_json(
            {"type": "error", "content": "character_id is required"}
        )
        return

    if not changes:
        # No actual edits — acknowledge the confirmation
        await sink.send_json(
            {"type": "character_confirmed", "data": {"character_id": character_id}}
        )

        # Still need to check for character_creation → playing transition
        async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
            game_session = await db.get(GameSession, session_id)
            if game_session and game_session.phase == "character_creation":
                game_session.phase = "playing"
                game_session.updated_at = datetime.now(timezone.utc)
                db.add(game_session)
                await db.commit()

                await sink.send_json(
                    {"type": "phase_change", "data": {"phase": "playing"}}
                )

                # Trigger DM to begin the adventure
                content = "【角色确认完成】请开始冒险叙事。"
                await _stream_process_message(
                    sink,
                    session_id,
                    content,
                    llm_overrides=llm_overrides,
                    image_overrides=image_overrides,
                )
                return

        # Not transitioning — send done to unblock the frontend
        done_event = {"type": "done", "content": ""}
        _add_log(session_id, "send", done_event)
        await sink.send_json(done_event)
        return

    transitioned_from_creation = False

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        state_mgr = GameStateManager(db)
        game_session = await db.get(GameSession, session_id)
        if not game_session:
            await sink.send_json({"type": "error", "content": "Session not found"})
            return

        # Update character
        char_data = {"character_id": character_id, **changes}
        char = await state_mgr.upsert_character(session_id, char_data)

        # Save system message recording the edit
        change_desc = ", ".join(f"{k}→{v}" for k, v in changes.items())
        await state_mgr.add_message(
            session_id,
            "system",
            f"玩家修改了角色 {char.name}: {change_desc}",
            message_type="system_event",
        )

        # Check if this completes character creation
        if game_session.phase == "character_creation":
            transitioned_from_creation = True
            game_session.phase = "playing"
            game_session.updated_at = datetime.now(timezone.utc)
            db.add(game_session)
            await db.commit()

            await sink.send_json(
                {"type": "phase_change", "data": {"phase": "playing"}}
            )

    # Push state_update back to client
    await sink.send_json({
        "type": "state_update",
        "data": {
            "characters": [{
                "id": char.id,
                "name": char.name,
                "role": char.role,
                "attributes": json.loads(char.attributes_json) if char.attributes_json else {},
                "inventory": json.loads(char.inventory_json) if char.inventory_json else [],
            }]
        },
    })

    if transitioned_from_creation:
        # Character creation completed — trigger DM to begin the adventure
        formatted = ", ".join(f"{k}={v}" for k, v in changes.items())
        content = f"【角色编辑完成】{char.name}: {formatted}。请开始冒险叙事。"
        await _stream_process_message(
            sink,
            session_id,
            content,
            llm_overrides=llm_overrides,
            image_overrides=image_overrides,
        )
    else:
        # No LLM call needed — send done to unblock the frontend
        done_event = {"type": "done", "content": ""}
        _add_log(session_id, "send", done_event)
        await sink.send_json(done_event)


async def _handle_scene_switch(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle scene switching — update current scene and trigger DM narration."""
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    scene_id = data.get("scene_id")
    if not scene_id:
        await sink.send_json(
            {"type": "error", "content": "scene_id required"}
        )
        return

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        from backend.app.models.scene import Scene

        scene = await db.get(Scene, scene_id)
        if not scene:
            await sink.send_json(
                {"type": "error", "content": "Scene not found"}
            )
            return

        scene_name = scene.name

    content = f"我前往{scene_name}"
    await _stream_process_message(
        sink,
        session_id,
        content,
        llm_overrides=llm_overrides,
        image_overrides=image_overrides,
    )


async def _handle_confirm(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle generic confirmations."""
    action = data.get("action", "")
    action_data = data.get("data", {})
    content = f"我确认{action}"
    if action_data:
        details = ", ".join(f"{k}={v}" for k, v in action_data.items())
        content += f" ({details})"
    await _stream_process_message(
        sink,
        session_id,
        content,
        llm_overrides=llm_overrides,
        image_overrides=image_overrides,
    )


async def _handle_block_response(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle a user's response to an interactive block (requires_response=true).

    The response is stored as a system message with block_response metadata,
    then injected into the next LLM context. Also triggers a DM continuation.
    """
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    block_type = data.get("block_type", "unknown")
    block_id = data.get("block_id", "")
    response_data = data.get("data", {})

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        game_session = await db.get(GameSession, session_id)
        if not game_session:
            await sink.send_json({"type": "error", "content": "Session not found"})
            return

        if (
            block_type == "story_image"
            and isinstance(response_data, dict)
            and str(response_data.get("action", "")).strip().lower() == "regenerate"
        ):
            from backend.app.services.image_service import (
                generate_story_image,
                regenerate_story_image,
            )

            image_id = str(response_data.get("image_id") or "").strip()
            reason = str(response_data.get("reason") or "").strip()

            turn_id = str(uuid.uuid4())
            if image_id:
                regenerated = await regenerate_story_image(
                    db,
                    project_id=game_session.project_id,
                    session_id=session_id,
                    image_id=image_id,
                    reason=reason or None,
                    turn_id=turn_id,
                    autocommit=False,
                    image_overrides=image_overrides,
                )
            else:
                title = str(response_data.get("title") or "Story Image (regen)")
                story_background = str(response_data.get("story_background") or "")
                prompt = str(response_data.get("prompt") or "")
                continuity_notes = str(response_data.get("continuity_notes") or "")
                if reason:
                    if continuity_notes:
                        continuity_notes = (
                            f"{continuity_notes}. Regeneration note: {reason}"
                        )
                    else:
                        continuity_notes = f"Regeneration note: {reason}"
                refs_raw = response_data.get("reference_image_ids")
                refs = (
                    [str(item).strip() for item in refs_raw if str(item).strip()]
                    if isinstance(refs_raw, list)
                    else []
                )
                scene_frames_raw = response_data.get("scene_frames")
                scene_frames = (
                    [str(item).strip() for item in scene_frames_raw if str(item).strip()]
                    if isinstance(scene_frames_raw, list)
                    else []
                )
                layout_preference = str(response_data.get("layout_preference") or "auto")
                regenerated = await generate_story_image(
                    db,
                    project_id=game_session.project_id,
                    session_id=session_id,
                    title=title,
                    story_background=story_background,
                    prompt=prompt,
                    continuity_notes=continuity_notes,
                    reference_image_ids=refs,
                    scene_frames=scene_frames,
                    layout_preference=layout_preference,
                    turn_id=turn_id,
                    autocommit=False,
                    image_overrides=image_overrides,
                )

            state_mgr = GameStateManager(db)
            regen_block_id = f"{turn_id}:0"
            await state_mgr.add_message(
                session_id,
                "assistant",
                "（图片已重新生成）" if regenerated.get("status") == "ok" else "（图片重生成失败）",
                message_type="narration",
                metadata={
                    "blocks": [
                        {
                            "type": "story_image",
                            "data": regenerated,
                            "block_id": regen_block_id,
                        }
                    ]
                },
                raw_content=(
                    "```json:story_image\n"
                    + json.dumps(regenerated, ensure_ascii=False)
                    + "\n```"
                ),
            )

            done_event = {
                "type": "done",
                "content": "（图片已重新生成）" if regenerated.get("status") == "ok" else "（图片重生成失败）",
                "turn_id": turn_id,
                "has_blocks": True,
            }
            _add_log(session_id, "send", done_event)
            await sink.send_json(done_event)

            block_event = {
                "type": "story_image",
                "data": regenerated,
                "block_id": regen_block_id,
                "turn_id": turn_id,
            }
            _add_log(session_id, "send", block_event)
            await sink.send_json(block_event)

            turn_end_event = {"type": "turn_end", "turn_id": turn_id}
            _add_log(session_id, "send", turn_end_event)
            await sink.send_json(turn_end_event)
            return

        state_mgr = GameStateManager(db)

        # Store as a special system message for context injection
        await state_mgr.add_message(
            session_id,
            "system",
            f"[block_response:{block_type}] {json.dumps(response_data, ensure_ascii=False)}",
            message_type="system_event",
            metadata={
                "block_response": True,
                "block_type": block_type,
                "block_id": block_id,
                "response_data": response_data,
            },
        )

    # Format as a contextual message for the DM and trigger continuation
    chosen = response_data.get("chosen") or response_data.get("value") or json.dumps(response_data, ensure_ascii=False)
    content = f"[对 {block_type} 的回应] {chosen}"
    await _stream_process_message(
        sink,
        session_id,
        content,
        llm_overrides=llm_overrides,
        image_overrides=image_overrides,
    )


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
        # Return lightweight index without full generation prompts/debug data
        return [
            {
                "image_id": row.get("image_id"),
                "message_id": row.get("message_id"),
                "image_url": row.get("image_url"),
                "title": row.get("title"),
                "status": "ok" if row.get("image_url") else "error",
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]


@router.websocket("/ws/debug-log/{session_id}")
async def websocket_debug_log(websocket: WebSocket, session_id: str):
    """Stream debug log entries in real time."""
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
