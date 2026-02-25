from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Protocol

from loguru import logger

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.app.core.access_key import is_request_authorized
from backend.app.core.rate_limit import limiter as _limiter
from backend.app.db.engine import engine
from backend.app.models.session import GameSession
from backend.app.services.chat_service import process_message, retrigger_plugins, stream_process_message  # noqa: F401 — tests patch process_message

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


class OverridePayload(BaseModel):
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None

    def to_non_empty_dict(self) -> dict[str, str] | None:
        out: dict[str, str] = {}
        for key in ("model", "api_key", "api_base"):
            val = str(getattr(self, key) or "").strip()
            if val:
                out[key] = val
        return out or None


class TerminalSummary(BaseModel):
    status: Literal["done", "error"]
    turn_id: str = ""


class ChatCommandResponse(BaseModel):
    events: list[dict[str, Any]]
    terminal: TerminalSummary | None = None


@dataclass(slots=True)
class CommandContext:
    sink: EventSink
    session_id: str
    data: dict[str, Any]
    transport_mode: Literal["http", "websocket"]
    llm_overrides: dict[str, str] | None = None
    image_overrides: dict[str, str] | None = None


CommandHandler = Callable[[CommandContext], Awaitable[None]]


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, msg_type: str, handler: CommandHandler) -> None:
        self._handlers[msg_type] = handler

    async def dispatch(self, ctx: CommandContext) -> None:
        msg_type = str(ctx.data.get("type", "message"))
        handler = self._handlers.get(msg_type)
        if handler is None:
            await _send_error(
                ctx.sink,
                f"Unknown message type: {msg_type}",
            )
            return
        await handler(ctx)


def _build_terminal_summary(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute terminal status from collected command events."""
    last_terminal: dict[str, Any] | None = None
    for evt in events:
        if not isinstance(evt, dict):
            continue
        etype = str(evt.get("type") or "")
        if etype in {"done", "error", "turn_end"}:
            last_terminal = evt
    if not last_terminal:
        return None
    etype = str(last_terminal.get("type") or "")
    status = "error" if etype == "error" else "done"
    turn_id = str(last_terminal.get("turn_id") or "")
    return {"status": status, "turn_id": turn_id}


def _extract_overrides(data: dict[str, Any], field_name: str) -> dict[str, str] | None:
    raw = data.get(field_name)
    if not isinstance(raw, dict):
        return None
    try:
        parsed = OverridePayload.model_validate(raw)
    except Exception:
        return None
    return parsed.to_non_empty_dict()


async def _send_error(sink: EventSink, content: str) -> None:
    await sink.send_json({"type": "error", "content": content})


async def _handle_retrigger_plugins(
    sink: EventSink,
    session_id: str,
    data: dict[str, Any],
    *,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    message_id = str(data.get("message_id", ""))
    if not message_id:
        await sink.send_json({"type": "error", "content": "message_id is required"})
        return
    async for event in retrigger_plugins(
        session_id, message_id,
        llm_overrides=llm_overrides, image_overrides=image_overrides,
    ):
        _add_log(session_id, "send", event)
        await sink.send_json(event)


async def _ensure_http_terminal_event(ctx: CommandContext) -> None:
    if ctx.transport_mode != "http":
        return
    events = getattr(ctx.sink, "events", None)
    if not isinstance(events, list):
        return
    has_terminal = any(
        isinstance(evt, dict) and evt.get("type") in {"done", "error", "turn_end"}
        for evt in events
    )
    if has_terminal:
        return
    done_event = {"type": "done", "content": ""}
    _add_log(ctx.session_id, "send", done_event)
    await ctx.sink.send_json(done_event)


async def _session_exists(session_id: str) -> bool:
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

    async with SQLModelAsyncSession(engine) as session:
        game_session = await session.get(GameSession, session_id)
        return bool(game_session)


async def _handle_message(ctx: CommandContext) -> None:
    content = str(ctx.data.get("content", "")).strip()
    if not content:
        await _send_error(ctx.sink, "Empty message")
        return
    await stream_process_message(
        ctx.sink,
        ctx.session_id,
        content,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
    )
    await _ensure_http_terminal_event(ctx)


async def _handle_init_game_command(ctx: CommandContext) -> None:
    await _handle_init_game(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
    )


async def _handle_form_submit_command(ctx: CommandContext) -> None:
    await _handle_form_submit(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
    )


async def _handle_character_edit_command(ctx: CommandContext) -> None:
    await _handle_character_edit(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
    )


async def _handle_scene_switch_command(ctx: CommandContext) -> None:
    await _handle_scene_switch(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
    )


async def _handle_confirm_command(ctx: CommandContext) -> None:
    await _handle_confirm(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
    )


async def _handle_block_response_command(ctx: CommandContext) -> None:
    await _handle_block_response(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
        transport_mode=ctx.transport_mode,
    )


async def _handle_force_trigger_command(ctx: CommandContext) -> None:
    await _handle_force_trigger(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
    )


async def _handle_generate_message_image_command(ctx: CommandContext) -> None:
    await _handle_generate_message_image(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        image_overrides=ctx.image_overrides,
        llm_overrides=ctx.llm_overrides,
    )


async def _handle_retrigger_plugins_command(ctx: CommandContext) -> None:
    await _handle_retrigger_plugins(
        ctx.sink,
        ctx.session_id,
        ctx.data,
        llm_overrides=ctx.llm_overrides,
        image_overrides=ctx.image_overrides,
    )


_COMMAND_ROUTER = CommandRouter()
_COMMAND_ROUTER.register("message", _handle_message)
_COMMAND_ROUTER.register("init_game", _handle_init_game_command)
_COMMAND_ROUTER.register("form_submit", _handle_form_submit_command)
_COMMAND_ROUTER.register("character_edit", _handle_character_edit_command)
_COMMAND_ROUTER.register("scene_switch", _handle_scene_switch_command)
_COMMAND_ROUTER.register("confirm", _handle_confirm_command)
_COMMAND_ROUTER.register("block_response", _handle_block_response_command)
_COMMAND_ROUTER.register("force_trigger", _handle_force_trigger_command)
_COMMAND_ROUTER.register("generate_message_image", _handle_generate_message_image_command)
_COMMAND_ROUTER.register("retrigger_plugins", _handle_retrigger_plugins_command)


async def _dispatch_incoming_message(
    sink: EventSink,
    session_id: str,
    data: dict[str, Any],
    *,
    transport_mode: Literal["http", "websocket"] = "websocket",
) -> None:
    msg_type = str(data.get("type", "message"))
    ctx = CommandContext(
        sink=sink,
        session_id=session_id,
        data=data,
        transport_mode=transport_mode,
        llm_overrides=_extract_overrides(data, "llm_overrides"),
        image_overrides=_extract_overrides(data, "image_overrides"),
    )
    try:
        await _COMMAND_ROUTER.dispatch(ctx)
    except Exception:
        logger.exception("Error processing {} message", msg_type)
        await _send_error(sink, "Internal server error")


@router.post("/api/chat/{session_id}/command", response_model=ChatCommandResponse)
@_limiter.limit("60/minute")
async def chat_command(request: Request, session_id: str, data: dict[str, Any]) -> ChatCommandResponse:
    """HTTP fallback for chat commands (Vercel-compatible, no WebSocket required)."""
    if not await _session_exists(session_id):
        events = [{"type": "error", "content": "Session not found"}]
        terminal = _build_terminal_summary(events)
        return ChatCommandResponse(events=events, terminal=terminal)

    payload = data if isinstance(data, dict) else {}
    _add_log(session_id, "recv", payload)

    collector = HttpEventCollector()
    await _dispatch_incoming_message(
        collector,
        session_id,
        payload,
        transport_mode="http",
    )
    terminal = _build_terminal_summary(collector.events)
    return ChatCommandResponse(events=collector.events, terminal=terminal)


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
            if len(raw) > 1_000_000:
                await websocket.send_json({"type": "error", "content": "Message too large (>1MB)"})
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue
            if not isinstance(data, dict):
                await websocket.send_json({"type": "error", "content": "Invalid payload"})
                continue

            _add_log(session_id, "recv", data)
            await _dispatch_incoming_message(
                websocket,
                session_id,
                data,
                transport_mode="websocket",
            )

    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info("WebSocket disconnected for session {}", session_id)
        _touch_log_session(session_id)
        _cleanup_log_sessions()
