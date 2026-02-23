from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.block_handlers import BlockContext, dispatch_block  # noqa: F401 — tests patch this
from backend.app.core.block_parser import strip_blocks
from backend.app.core.game_state import GameStateManager
from backend.app.core.llm_config import resolve_llm_config
from backend.app.core.llm_gateway import completion_with_config  # noqa: F401 — tests patch this
from backend.app.db.engine import engine  # noqa: F401 — tests patch this
from backend.app.services.archive_service import ARCHIVE_PLUGIN_NAME, maybe_auto_archive_summary
from backend.app.services.block_processing import process_blocks
from backend.app.services.plugin_service import get_enabled_plugins  # noqa: F401 — tests patch this
from backend.app.services.prompt_assembly import _build_pre_response_instructions  # noqa: F401 — tests import this
from backend.app.services.turn_context import build_turn_context


async def process_message(
    session_id: str,
    user_content: str,
    *,
    save_user_msg: bool = True,
    save_assistant_msg: bool = True,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Process a user message end-to-end and yield streaming events."""
    turn_id = str(uuid.uuid4())

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        state_mgr = GameStateManager(db, autocommit=False)

        # 1. Build turn context (loads session, project, characters, plugins, etc.)
        ctx = await build_turn_context(db, session_id, state_mgr)
        if ctx is None:
            yield {"type": "error", "content": "Session or project not found", "turn_id": turn_id}
            return

        # 2. Save user message
        if save_user_msg:
            await state_mgr.add_message(
                session_id, "user", user_content, scene_id=ctx.current_scene_id
            )
            await db.commit()

        # 3. Assemble prompt and call LLM
        from backend.app.services.prompt_assembly import assemble_prompt

        messages = assemble_prompt(ctx, user_content, save_user_msg)
        config = resolve_llm_config(project=ctx.project, overrides=llm_overrides)
        logger.info(f"Using LLM: model={config.model}, source={config.source}")

        try:
            full_response = ""
            stream = await completion_with_config(messages, config, stream=True)
            async for chunk in stream:
                full_response += chunk
                yield {"type": "chunk", "content": chunk, "turn_id": turn_id}
        except Exception as exc:
            logger.exception("LLM call failed")
            yield {"type": "error", "content": _format_llm_error(exc, config.model), "turn_id": turn_id}
            return

        logger.info("LLM response ({} chars): {}", len(full_response), full_response)

        # 4. Process blocks
        block_context = BlockContext(
            session_id=session_id, project_id=ctx.project.id, db=db,
            state_mgr=state_mgr, autocommit=False, turn_id=turn_id,
            image_overrides=image_overrides,
            llm_overrides=llm_overrides,
        )

        clean_response = strip_blocks(full_response)
        has_content = clean_response.strip() or bool(extract_blocks_check(full_response))
        should_increment_turn = bool(save_assistant_msg and has_content)
        saved_message_id: str | None = None

        try:
            processed_blocks, event_bus = await process_blocks(
                full_response, block_context, ctx.block_declarations,
                ctx.capability_declarations, ctx.pe, ctx.enabled_names,
                dispatch_fn=dispatch_block,
            )
            block_context.event_bus = event_bus

            # 5. Save assistant message
            updated_scene = await state_mgr.get_current_scene(session_id)
            updated_scene_id = updated_scene.id if updated_scene else ctx.current_scene_id

            stage_b_has_writes = bool(processed_blocks)
            if save_assistant_msg and has_content:
                block_summary = [
                    {"type": b["type"], "data": b["data"], "block_id": b.get("block_id")}
                    for b in processed_blocks
                ]
                saved_msg = await state_mgr.add_message(
                    session_id, "assistant", clean_response,
                    message_type="narration",
                    metadata={"blocks": block_summary} if block_summary else None,
                    raw_content=full_response, scene_id=updated_scene_id,
                )
                saved_message_id = saved_msg.id
                stage_b_has_writes = True

            # 6. Increment turn count
            if should_increment_turn:
                game_state = json.loads(ctx.session.game_state_json or "{}")
                game_state["turn_count"] = game_state.get("turn_count", 0) + 1
                ctx.session.game_state_json = json.dumps(game_state)
                db.add(ctx.session)
                stage_b_has_writes = True

            if stage_b_has_writes:
                await db.commit()

        except Exception:
            await db.rollback()
            logger.exception("Failed to finalize turn {}", turn_id)
            yield {"type": "error", "content": "回合状态保存失败，请重试", "turn_id": turn_id}
            return

        # 7. Yield block events
        for block in processed_blocks:
            yield {
                "type": block["type"], "data": block["data"],
                "block_id": block.get("block_id"), "turn_id": turn_id,
            }

        if saved_message_id:
            yield {"type": "_message_saved", "message_id": saved_message_id, "turn_id": turn_id}

        # 8. Auto archive
        if should_increment_turn and ARCHIVE_PLUGIN_NAME in ctx.enabled_names:
            try:
                created = await maybe_auto_archive_summary(db, ctx.project, ctx.session)
                if created:
                    yield {
                        "type": "notification",
                        "data": {"level": "info", "title": "存档已更新", "content": f"自动生成版本 v{created['version']}"},
                        "turn_id": turn_id,
                    }
            except Exception:
                logger.exception("Auto archive summary failed")


def extract_blocks_check(text: str) -> bool:
    """Quick check if text contains any blocks."""
    from backend.app.core.block_parser import extract_blocks
    return bool(extract_blocks(text))


def _format_llm_error(exc: Exception, model: str) -> str:
    """Convert an LLM exception into a user-friendly error message."""
    import litellm

    exc_type = type(exc).__name__
    if isinstance(exc, litellm.AuthenticationError):
        return f"LLM 认证失败: API Key 无效或已过期 (model: {model})"
    if isinstance(exc, litellm.NotFoundError):
        return f"模型不可用: {model} 不存在或无权访问"
    if isinstance(exc, litellm.RateLimitError):
        return f"请求限速: {model} 的调用频率超限，请稍后重试"
    if isinstance(exc, litellm.ServiceUnavailableError):
        return f"服务不可用: {model} 暂时无法响应，请稍后重试"
    if isinstance(exc, litellm.APIConnectionError):
        return f"连接失败: 无法连接到 LLM 服务 (model: {model})"
    if isinstance(exc, litellm.Timeout):
        return f"请求超时: {model} 响应超时，请稍后重试"
    if isinstance(exc, litellm.BadRequestError):
        return f"请求错误: {model} 拒绝了请求 — {exc}"
    return f"LLM 调用失败 ({exc_type}): {exc}"
