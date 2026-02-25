from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.block_handlers import BlockContext, dispatch_block  # noqa: F401 — tests patch this
from backend.app.core.block_validation import validate_block_data
from backend.app.core.game_state import GameStateManager
from backend.app.core.json_utils import safe_json_loads
from backend.app.core.llm_config import resolve_llm_config, resolve_plugin_llm_config
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


def _normalize_plugin_counts(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            counts[name] = max(0, int(value))
        except Exception:
            continue
    return counts


def _plugins_to_count(plugin_summary: dict[str, Any]) -> list[str]:
    preferred = plugin_summary.get("plugins_executed")
    raw = preferred if isinstance(preferred, list) else plugin_summary.get("plugins_run")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        name = str(item or "").strip()
        if name:
            out.append(name)
    return out


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
            game_state = safe_json_loads(
                ctx.session.game_state_json,
                fallback={},
                context=f"GameSession state ({session_id})",
            )
            if not isinstance(game_state, dict):
                game_state = {}
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
        yield {"type": "phase_change", "phase": "plugins", "turn_id": turn_id}

        plugin_config = resolve_plugin_llm_config(config, overrides=llm_overrides)
        logger.info("Plugin Agent: model={}, source={}", plugin_config.model, plugin_config.source)

        game_db = GameDB(db, session_id)
        state_snapshot = await game_db.build_state_snapshot()
        plugin_summary: dict[str, Any] = {}

        # Load per-session plugin trigger counts
        game_state_data = safe_json_loads(
            ctx.session.game_state_json,
            fallback={},
            context=f"GameSession state ({session_id})",
        )
        if not isinstance(game_state_data, dict):
            game_state_data = {}
        trigger_counts = _normalize_plugin_counts(
            game_state_data.get("plugin_execution_counts")
        )
        if not trigger_counts:
            trigger_counts = _normalize_plugin_counts(
                game_state_data.get("plugin_trigger_counts")
            )

        # Use asyncio.Queue to stream plugin progress in real-time
        progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def _run_agent() -> tuple[list[dict], dict[str, Any]]:
            return await run_plugin_agent(
                narrative=full_response,
                game_state=state_snapshot,
                enabled_plugins=ctx.enabled_names,
                session_id=session_id,
                game_db=game_db,
                pe=ctx.pe,
                config=plugin_config,
                on_progress=progress_queue.put_nowait,
                trigger_counts=trigger_counts,
            )

        agent_task = asyncio.create_task(_run_agent())
        try:
            while not agent_task.done():
                try:
                    progress = await asyncio.wait_for(progress_queue.get(), timeout=0.2)
                    yield {"type": "plugin_progress", "data": progress, "turn_id": turn_id}
                except asyncio.TimeoutError:
                    continue
            # Drain remaining progress events
            while not progress_queue.empty():
                progress = progress_queue.get_nowait()
                yield {"type": "plugin_progress", "data": progress, "turn_id": turn_id}
            blocks, plugin_summary = agent_task.result()
        except Exception:
            logger.exception("Plugin Agent failed for session {}", session_id)
            blocks = []
            if not agent_task.done():
                agent_task.cancel()

        # Filter conflicting blocks: suppress guide/choices when character_sheet is present
        block_types = {b.get("type") for b in blocks}
        if "character_sheet" in block_types:
            suppressed = {"guide", "choices", "auto_guide"}
            before_count = len(blocks)
            blocks = [b for b in blocks if b.get("type") not in suppressed]
            if len(blocks) < before_count:
                logger.debug("Suppressed guide/choices blocks due to character_sheet presence")

        # Suppress character_sheet if a player character already exists
        if "character_sheet" in block_types:
            existing_chars = await state_mgr.get_characters(session_id)
            has_player = any(c.role == "player" for c in existing_chars)
            if has_player:
                before_count = len(blocks)
                blocks = [b for b in blocks if b.get("type") != "character_sheet"]
                if len(blocks) < before_count:
                    logger.debug("Suppressed character_sheet: player character already exists")

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

        yield {"type": "phase_change", "phase": "complete", "turn_id": turn_id}

        if plugin_summary:
            yield {"type": "plugin_summary", "data": plugin_summary, "turn_id": turn_id}

        # 7. Dispatch blocks
        block_context = BlockContext(
            session_id=session_id, project_id=ctx.project.id, db=db,
            state_mgr=state_mgr, autocommit=False, turn_id=turn_id,
            image_overrides=image_overrides, llm_overrides=llm_overrides,
        )
        _INFRA_BLOCK_TYPES = {"state_update"}
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
                # Infrastructure blocks (e.g. state_update) are processed but not sent to frontend
                if block_type in _INFRA_BLOCK_TYPES:
                    continue
                if isinstance(result, list):
                    for r in result:
                        yield {"type": r["type"], "data": r["data"], "turn_id": turn_id}
                else:
                    yield {"type": block["type"], "data": block["data"], "turn_id": turn_id}
            except Exception:
                logger.exception("Block dispatch failed: {}", block.get("type"))

        # 7b. Persist blocks to message metadata for reload recovery
        if saved_message_id and blocks:
            dispatched_blocks = [
                {"type": b.get("type"), "data": b.get("data"), "block_id": f"{saved_message_id}:{i}"}
                for i, b in enumerate(blocks)
                if b.get("type") not in {"state_update"}  # infra blocks excluded
            ]
            if dispatched_blocks:
                from backend.app.models.message import Message
                msg_obj = await db.get(Message, saved_message_id)
                if msg_obj:
                    existing_meta = safe_json_loads(
                        msg_obj.metadata_json,
                        fallback={},
                        context=f"Message metadata ({saved_message_id})",
                    )
                    if not isinstance(existing_meta, dict):
                        existing_meta = {}
                    existing_meta["blocks"] = dispatched_blocks
                    msg_obj.metadata_json = json.dumps(existing_meta, ensure_ascii=False)
                    db.add(msg_obj)

        # Update trigger counts for plugins that emitted blocks
        plugins_counted = _plugins_to_count(plugin_summary)
        if plugins_counted:
            latest_state = safe_json_loads(
                ctx.session.game_state_json,
                fallback={},
                context=f"GameSession state ({session_id})",
            )
            if not isinstance(latest_state, dict):
                latest_state = {}
            latest_trigger_counts = _normalize_plugin_counts(
                latest_state.get("plugin_execution_counts")
            )
            if not latest_trigger_counts:
                latest_trigger_counts = _normalize_plugin_counts(
                    latest_state.get("plugin_trigger_counts")
                )
            for pname in plugins_counted:
                latest_trigger_counts[pname] = int(latest_trigger_counts.get(pname, 0) or 0) + 1
            # New canonical key + legacy compatibility key.
            latest_state["plugin_execution_counts"] = latest_trigger_counts
            latest_state["plugin_trigger_counts"] = latest_trigger_counts
            ctx.session.game_state_json = json.dumps(latest_state)
            db.add(ctx.session)

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


async def retrigger_plugins(
    session_id: str,
    message_id: str,
    *,
    llm_overrides: dict[str, str] | None = None,
    image_overrides: dict[str, str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Re-run Plugin Agent for an existing assistant message's narrative."""
    turn_id = str(uuid.uuid4())

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        state_mgr = GameStateManager(db, autocommit=False)

        # Load the target message
        from backend.app.models.message import Message
        msg_obj = await db.get(Message, message_id)
        if not msg_obj or msg_obj.session_id != session_id:
            yield {"type": "error", "content": "Message not found", "turn_id": turn_id}
            return
        if msg_obj.role != "assistant":
            yield {"type": "error", "content": "Can only retrigger plugins for assistant messages", "turn_id": turn_id}
            return

        narrative = msg_obj.content
        if not narrative or not narrative.strip():
            yield {"type": "error", "content": "Message has no narrative content", "turn_id": turn_id}
            return

        # Build context
        ctx = await build_turn_context(db, session_id, state_mgr)
        if ctx is None:
            yield {"type": "error", "content": "Session or project not found", "turn_id": turn_id}
            return

        main_config = resolve_llm_config(project=ctx.project, overrides=llm_overrides)
        plugin_config = resolve_plugin_llm_config(main_config, overrides=llm_overrides)

        yield {"type": "phase_change", "phase": "plugins", "turn_id": turn_id}

        game_db = GameDB(db, session_id)
        state_snapshot = await game_db.build_state_snapshot()
        plugin_summary: dict[str, Any] = {}

        # Load per-session plugin trigger counts
        retrigger_gs_data = safe_json_loads(
            ctx.session.game_state_json,
            fallback={},
            context=f"GameSession state ({session_id})",
        )
        if not isinstance(retrigger_gs_data, dict):
            retrigger_gs_data = {}
        retrigger_trigger_counts = _normalize_plugin_counts(
            retrigger_gs_data.get("plugin_execution_counts")
        )
        if not retrigger_trigger_counts:
            retrigger_trigger_counts = _normalize_plugin_counts(
                retrigger_gs_data.get("plugin_trigger_counts")
            )

        try:
            blocks, plugin_summary = await run_plugin_agent(
                narrative=narrative,
                game_state=state_snapshot,
                enabled_plugins=ctx.enabled_names,
                session_id=session_id,
                game_db=game_db,
                pe=ctx.pe,
                config=plugin_config,
                trigger_counts=retrigger_trigger_counts,
            )
        except Exception:
            logger.exception("Plugin Agent retrigger failed for session {}", session_id)
            blocks = []

        # Filter conflicting blocks
        block_types = {b.get("type") for b in blocks}
        if "character_sheet" in block_types:
            suppressed = {"guide", "choices", "auto_guide"}
            blocks = [b for b in blocks if b.get("type") not in suppressed]

        # Suppress character_sheet if a player character already exists
        if "character_sheet" in block_types:
            existing_chars = await state_mgr.get_characters(session_id)
            has_player = any(c.role == "player" for c in existing_chars)
            if has_player:
                blocks = [b for b in blocks if b.get("type") != "character_sheet"]
                logger.debug("Retrigger: suppressed character_sheet (player exists)")

        logger.info("Retrigger: {} blocks emitted for message {}", len(blocks), message_id)

        yield {"type": "phase_change", "phase": "complete", "turn_id": turn_id}

        if plugin_summary:
            yield {"type": "plugin_summary", "data": plugin_summary, "turn_id": turn_id}

        # Dispatch blocks (side effects like DB writes) but collect for batch update
        block_context = BlockContext(
            session_id=session_id, project_id=ctx.project.id, db=db,
            state_mgr=state_mgr, autocommit=False, turn_id=turn_id,
            image_overrides=image_overrides, llm_overrides=llm_overrides,
        )
        dispatched_blocks: list[dict] = []
        for i, block in enumerate(blocks):
            block_type = str(block.get("type", "unknown"))
            block_data = block.get("data")
            declaration = ctx.block_declarations.get(block_type) if ctx.block_declarations else None

            validation_errors = validate_block_data(block_type, block_data, declaration)
            if validation_errors:
                logger.warning("Invalid block on retrigger: type={}, errors={}", block_type, validation_errors)
                continue

            try:
                await dispatch_block(block, block_context, ctx.block_declarations, None)
            except Exception:
                logger.exception("Block dispatch failed on retrigger: {}", block.get("type"))
                continue

            if block_type not in {"state_update"}:
                dispatched_blocks.append({
                    "type": block_type,
                    "data": block_data,
                    "block_id": f"{message_id}:{i}",
                })

        # Persist blocks to message metadata
        if dispatched_blocks:
            existing_meta = safe_json_loads(
                msg_obj.metadata_json,
                fallback={},
                context=f"Message metadata ({message_id})",
            )
            if not isinstance(existing_meta, dict):
                existing_meta = {}
            existing_meta["blocks"] = dispatched_blocks
            msg_obj.metadata_json = json.dumps(existing_meta, ensure_ascii=False)
            db.add(msg_obj)

        # Update trigger counts for plugins that emitted blocks
        plugins_counted = _plugins_to_count(plugin_summary)
        if plugins_counted:
            latest_state = safe_json_loads(
                ctx.session.game_state_json,
                fallback={},
                context=f"GameSession state ({session_id})",
            )
            if not isinstance(latest_state, dict):
                latest_state = {}
            latest_trigger_counts = _normalize_plugin_counts(
                latest_state.get("plugin_execution_counts")
            )
            if not latest_trigger_counts:
                latest_trigger_counts = _normalize_plugin_counts(
                    latest_state.get("plugin_trigger_counts")
                )
            for pname in plugins_counted:
                latest_trigger_counts[pname] = int(latest_trigger_counts.get(pname, 0) or 0) + 1
            latest_state["plugin_execution_counts"] = latest_trigger_counts
            latest_state["plugin_trigger_counts"] = latest_trigger_counts
            ctx.session.game_state_json = json.dumps(latest_state)
            db.add(ctx.session)

        await db.commit()

        # Send a single event so the frontend can update the message's blocks in-place
        yield {
            "type": "message_blocks_updated",
            "message_id": message_id,
            "blocks": dispatched_blocks,
            "turn_id": turn_id,
        }
        yield {"type": "turn_end", "turn_id": turn_id}
