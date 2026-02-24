from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Protocol

from loguru import logger

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.core.access_key import is_request_authorized
from backend.app.db.engine import engine
from backend.app.models.session import GameSession
from backend.app.services.chat_service import process_message

from backend.app.api.debug_log import _add_log, _touch_log_session, _cleanup_log_sessions
from backend.app.services.command_handlers import (
    _handle_init_game,
    _handle_form_submit,
    _handle_character_edit,
    _handle_scene_switch,
    _handle_confirm,
    _handle_block_response,
    _handle_force_trigger,
    _handle_generate_message_image,
)

router = APIRouter()


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
    overrides: dict[str, str] = {}
    for key in ("model", "api_key", "api_base"):
        val = str(raw.get(key) or "").strip()
        if val:
            overrides[key] = val
    return overrides or None


def _extract_image_overrides(data: dict[str, Any]) -> dict[str, str] | None:
    raw = data.get("image_overrides")
    if not isinstance(raw, dict):
        return None
    overrides: dict[str, str] = {}
    for key in ("model", "api_key", "api_base"):
        val = str(raw.get(key) or "").strip()
        if val:
            overrides[key] = val
    return overrides or None


async def _background_generate_image(
    sink: EventSink,
    session_id: str,
    block_id: str,
    turn_id: str,
    params: dict[str, Any],
) -> None:
    """Run story image generation in the background and push the result via WebSocket."""
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    from backend.app.services.image_service import generate_story_image

    try:
        async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
            result = await generate_story_image(
                db,
                project_id=params["project_id"],
                session_id=params["session_id"],
                title=params.get("title", "Story Image"),
                story_background=params.get("story_background", ""),
                prompt=params.get("prompt", ""),
                continuity_notes=params.get("continuity_notes", ""),
                reference_image_ids=params.get("reference_image_ids", []),
                scene_frames=params.get("scene_frames", []),
                layout_preference=params.get("layout_preference", "auto"),
                turn_id=params.get("turn_id"),
                autocommit=True,
                image_overrides=params.get("image_overrides"),
                llm_overrides=params.get("llm_overrides"),
            )
        event = {
            "type": "story_image",
            "data": result,
            "block_id": block_id,
            "turn_id": turn_id,
        }
        _add_log(session_id, "send", event)
        await sink.send_json(event)
    except Exception as exc:
        logger.exception("Background story_image generation failed")
        try:
            error_event = {
                "type": "story_image",
                "data": {
                    "status": "error",
                    "title": params.get("title", "Story Image"),
                    "story_background": params.get("story_background", ""),
                    "prompt": params.get("prompt", ""),
                    "continuity_notes": params.get("continuity_notes", ""),
                    "reference_image_ids": params.get("reference_image_ids", []),
                    "scene_frames": params.get("scene_frames", []),
                    "layout_preference": params.get("layout_preference", "auto"),
                    "error": f"Image generation failed: {exc}",
                    "can_regenerate": True,
                },
                "block_id": block_id,
                "turn_id": turn_id,
            }
            _add_log(session_id, "send", error_event)
            await sink.send_json(error_event)
        except Exception:
            logger.warning("Failed to send image error event (WebSocket likely closed)")


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
    """Stream process_message events (narrative + plugin agent) to sink."""
    async for event in process_message(
        session_id, content,
        save_user_msg=save_user_msg,
        save_assistant_msg=save_assistant_msg,
        llm_overrides=llm_overrides,
        image_overrides=image_overrides,
    ):
        etype = event.get("type", "")
        if etype == "_message_saved":
            continue  # internal event, don't forward
        _add_log(session_id, "send", event)
        await sink.send_json(event)


async def _session_exists(session_id: str) -> bool:
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    async with SQLModelAsyncSession(engine) as session:
        game_session = await session.get(GameSession, session_id)
        return bool(game_session)


async def _dispatch_incoming_message(
    sink: EventSink, session_id: str, data: dict[str, Any],
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
                sink, session_id, content,
                llm_overrides=llm_overrides, image_overrides=image_overrides,
            )
        elif msg_type == "init_game":
            await _handle_init_game(sink, session_id, data, llm_overrides=llm_overrides, image_overrides=image_overrides)
        elif msg_type == "form_submit":
            await _handle_form_submit(sink, session_id, data, llm_overrides=llm_overrides, image_overrides=image_overrides)
        elif msg_type == "character_edit":
            await _handle_character_edit(sink, session_id, data, llm_overrides=llm_overrides, image_overrides=image_overrides)
        elif msg_type == "scene_switch":
            await _handle_scene_switch(sink, session_id, data, llm_overrides=llm_overrides, image_overrides=image_overrides)
        elif msg_type == "confirm":
            await _handle_confirm(sink, session_id, data, llm_overrides=llm_overrides, image_overrides=image_overrides)
        elif msg_type == "block_response":
            await _handle_block_response(sink, session_id, data, llm_overrides=llm_overrides, image_overrides=image_overrides)
        elif msg_type == "force_trigger":
            await _handle_force_trigger(sink, session_id, data, llm_overrides=llm_overrides, image_overrides=image_overrides)
        elif msg_type == "generate_message_image":
            await _handle_generate_message_image(sink, session_id, data, image_overrides=image_overrides, llm_overrides=llm_overrides)
        else:
            await sink.send_json({"type": "error", "content": f"Unknown message type: {msg_type}"})
    except Exception:
        logger.exception("Error processing {} message", msg_type)
        await sink.send_json({"type": "error", "content": "Internal server error"})


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
    if not is_request_authorized(websocket.headers, websocket.query_params):
        await websocket.close(code=4401, reason="Unauthorized")
        return

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
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue
            if not isinstance(data, dict):
                await websocket.send_json({"type": "error", "content": "Invalid payload"})
                continue

            _add_log(session_id, "recv", data)
            await _dispatch_incoming_message(websocket, session_id, data)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session {}", session_id)
        _touch_log_session(session_id)
        _cleanup_log_sessions()
