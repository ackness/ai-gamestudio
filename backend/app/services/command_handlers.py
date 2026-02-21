from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.app.core.game_state import GameStateManager
from backend.app.db.engine import engine
from backend.app.models.session import GameSession

# Imported from sibling modules — these are the cross-module dependencies
from backend.app.api.debug_log import _add_log

# Late imports to avoid circular: EventSink and _stream_process_message come from chat.py
# We use TYPE_CHECKING for the protocol and pass _stream_process_message at call sites
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.api.chat import EventSink

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_INIT_PROMPT = (
    "玩家开始了一场新游戏。请根据世界观文档生成一段沉浸式的开场叙事。"
    "在叙事末尾包含一个 json:character_sheet 代码块用于角色创建，"
    "其中 editable_fields 需包含 'name'。"
    "同时包含一个 json:scene_update 代码块来建立起始场景。"
)

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
    from backend.app.api.chat import _stream_process_message

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
    from backend.app.api.chat import _stream_process_message

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
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
    from backend.app.api.chat import _stream_process_message

    form_id = data.get("form_id", "")
    values = data.get("values", {})

    if form_id == "character_creation":
        async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
            state_mgr = GameStateManager(db)
            game_session = await db.get(GameSession, session_id)
            if not game_session:
                await sink.send_json({"type": "error", "content": "Session not found"})
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
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
    from backend.app.api.chat import _stream_process_message

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

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        state_mgr = GameStateManager(db)
        game_session = await db.get(GameSession, session_id)
        if not game_session:
            await sink.send_json({"type": "error", "content": "Session not found"})
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
                "attributes": json.loads(char.attributes_json) if char.attributes_json else {},
                "inventory": json.loads(char.inventory_json) if char.inventory_json else [],
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
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
    from backend.app.api.chat import _stream_process_message

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
    from backend.app.api.chat import _stream_process_message

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
) -> None:
    """Handle a user's response to an interactive block (requires_response=true)."""
    from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
    from backend.app.api.chat import _stream_process_message

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
            await _handle_story_image_regen(
                sink, db, game_session, session_id, response_data, image_overrides,
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
) -> None:
    """Handle story image regeneration within a block_response."""
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
    status_text = "（图片已重新生成）" if regenerated.get("status") == "ok" else "（图片重生成失败）"
    await state_mgr.add_message(
        session_id, "assistant", status_text,
        message_type="narration",
        metadata={"blocks": [{"type": "story_image", "data": regenerated, "block_id": regen_block_id}]},
        raw_content="```json:story_image\n" + json.dumps(regenerated, ensure_ascii=False) + "\n```",
    )

    done_event = {"type": "done", "content": status_text, "turn_id": turn_id, "has_blocks": True}
    _add_log(session_id, "send", done_event)
    await sink.send_json(done_event)

    block_event = {"type": "story_image", "data": regenerated, "block_id": regen_block_id, "turn_id": turn_id}
    _add_log(session_id, "send", block_event)
    await sink.send_json(block_event)

    turn_end_event = {"type": "turn_end", "turn_id": turn_id}
    _add_log(session_id, "send", turn_end_event)
    await sink.send_json(turn_end_event)