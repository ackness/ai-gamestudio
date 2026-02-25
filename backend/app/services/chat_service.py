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
from backend.app.services.session_state import SessionStateAccessor
from backend.app.core.plugin_trigger import (
    BLOCK_TRIGGER_ONCE_PER_SESSION,
    normalize_block_trigger_policy,
)
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
from backend.app.services.debug_log_service import add_debug_log as _add_log


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


_INFRA_BLOCK_TYPES = {"state_update"}


async def _filter_plugin_blocks(
    blocks: list[dict[str, Any]],
    *,
    state_mgr: GameStateManager,
    session_id: str,
    log_prefix: str,
) -> list[dict[str, Any]]:
    """Apply cross-block conflict rules before dispatch."""
    filtered = list(blocks)
    block_types = {b.get("type") for b in filtered}
    if "character_sheet" in block_types:
        suppressed = {"guide", "choices", "auto_guide"}
        before_count = len(filtered)
        filtered = [b for b in filtered if b.get("type") not in suppressed]
        if len(filtered) < before_count:
            logger.debug("{}: suppressed guide/choices blocks due to character_sheet", log_prefix)

    if "character_sheet" in block_types:
        existing_chars = await state_mgr.get_characters(session_id)
        has_player = any(c.role == "player" for c in existing_chars)
        if has_player:
            before_count = len(filtered)
            filtered = [b for b in filtered if b.get("type") != "character_sheet"]
            if len(filtered) < before_count:
                logger.debug("{}: suppressed character_sheet (player exists)", log_prefix)

    return filtered


async def _dispatch_blocks_stage(
    blocks: list[dict[str, Any]],
    *,
    block_context: BlockContext,
    block_declarations: dict[str, Any],
    turn_id: str,
    emit_front_events: bool,
    log_prefix: str,
    block_trigger_counts: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate + dispatch blocks, returning events and metadata payload candidates."""
    events: list[dict[str, Any]] = []
    persisted_blocks: list[dict[str, Any]] = []

    for i, block in enumerate(blocks):
        block_type = str(block.get("type", "unknown"))
        block_data = block.get("data")
        block_id = str(block.get("id") or "").strip() or None
        block_version = str(block.get("version") or "1.0").strip() or "1.0"
        block_meta = block.get("meta") if isinstance(block.get("meta"), dict) else {}
        block_status = str(block.get("status") or "done").strip() or "done"
        declaration = block_declarations.get(block_type) if block_declarations else None
        trigger_policy = normalize_block_trigger_policy(
            getattr(declaration, "trigger", None) if declaration else None
        )
        if (
            trigger_policy.get("mode") == BLOCK_TRIGGER_ONCE_PER_SESSION
            and isinstance(block_trigger_counts, dict)
            and int(block_trigger_counts.get(block_type, 0) or 0) > 0
        ):
            logger.debug(
                "Skip block '{}' on {}: once_per_session already consumed",
                block_type,
                log_prefix,
            )
            continue

        validation_errors = validate_block_data(block_type, block_data, declaration)
        if validation_errors:
            logger.warning(
                "Invalid block on {}: type={}, errors={}",
                log_prefix,
                block_type,
                validation_errors,
            )
            if emit_front_events:
                events.append(
                    {
                        "type": "notification",
                        "data": {
                            "level": "warning",
                            "title": "Block 数据不完整",
                            "content": f"{block_type}: {'; '.join(validation_errors[:2])}",
                        },
                        "turn_id": turn_id,
                    }
                )
            continue

        try:
            result = await dispatch_block(block, block_context, block_declarations, None)
        except Exception:
            logger.exception("Block dispatch failed on {}: {}", log_prefix, block_type)
            continue

        if isinstance(block_trigger_counts, dict):
            block_trigger_counts[block_type] = int(block_trigger_counts.get(block_type, 0) or 0) + 1

        if block_type in _INFRA_BLOCK_TYPES:
            continue

        persisted_blocks.append(
            {
                "type": block_type,
                "data": block_data,
                "index": i,
                "id": block_id,
                "version": block_version,
                "meta": block_meta,
                "status": block_status,
            }
        )
        if not emit_front_events:
            continue

        if isinstance(result, list):
            for r in result:
                r_type = str(r.get("type", "unknown"))
                r_data = r.get("data")
                r_id = str(r.get("id") or "").strip() or None
                r_version = str(r.get("version") or "1.0").strip() or "1.0"
                r_meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
                r_status = str(r.get("status") or "done").strip() or "done"
                events.append(
                    {
                        "type": r_type,
                        "data": r_data,
                        "turn_id": turn_id,
                        "block_id": r_id,
                        "output": {
                            "id": r_id,
                            "version": r_version,
                            "type": r_type,
                            "data": r_data,
                            "meta": r_meta,
                            "status": r_status,
                        },
                    }
                )
        else:
            events.append(
                {
                    "type": block_type,
                    "data": block_data,
                    "turn_id": turn_id,
                    "block_id": block_id,
                    "output": {
                        "id": block_id,
                        "version": block_version,
                        "type": block_type,
                        "data": block_data,
                        "meta": block_meta,
                        "status": block_status,
                    },
                }
            )

    return events, persisted_blocks


def _to_message_blocks(message_id: str, persisted_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert dispatched block payloads to stored message metadata format."""
    out: list[dict[str, Any]] = []
    for b in persisted_blocks:
        block_id = str(b.get("id") or "").strip() or f"{message_id}:{b.get('index', 0)}"
        block_type = b.get("type")
        block_data = b.get("data")
        block_meta = b.get("meta") if isinstance(b.get("meta"), dict) else {}
        block_status = str(b.get("status") or "done")
        block_version = str(b.get("version") or "1.0")
        out.append(
            {
                "type": block_type,
                "data": block_data,
                "block_id": block_id,
                "output": {
                    "id": block_id,
                    "version": block_version,
                    "type": block_type,
                    "data": block_data,
                    "meta": block_meta,
                    "status": block_status,
                },
            }
        )
    return out


def _merge_blocks_into_metadata(
    metadata_json: str | None,
    message_id: str,
    blocks: list[dict[str, Any]],
    llm_calls: dict[str, Any] | None = None,
) -> str:
    existing_meta = safe_json_loads(
        metadata_json,
        fallback={},
        context=f"Message metadata ({message_id})",
    )
    if not isinstance(existing_meta, dict):
        existing_meta = {}
    existing_meta["blocks"] = blocks
    if llm_calls:
        existing_meta["llm_calls"] = llm_calls
    return json.dumps(existing_meta, ensure_ascii=False, default=str)


async def _finalize_turn_stage(
    *,
    db: SQLModelAsyncSession,
    ctx: Any,
    state_mgr: GameStateManager,
    session_id: str,
    should_increment_turn: bool,
    context_usage: float,
    model: str,
    llm_overrides: dict[str, str] | None,
    turn_id: str,
) -> list[dict[str, Any]]:
    """Run post-turn finalize hooks (auto-archive + auto-compress)."""
    events: list[dict[str, Any]] = []

    # Auto archive (memory plugin subsumes archive)
    if should_increment_turn and "memory" in ctx.enabled_names:
        try:
            created = await maybe_auto_archive_summary(db, ctx.project, ctx.session)
            if created:
                events.append(
                    {
                        "type": "notification",
                        "data": {
                            "level": "info",
                            "title": "存档已更新",
                            "content": f"自动生成版本 v{created['version']}",
                        },
                        "turn_id": turn_id,
                    }
                )
        except Exception:
            logger.exception("Auto archive summary failed")

    # Auto compress check (memory plugin subsumes auto-compress)
    if "memory" not in ctx.enabled_names or context_usage <= 0:
        return events

    from backend.app.services.compress_service import should_compress, compress_history

    ac_settings = ctx.runtime_settings_by_plugin.get("memory", {})
    threshold = float(ac_settings.get("compression_threshold", 0.7))
    keep_recent = int(ac_settings.get("keep_recent_messages", 6))
    if not should_compress(context_usage, threshold):
        return events

    try:
        all_messages = await state_mgr.get_messages(session_id, limit=100)
        if len(all_messages) <= keep_recent:
            return events

        messages_to_compress = all_messages[:-keep_recent]
        existing_summary = ctx.compression_summary
        compress_result = await compress_history(
            messages_to_compress,
            existing_summary,
            model=model,
            llm_overrides=llm_overrides,
        )

        await storage_set(
            db,
            ctx.project.id,
            "auto-compress",
            "compression-summary",
            {"summary": compress_result["summary"]},
            autocommit=True,
        )

        prev_state = await _storage_get(
            db,
            ctx.project.id,
            "auto-compress",
            "compression-state",
        )
        prev_count = (
            (prev_state or {}).get("total_compressions", 0)
            if isinstance(prev_state, dict)
            else 0
        )
        await storage_set(
            db,
            ctx.project.id,
            "auto-compress",
            "compression-state",
            {
                "last_compressed_message_count": len(messages_to_compress),
                "total_compressions": prev_count + 1,
            },
            autocommit=True,
        )

        events.append(
            {
                "type": "notification",
                "data": {
                    "level": "info",
                    "title": "上下文已压缩",
                    "content": f"已将 {len(messages_to_compress)} 条旧消息压缩为摘要",
                },
                "turn_id": turn_id,
            }
        )
        logger.info("Auto-compressed {} messages for session {}", len(messages_to_compress), session_id)
    except Exception:
        logger.exception("Auto-compress failed for session {}", session_id)

    return events


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

        # Collect narrative LLM call data for storage
        llm_calls: dict[str, Any] = {
            "narrative": {
                "messages": messages,
                "response": full_response,
                "model": config.model,
                "tokens": {"prompt": prompt_tokens, "completion": completion_tokens},
            },
        }

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
        current_turn = SessionStateAccessor(ctx.session.game_state_json, session_id).load_turn_count()

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
        _state_acc = SessionStateAccessor(ctx.session.game_state_json, session_id)
        trigger_counts = _state_acc.load_plugin_trigger_counts()
        block_trigger_counts = _state_acc.load_block_trigger_counts()
        has_player_character = any(getattr(ch, "role", None) == "player" for ch in ctx.characters)

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
                current_turn=current_turn,
                session_phase=getattr(ctx.session, "phase", None),
                runtime_settings_by_plugin=ctx.runtime_settings_by_plugin,
                block_trigger_counts=block_trigger_counts,
                has_player_character=has_player_character,
                turn_id=turn_id,
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

        blocks = await _filter_plugin_blocks(
            blocks,
            state_mgr=state_mgr,
            session_id=session_id,
            log_prefix="Plugin Agent",
        )

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

        # Collect plugin LLM call data
        if plugin_summary:
            plugin_calls: dict[str, Any] = {}
            for pm in plugin_summary.get("plugin_metrics", []):
                pname = pm.get("plugin", "")
                if pname and "messages" in pm:
                    plugin_calls[pname] = {
                        "messages": pm.pop("messages"),
                        "rounds": pm.get("rounds", 0),
                        "model": plugin_config.model,
                    }
            if plugin_calls:
                llm_calls["plugins"] = plugin_calls

        # 7. Dispatch blocks
        block_trigger_counts_before = dict(block_trigger_counts)
        block_context = BlockContext(
            session_id=session_id, project_id=ctx.project.id, db=db,
            state_mgr=state_mgr, autocommit=False, turn_id=turn_id,
            image_overrides=image_overrides, llm_overrides=llm_overrides,
        )
        stage_events, persisted_blocks = await _dispatch_blocks_stage(
            blocks,
            block_context=block_context,
            block_declarations=ctx.block_declarations,
            turn_id=turn_id,
            emit_front_events=True,
            log_prefix="process_message",
            block_trigger_counts=block_trigger_counts,
        )
        for evt in stage_events:
            yield evt

        # 7b. Persist blocks to message metadata for reload recovery
        if saved_message_id and persisted_blocks:
            dispatched_blocks = _to_message_blocks(saved_message_id, persisted_blocks)
            from backend.app.models.message import Message

            msg_obj = await db.get(Message, saved_message_id)
            if msg_obj:
                msg_obj.metadata_json = _merge_blocks_into_metadata(
                    msg_obj.metadata_json,
                    saved_message_id,
                    dispatched_blocks,
                    llm_calls=llm_calls,
                )
                db.add(msg_obj)

        if block_trigger_counts != block_trigger_counts_before:
            ctx.session.game_state_json = SessionStateAccessor(
                ctx.session.game_state_json, session_id
            ).set_block_trigger_counts(block_trigger_counts)
            db.add(ctx.session)

        # Update trigger counts for plugins that emitted blocks
        plugins_counted = _plugins_to_count(plugin_summary)
        if plugins_counted:
            ctx.session.game_state_json = SessionStateAccessor(
                ctx.session.game_state_json, session_id
            ).increment_plugin_trigger_counts(plugins_counted)
            db.add(ctx.session)

        await db.commit()

        if saved_message_id:
            yield {"type": "_message_saved", "message_id": saved_message_id, "turn_id": turn_id}

        finalize_events = await _finalize_turn_stage(
            db=db,
            ctx=ctx,
            state_mgr=state_mgr,
            session_id=session_id,
            should_increment_turn=should_increment_turn,
            context_usage=context_usage,
            model=config.model,
            llm_overrides=llm_overrides,
            turn_id=turn_id,
        )
        for evt in finalize_events:
            yield evt

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
        _retrigger_state = SessionStateAccessor(ctx.session.game_state_json, session_id)
        retrigger_trigger_counts = _retrigger_state.load_plugin_trigger_counts()
        current_turn = _retrigger_state.load_turn_count()
        block_trigger_counts = _retrigger_state.load_block_trigger_counts()
        has_player_character = any(getattr(ch, "role", None) == "player" for ch in ctx.characters)

        try:
            blocks, plugin_summary = await run_plugin_agent(
                narrative=narrative,
                game_state=state_snapshot,
                enabled_plugins=ctx.enabled_names,
                session_id=session_id,
                game_db=game_db,
                pe=ctx.pe,
                config=plugin_config,
                current_turn=current_turn,
                session_phase=getattr(ctx.session, "phase", None),
                runtime_settings_by_plugin=ctx.runtime_settings_by_plugin,
                block_trigger_counts=block_trigger_counts,
                has_player_character=has_player_character,
                turn_id=turn_id,
                trigger_counts=retrigger_trigger_counts,
            )
        except Exception:
            logger.exception("Plugin Agent retrigger failed for session {}", session_id)
            blocks = []

        blocks = await _filter_plugin_blocks(
            blocks,
            state_mgr=state_mgr,
            session_id=session_id,
            log_prefix="Retrigger",
        )

        logger.info("Retrigger: {} blocks emitted for message {}", len(blocks), message_id)

        yield {"type": "phase_change", "phase": "complete", "turn_id": turn_id}

        if plugin_summary:
            yield {"type": "plugin_summary", "data": plugin_summary, "turn_id": turn_id}

        # Dispatch blocks (side effects like DB writes) but collect for batch update
        block_trigger_counts_before = dict(block_trigger_counts)
        block_context = BlockContext(
            session_id=session_id, project_id=ctx.project.id, db=db,
            state_mgr=state_mgr, autocommit=False, turn_id=turn_id,
            image_overrides=image_overrides, llm_overrides=llm_overrides,
        )
        _, persisted_blocks = await _dispatch_blocks_stage(
            blocks,
            block_context=block_context,
            block_declarations=ctx.block_declarations,
            turn_id=turn_id,
            emit_front_events=False,
            log_prefix="retrigger",
            block_trigger_counts=block_trigger_counts,
        )
        dispatched_blocks = _to_message_blocks(message_id, persisted_blocks)

        # Persist blocks to message metadata
        if dispatched_blocks:
            msg_obj.metadata_json = _merge_blocks_into_metadata(
                msg_obj.metadata_json,
                message_id,
                dispatched_blocks,
            )
            db.add(msg_obj)

        if block_trigger_counts != block_trigger_counts_before:
            ctx.session.game_state_json = SessionStateAccessor(
                ctx.session.game_state_json, session_id
            ).set_block_trigger_counts(block_trigger_counts)
            db.add(ctx.session)

        # Update trigger counts for plugins that emitted blocks
        plugins_counted = _plugins_to_count(plugin_summary)
        if plugins_counted:
            ctx.session.game_state_json = SessionStateAccessor(
                ctx.session.game_state_json, session_id
            ).increment_plugin_trigger_counts(plugins_counted)
            db.add(ctx.session)

        await db.commit()

        yield {"type": "turn_end", "turn_id": turn_id}


async def stream_process_message(
    sink: Any,
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
