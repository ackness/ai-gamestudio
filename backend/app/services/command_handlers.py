from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.game_state import GameStateManager
from backend.app.core.json_utils import safe_json_loads
from backend.app.db.engine import engine
from backend.app.models.session import GameSession
from backend.app.services.debug_log_service import add_debug_log as _add_log
from backend.app.services.chat_service import stream_process_message as _stream_process_message
from typing import Protocol


class EventSink(Protocol):
    async def send_json(self, data: dict) -> None: ...


# ---------------------------------------------------------------------------
# Shared helpers — reduce repeated session-lookup boilerplate
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _with_session() -> AsyncIterator[SQLModelAsyncSession]:
    """Open a short-lived DB session (replaces repeated ``async with SQLModelAsyncSession(engine, ...)`` blocks)."""
    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        yield db


async def _get_session_or_error(
    sink: EventSink,
    session_id: str,
    db: SQLModelAsyncSession,
) -> GameSession | None:
    """Fetch a GameSession by id, sending an error event and returning None if missing."""
    game_session = await db.get(GameSession, session_id)
    if not game_session:
        await sink.send_json({"type": "error", "content": "Session not found"})
        return None
    return game_session

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_INIT_PROMPT = (
    "玩家开始了一场新游戏。请根据世界观文档生成一段沉浸式的开场叙事。"
    "描述玩家角色的初始状态和所在场景，并引导玩家创建自己的角色。"
)

_FORCE_TRIGGER_PROMPTS: dict[str, str] = {
    "guide": (
        "请简短描述当前场景和角色面临的局势，"
        "并列出玩家可以采取的几种行动方向。"
    ),
    "state_update": (
        "请根据最近发生的事件，简要总结角色状态的变化，"
        "包括属性、物品、位置等方面的更新。"
    ),
    "scene_update": (
        "请描述当前场景的环境、氛围和在场人物，"
        "让玩家感受到场景的变化。"
    ),
    "story_image": (
        "请用一段密集的叙事描绘当前场景的视觉画面，"
        "包括环境、光线、角色姿态和氛围。"
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
    llm_overrides: dict[str, str] | None = None,
) -> None:
    """Handle per-message image generation — no LLM round-trip."""
    from sqlmodel import select

    from backend.app.models.message import Message
    from backend.app.services.image_service import generate_message_image

    message_id = data.get("message_id", "")
    if not message_id:
        await sink.send_json(
            {"type": "error", "content": "message_id is required"}
        )
        return

    async with _with_session() as db:
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

        game_session = await _get_session_or_error(sink, session_id, db)
        if not game_session:
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
                llm_overrides=llm_overrides,
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


async def _handle_init_game(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle game initialization — transition to character_creation or playing."""
    from backend.app.models.project import Project

    async with _with_session() as db:
        game_session = await _get_session_or_error(sink, session_id, db)
        if not game_session:
            return

        project = await db.get(Project, game_session.project_id)
        if not project:
            await sink.send_json({"type": "error", "content": "Project not found"})
            return

        init_prompt = project.init_prompt or DEFAULT_INIT_PROMPT

        game_session.phase = "character_creation"
        game_session.updated_at = datetime.now(timezone.utc)
        db.add(game_session)
        await db.commit()

    phase_event = {"type": "phase_change", "data": {"phase": "character_creation"}}
    _add_log(session_id, "send", phase_event)
    await sink.send_json(phase_event)

    await _stream_process_message(
        sink, session_id, init_prompt,
        llm_overrides=llm_overrides, image_overrides=image_overrides,
    )


async def _handle_form_submit(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle form submission — may trigger character creation or other actions."""
    form_id = data.get("form_id", "")
    values = data.get("values", {})

    if form_id == "character_creation":
        async with _with_session() as db:
            state_mgr = GameStateManager(db)
            game_session = await _get_session_or_error(sink, session_id, db)
            if not game_session:
                return

            char = await state_mgr.upsert_character(
                session_id,
                {
                    "name": values.get("name", "Unknown"),
                    "role": "player",
                    **{k: v for k, v in values.items() if k != "name"},
                },
            )

            game_session.phase = "playing"
            game_session.updated_at = datetime.now(timezone.utc)
            db.add(game_session)
            await db.commit()

            await sink.send_json(
                {"type": "phase_change", "data": {"phase": "playing"}}
            )
            await sink.send_json(
                {"type": "state_update", "data": {"characters": [{"id": char.id, "name": char.name, "role": char.role}]}}
            )

        formatted = ", ".join(f"{k}={v}" for k, v in values.items())
        content = (
            f"【角色创建完成】{formatted}。请开始冒险叙事。\n"
            "（这是开场叙事，不要输出 json:guide，让玩家自由开始冒险。）"
        )
        await _stream_process_message(
            sink, session_id, content,
            llm_overrides=llm_overrides, image_overrides=image_overrides,
        )
    else:
        formatted = ", ".join(f"{k}={v}" for k, v in values.items())
        content = f"【表单提交】{form_id}: {formatted}"
        await _stream_process_message(
            sink, session_id, content,
            llm_overrides=llm_overrides, image_overrides=image_overrides,
        )


async def _handle_character_edit(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> None:
    """Handle character edits — no LLM call, direct DB update."""
    character_id = data.get("character_id")
    changes = data.get("changes", {})

    if not character_id:
        await sink.send_json(
            {"type": "error", "content": "character_id is required"}
        )
        return

    if not changes:
        await sink.send_json(
            {"type": "character_confirmed", "data": {"character_id": character_id}}
        )

        async with _with_session() as db:
            game_session = await db.get(GameSession, session_id)
            if game_session and game_session.phase == "character_creation":
                game_session.phase = "playing"
                game_session.updated_at = datetime.now(timezone.utc)
                db.add(game_session)
                await db.commit()

                await sink.send_json(
                    {"type": "phase_change", "data": {"phase": "playing"}}
                )

                content = "【角色确认完成】请开始冒险叙事。"
                await _stream_process_message(
                    sink, session_id, content,
                    llm_overrides=llm_overrides, image_overrides=image_overrides,
                )
                return

        done_event = {"type": "done", "content": ""}
        _add_log(session_id, "send", done_event)
        await sink.send_json(done_event)
        return

    transitioned_from_creation = False

    async with _with_session() as db:
        state_mgr = GameStateManager(db)
        game_session = await _get_session_or_error(sink, session_id, db)
        if not game_session:
            return

        char_data = {"character_id": character_id, **changes}
        char = await state_mgr.upsert_character(session_id, char_data)

        change_desc = ", ".join(f"{k}→{v}" for k, v in changes.items())
        await state_mgr.add_message(
            session_id, "system",
            f"玩家修改了角色 {char.name}: {change_desc}",
            message_type="system_event",
        )

        if game_session.phase == "character_creation":
            transitioned_from_creation = True
            game_session.phase = "playing"
            game_session.updated_at = datetime.now(timezone.utc)
            db.add(game_session)
            await db.commit()

            await sink.send_json(
                {"type": "phase_change", "data": {"phase": "playing"}}
            )

    await sink.send_json({
        "type": "state_update",
        "data": {
            "characters": [{
                "id": char.id,
                "name": char.name,
                "role": char.role,
                "attributes": safe_json_loads(
                    char.attributes_json,
                    fallback={},
                    context=f"Character attributes ({char.id})",
                ),
                "inventory": safe_json_loads(
                    char.inventory_json,
                    fallback=[],
                    context=f"Character inventory ({char.id})",
                ),
            }]
        },
    })

    if transitioned_from_creation:
        formatted = ", ".join(f"{k}={v}" for k, v in changes.items())
        content = f"【角色编辑完成】{char.name}: {formatted}。请开始冒险叙事。"
        await _stream_process_message(
            sink, session_id, content,
            llm_overrides=llm_overrides, image_overrides=image_overrides,
        )
    else:
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
    scene_id = data.get("scene_id")
    if not scene_id:
        await sink.send_json(
            {"type": "error", "content": "scene_id required"}
        )
        return

    async with _with_session() as db:
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
        sink, session_id, content,
        llm_overrides=llm_overrides, image_overrides=image_overrides,
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
        sink, session_id, content,
        llm_overrides=llm_overrides, image_overrides=image_overrides,
    )


async def _handle_block_response(
    sink: EventSink,
    session_id: str,
    data: dict,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
    transport_mode: str = "websocket",
) -> None:
    """Handle a user's response to an interactive block (requires_response=true)."""
    block_type = data.get("block_type", "unknown")
    block_id = data.get("block_id", "")
    response_data = data.get("data", {})

    async with _with_session() as db:
        game_session = await _get_session_or_error(sink, session_id, db)
        if not game_session:
            return

        if (
            block_type == "story_image"
            and isinstance(response_data, dict)
            and str(response_data.get("action", "")).strip().lower() == "regenerate"
        ):
            await _handle_story_image_regen(
                sink, db, game_session, session_id, response_data, image_overrides,
                llm_overrides=llm_overrides,
                transport_mode=transport_mode,
            )
            return

        state_mgr = GameStateManager(db)
        await state_mgr.add_message(
            session_id, "system",
            f"[block_response:{block_type}] {json.dumps(response_data, ensure_ascii=False)}",
            message_type="system_event",
            metadata={
                "block_response": True,
                "block_type": block_type,
                "block_id": block_id,
                "response_data": response_data,
            },
        )

    chosen = response_data.get("chosen") or response_data.get("value") or json.dumps(response_data, ensure_ascii=False)
    content = f"[对 {block_type} 的回应] {chosen}"
    await _stream_process_message(
        sink, session_id, content,
        llm_overrides=llm_overrides, image_overrides=image_overrides,
    )


async def _handle_story_image_regen(
    sink: EventSink,
    db: Any,
    game_session: GameSession,
    session_id: str,
    response_data: dict,
    image_overrides: dict[str, str] | None = None,
    llm_overrides: dict[str, str] | None = None,
    transport_mode: str = "websocket",
) -> None:
    """Handle story image regeneration.

    WebSocket mode runs regeneration in background.
    HTTP fallback runs synchronously so completion event is returned in one response.
    """
    image_id = str(response_data.get("image_id") or "").strip()
    reason = str(response_data.get("reason") or "").strip()

    turn_id = str(uuid.uuid4())
    regen_block_id = f"{turn_id}:0"

    # Build a placeholder for the "generating" status
    placeholder_title = str(response_data.get("title") or "Story Image (regen)")
    placeholder = {
        "status": "generating",
        "title": placeholder_title,
        "story_background": str(response_data.get("story_background") or ""),
        "prompt": str(response_data.get("prompt") or ""),
        "continuity_notes": str(response_data.get("continuity_notes") or ""),
        "can_regenerate": False,
    }

    # Send placeholder immediately so the user sees feedback
    done_event = {"type": "done", "content": "（正在重新生成图片…）", "turn_id": turn_id, "has_blocks": True}
    _add_log(session_id, "send", done_event)
    await sink.send_json(done_event)

    block_event = {"type": "story_image", "data": placeholder, "block_id": regen_block_id, "turn_id": turn_id}
    _add_log(session_id, "send", block_event)
    await sink.send_json(block_event)

    turn_end_event = {"type": "turn_end", "turn_id": turn_id}
    _add_log(session_id, "send", turn_end_event)
    await sink.send_json(turn_end_event)

    regen_coro = _background_regen_image(
        sink,
        project_id=game_session.project_id,
        session_id=session_id,
        turn_id=turn_id,
        regen_block_id=regen_block_id,
        image_id=image_id,
        reason=reason,
        response_data=response_data,
        image_overrides=image_overrides,
        llm_overrides=llm_overrides,
    )
    if transport_mode == "http":
        await regen_coro
    else:
        task = asyncio.create_task(regen_coro)
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


async def _background_regen_image(
    sink: EventSink,
    *,
    project_id: str,
    session_id: str,
    turn_id: str,
    regen_block_id: str,
    image_id: str,
    reason: str,
    response_data: dict,
    image_overrides: dict[str, str] | None = None,
    llm_overrides: dict[str, str] | None = None,
) -> None:
    """Run story image regeneration in the background."""
    from backend.app.services.image_service import (
        generate_story_image,
        regenerate_story_image,
    )

    try:
        async with _with_session() as db:
            if image_id:
                regenerated = await regenerate_story_image(
                    db,
                    project_id=project_id,
                    session_id=session_id,
                    image_id=image_id,
                    reason=reason or None,
                    turn_id=turn_id,
                    autocommit=True,
                    image_overrides=image_overrides,
                    llm_overrides=llm_overrides,
                )
            else:
                title = str(response_data.get("title") or "Story Image (regen)")
                story_background = str(response_data.get("story_background") or "")
                prompt = str(response_data.get("prompt") or "")
                continuity_notes = str(response_data.get("continuity_notes") or "")
                if reason:
                    if continuity_notes:
                        continuity_notes = f"{continuity_notes}. Regeneration note: {reason}"
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
                    project_id=project_id,
                    session_id=session_id,
                    title=title,
                    story_background=story_background,
                    prompt=prompt,
                    continuity_notes=continuity_notes,
                    reference_image_ids=refs,
                    scene_frames=scene_frames,
                    layout_preference=layout_preference,
                    turn_id=turn_id,
                    autocommit=True,
                    image_overrides=image_overrides,
                    llm_overrides=llm_overrides,
                )

            # Save message to DB
            state_mgr = GameStateManager(db)
            status_text = "（图片已重新生成）" if regenerated.get("status") == "ok" else "（图片重生成失败）"
            await state_mgr.add_message(
                session_id, "assistant", status_text,
                message_type="narration",
                metadata={"blocks": [{"type": "story_image", "data": regenerated, "block_id": regen_block_id}]},
                raw_content="```json:story_image\n" + json.dumps(regenerated, ensure_ascii=False) + "\n```",
            )

        # Push completed result to frontend (updates the "generating" placeholder)
        block_event = {"type": "story_image", "data": regenerated, "block_id": regen_block_id, "turn_id": turn_id}
        _add_log(session_id, "send", block_event)
        await sink.send_json(block_event)

    except Exception as exc:
        logger.exception("Background story_image regeneration failed")
        try:
            error_event = {
                "type": "story_image",
                "data": {
                    "status": "error",
                    "title": str(response_data.get("title") or "Story Image"),
                    "error": f"Image regeneration failed: {exc}",
                    "can_regenerate": True,
                },
                "block_id": regen_block_id,
                "turn_id": turn_id,
            }
            _add_log(session_id, "send", error_event)
            await sink.send_json(error_event)
        except Exception:
            logger.warning("Failed to send regen error event (WebSocket likely closed)")
