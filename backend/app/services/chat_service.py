from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.block_handlers import BlockContext, dispatch_block  # noqa: F401 — tests patch this
from backend.app.core.block_validation import validate_block_data
from backend.app.core.game_state import GameStateManager
from backend.app.core.llm_config import resolve_llm_config
from backend.app.core.llm_gateway import completion_with_config, create_stream_result  # noqa: F401 — tests patch this
from backend.app.db.engine import engine  # noqa: F401 — tests patch this
from backend.app.services.archive_service import maybe_auto_archive_summary
from backend.app.services.plugin_service import storage_get as _storage_get, storage_set  # noqa: F401 — tests patch this
from backend.app.services.token_service import (
    calculate_turn_cost,
    count_message_tokens,
    get_model_context_window,
)
from backend.app.services.turn_context import build_turn_context
from backend.app.core.game_db import GameDB
from backend.app.services.plugin_agent import run_plugin_agent
from backend.app.api.debug_log import _add_log


async def process_message(
    session_id: str,
    user_content: str,
    *,
    save_user_msg: bool = True,
    save_assistant_msg: bool = True,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Process a user message: narrative LLM + Plugin Agent post-processing."""
    turn_id = str(uuid.uuid4())

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        state_mgr = GameStateManager(db, autocommit=False)

        # 1. Build turn context
        ctx = await build_turn_context(db, session_id, state_mgr)
        if ctx is None:
            yield {"type": "error", "content": "Session or project not found", "turn_id": turn_id}
            return

        # 2. Save user message
        if save_user_msg:
            await state_mgr.add_message(session_id, "user", user_content, scene_id=ctx.current_scene_id)
            await db.commit()

        # 3. Assemble narrative-only prompt (no block instructions)
        from backend.app.services.prompt_assembly import assemble_narrative_prompt
        messages = assemble_narrative_prompt(ctx, user_content, save_user_msg)
        config = resolve_llm_config(project=ctx.project, overrides=llm_overrides)
        logger.info("Narrative LLM: model={}, source={}", config.model, config.source)

        # Debug: log prompt summary
        logger.debug(
            "Prompt: {} messages, {} chars, enabled_plugins={}",
            len(messages), sum(len(m["content"]) for m in messages), ctx.enabled_names,
        )
        _add_log(session_id, "debug", {
            "type": "narrative_prompt",
            "turn_id": turn_id,
            "model": config.model,
            "source": config.source,
            "enabled_plugins": ctx.enabled_names,
            "message_count": len(messages),
            "total_chars": sum(len(m["content"]) for m in messages),
            "messages": [
                {"role": m["role"], "length": len(m["content"]), "preview": m["content"][:200]}
                for m in messages
            ],
        })

        # Token tracking
        estimated_prompt_tokens = count_message_tokens(config.model, messages)
        context_window = get_model_context_window(config.model)
        max_input = context_window["max_input_tokens"]
        result_acc = create_stream_result()

        # 4. Stream narrative (no tools, no blocks)
        try:
            full_response = ""
            stream = await completion_with_config(messages, config, stream=True, result_acc=result_acc)
            async for chunk in stream:
                full_response += chunk
                yield {"type": "chunk", "content": chunk, "turn_id": turn_id}
        except Exception as exc:
            logger.exception("Narrative LLM call failed")
            yield {"type": "error", "content": _format_llm_error(exc, config.model), "turn_id": turn_id}
            return

        yield {"type": "done", "content": full_response, "turn_id": turn_id}

        # 5. Save narrative message + update turn count
        prompt_tokens = result_acc.prompt_tokens or estimated_prompt_tokens
        completion_tokens = result_acc.completion_tokens or max(1, len(full_response) // 4)
        turn_cost = calculate_turn_cost(config.model, prompt_tokens, completion_tokens)
        context_usage = prompt_tokens / max_input if max_input > 0 else 0.0

        saved_message_id: str | None = None
        should_increment_turn = bool(save_assistant_msg and full_response.strip())

        if save_assistant_msg and full_response.strip():
            saved_msg = await state_mgr.add_message(
                session_id, "assistant", full_response,
                message_type="narration", scene_id=ctx.current_scene_id,
            )
            saved_message_id = saved_msg.id

        token_state: dict[str, Any] = {}
        if should_increment_turn:
            game_state = json.loads(ctx.session.game_state_json or "{}")
            game_state["turn_count"] = game_state.get("turn_count", 0) + 1
            token_state = game_state.setdefault("token_usage", {
                "total_prompt_tokens": 0, "total_completion_tokens": 0, "total_cost": 0.0,
            })
            token_state["total_prompt_tokens"] += prompt_tokens
            token_state["total_completion_tokens"] += completion_tokens
            token_state["total_cost"] += turn_cost
            ctx.session.game_state_json = json.dumps(game_state)
            db.add(ctx.session)

        await db.commit()

        yield {
            "type": "token_usage", "turn_id": turn_id,
            "data": {
                "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "turn_cost": turn_cost, "context_usage": round(context_usage, 4),
                "total_cost": token_state.get("total_cost", turn_cost),
                "total_prompt_tokens": token_state.get("total_prompt_tokens", prompt_tokens),
                "total_completion_tokens": token_state.get("total_completion_tokens", completion_tokens),
                "max_input_tokens": max_input, "model": config.model,
            },
        }

        # 6. Run Plugin Agent (post-processing)
        game_db = GameDB(db, session_id)
        state_snapshot = await game_db.build_state_snapshot()
        try:
            blocks = await run_plugin_agent(
                narrative=full_response,
                game_state=state_snapshot,
                enabled_plugins=ctx.enabled_names,
                session_id=session_id,
                game_db=game_db,
                pe=ctx.pe,
                config=config,
            )
        except Exception:
            logger.exception("Plugin Agent failed for session {}", session_id)
            blocks = []

        # Debug: log Plugin Agent results
        logger.debug(
            "Plugin Agent: {} blocks emitted: {}",
            len(blocks), [b.get("type") for b in blocks],
        )
        _add_log(session_id, "debug", {
            "type": "plugin_agent_result",
            "turn_id": turn_id,
            "block_count": len(blocks),
            "blocks": [{"type": b.get("type"), "data_keys": list(b.get("data", {}).keys()) if isinstance(b.get("data"), dict) else None} for b in blocks],
        })

        # 7. Dispatch blocks
        block_context = BlockContext(
            session_id=session_id, project_id=ctx.project.id, db=db,
            state_mgr=state_mgr, autocommit=False, turn_id=turn_id,
            image_overrides=image_overrides, llm_overrides=llm_overrides,
        )
        for block in blocks:
            block_type = str(block.get("type", "unknown"))
            block_data = block.get("data")
            declaration = ctx.block_declarations.get(block_type) if ctx.block_declarations else None

            validation_errors = validate_block_data(block_type, block_data, declaration)
            if validation_errors:
                logger.warning("Invalid block from Plugin Agent: type={}, errors={}", block_type, validation_errors)
                yield {
                    "type": "notification",
                    "data": {
                        "level": "warning",
                        "title": "Block 数据不完整",
                        "content": f"{block_type}: {'; '.join(validation_errors[:2])}",
                    },
                    "turn_id": turn_id,
                }
                continue

            try:
                result = await dispatch_block(
                    block, block_context, ctx.block_declarations, None,
                )
                if isinstance(result, list):
                    for r in result:
                        yield {"type": r["type"], "data": r["data"], "turn_id": turn_id}
                else:
                    yield {"type": block["type"], "data": block["data"], "turn_id": turn_id}
            except Exception:
                logger.exception("Block dispatch failed: {}", block.get("type"))

        await db.commit()

        if saved_message_id:
            yield {"type": "_message_saved", "message_id": saved_message_id, "turn_id": turn_id}

        # 8. Auto archive (memory plugin subsumes archive)
        if should_increment_turn and "memory" in ctx.enabled_names:
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

        # 9. Auto compress check (memory plugin subsumes auto-compress)
        if "memory" in ctx.enabled_names and context_usage > 0:
            from backend.app.services.compress_service import should_compress, compress_history

            ac_settings = ctx.runtime_settings_by_plugin.get("memory", {})
            threshold = float(ac_settings.get("compression_threshold", 0.7))
            keep_recent = int(ac_settings.get("keep_recent_messages", 6))

            if should_compress(context_usage, threshold):
                try:
                    all_messages = await state_mgr.get_messages(session_id, limit=100)
                    if len(all_messages) > keep_recent:
                        messages_to_compress = all_messages[:-keep_recent]
                        existing_summary = ctx.compression_summary

                        compress_result = await compress_history(
                            messages_to_compress,
                            existing_summary,
                            model=config.model,
                            llm_overrides=llm_overrides,
                        )

                        await storage_set(
                            db, ctx.project.id, "auto-compress",
                            "compression-summary",
                            {"summary": compress_result["summary"]},
                            autocommit=True,
                        )

                        prev_state = await _storage_get(db, ctx.project.id, "auto-compress", "compression-state")
                        prev_count = (prev_state or {}).get("total_compressions", 0) if isinstance(prev_state, dict) else 0
                        await storage_set(
                            db, ctx.project.id, "auto-compress",
                            "compression-state",
                            {
                                "last_compressed_message_count": len(messages_to_compress),
                                "total_compressions": prev_count + 1,
                            },
                            autocommit=True,
                        )

                        yield {
                            "type": "notification",
                            "data": {
                                "level": "info",
                                "title": "上下文已压缩",
                                "content": f"已将 {len(messages_to_compress)} 条旧消息压缩为摘要",
                            },
                            "turn_id": turn_id,
                        }
                        logger.info("Auto-compressed {} messages for session {}", len(messages_to_compress), session_id)
                except Exception:
                    logger.exception("Auto-compress failed for session {}", session_id)

        yield {"type": "turn_end", "turn_id": turn_id}


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


