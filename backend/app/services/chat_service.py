from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.block_handlers import BlockContext, dispatch_block
from backend.app.core.block_parser import extract_blocks, strip_blocks
from backend.app.core.block_validation import validate_block_data
from backend.app.core.config import settings
from backend.app.core.event_bus import PluginEventBus
from backend.app.core.game_state import GameStateManager
from backend.app.core.llm_config import get_effective_config_for_project
from backend.app.core.llm_gateway import completion_with_config
from backend.app.core.plugin_engine import BlockDeclaration, PluginEngine
from backend.app.core.plugin_registry import get_plugin_engine
from backend.app.core.prompt_builder import PromptBuilder
from backend.app.db.engine import engine
from backend.app.models.project import Project
from backend.app.models.session import GameSession
from backend.app.services.archive_service import (
    ARCHIVE_PLUGIN_NAME,
    ensure_archive_initialized,
    get_archive_prompt_context,
    maybe_auto_archive_summary,
)
from backend.app.services.plugin_service import get_enabled_plugins, storage_get
from backend.app.services.runtime_settings_service import (
    build_runtime_settings_prompt_block,
    resolve_runtime_settings,
)


async def process_message(
    session_id: str,
    user_content: str,
    *,
    save_user_msg: bool = True,
    save_assistant_msg: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Process a user message end-to-end and yield streaming events.

    Yields dicts with keys:
        {"type": "chunk", "content": "..."}
        {"type": "<block_type>", "data": {...}}
        {"type": "error", "content": "..."}
    """
    turn_id = str(uuid.uuid4())

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as db:
        state_mgr = GameStateManager(db, autocommit=False)

        # 1. Load session and project
        game_session = await db.get(GameSession, session_id)
        if not game_session:
            yield {
                "type": "error",
                "content": "Session not found",
                "turn_id": turn_id,
            }
            return

        project = await db.get(Project, game_session.project_id)
        if not project:
            yield {
                "type": "error",
                "content": "Project not found",
                "turn_id": turn_id,
            }
            return

        # Ensure archive storage is ready for this session.
        await ensure_archive_initialized(db, project.id, session_id)

        # 2. Save user message (with current scene_id)
        current_scene = await state_mgr.get_current_scene(session_id)
        current_scene_id = current_scene.id if current_scene else None
        if save_user_msg:
            await state_mgr.add_message(
                session_id, "user", user_content, scene_id=current_scene_id
            )
            await db.commit()

        # 3. Resolve enabled plugins first (required plugins included)
        enabled_names: list[str] = []
        archive_context: dict[str, Any] = {}
        runtime_settings_by_plugin: dict[str, Any] = {}
        runtime_settings_flat: dict[str, Any] = {}
        runtime_settings_prompt: str | None = None
        try:
            enabled = await get_enabled_plugins(
                db, project.id, world_doc=project.world_doc
            )
            enabled_names = [p["plugin_name"] for p in enabled]
            if ARCHIVE_PLUGIN_NAME in enabled_names:
                archive_context = await get_archive_prompt_context(
                    db, project.id, session_id
                )
            resolved_runtime_settings = await resolve_runtime_settings(
                db,
                project_id=project.id,
                session_id=session_id,
                enabled_plugins=enabled_names,
            )
            runtime_settings_by_plugin = dict(
                resolved_runtime_settings.get("by_plugin") or {}
            )
            runtime_settings_flat = dict(
                resolved_runtime_settings.get("values") or {}
            )
            runtime_settings_prompt = build_runtime_settings_prompt_block(
                resolved_runtime_settings
            )
        except Exception:
            logger.exception("Failed to resolve enabled plugins")

        # 4. Get recent messages for context.
        # If archive snapshot exists, reduce history window to compress token usage.
        history_limit = 12 if archive_context.get("has_snapshot") else 30
        recent_messages = await state_mgr.get_messages(session_id, limit=history_limit)

        # 5. Get characters
        characters = await state_mgr.get_characters(session_id)

        # 6. Get active events
        active_events = await state_mgr.get_active_events(session_id)

        # 6.5 Get world/plugin state used by prompt templates
        world_state = await state_mgr.get_world_state(session_id, project.id)
        memories: list[dict[str, Any]] = []
        story_images: list[dict[str, Any]] = []
        if "memory" in enabled_names:
            try:
                short_term = await storage_get(
                    db,
                    project.id,
                    "memory",
                    "short-term-memory",
                )
                long_term = await storage_get(
                    db,
                    project.id,
                    "memory",
                    "long-term-memory",
                )
                candidates: list[Any] = []
                for source in (short_term, long_term):
                    if isinstance(source, list):
                        candidates.extend(source)
                    elif source is not None:
                        candidates.append(source)
                for raw_item in candidates:
                    if isinstance(raw_item, dict):
                        content = str(raw_item.get("content", "")).strip()
                        if not content:
                            continue
                        memories.append(
                            {
                                "timestamp": raw_item.get("timestamp", ""),
                                "content": content,
                            }
                        )
                    elif isinstance(raw_item, str) and raw_item.strip():
                        memories.append({"timestamp": "", "content": raw_item.strip()})
            except Exception:
                logger.exception("Failed to load memory plugin storage")
        if "story-image" in enabled_names:
            try:
                from backend.app.services.image_service import (
                    build_story_image_prompt_context,
                    get_session_story_images,
                )

                raw_images = await get_session_story_images(
                    db,
                    project_id=project.id,
                    session_id=session_id,
                )
                story_images = build_story_image_prompt_context(raw_images)
            except Exception:
                logger.exception("Failed to load story-image plugin storage")

        # 7. Build prompt
        builder = PromptBuilder()

        # System: world doc (strip frontmatter before injecting)
        if project.world_doc:
            try:
                import frontmatter as fm

                parsed = fm.loads(project.world_doc)
                clean_world_doc = parsed.content
            except Exception:
                clean_world_doc = project.world_doc

            builder.inject(
                "system",
                0,
                "You are the Dungeon Master (DM) for a role-playing game.\n\n"
                f"## World Document\n\n{clean_world_doc}",
            )
        else:
            builder.inject(
                "system",
                0,
                "You are the Dungeon Master (DM) for a role-playing game. "
                "No world document has been defined yet. Help the player explore.",
            )

        # Character info
        if characters:
            char_text = "## Characters\n\n"
            for ch in characters:
                char_text += f"- **{ch.name}** ({ch.role}) [id: {ch.id}]"
                if ch.description:
                    char_text += f": {ch.description}"
                if ch.personality:
                    char_text += f"\n  Personality: {ch.personality}"
                attrs = json.loads(ch.attributes_json) if ch.attributes_json else {}
                if attrs:
                    char_text += (
                        f"\n  Attributes: {json.dumps(attrs, ensure_ascii=False)}"
                    )
                inv = json.loads(ch.inventory_json) if ch.inventory_json else []
                if inv:
                    char_text += f"\n  Inventory: {', '.join(str(i) for i in inv)}"
                char_text += "\n"
            builder.inject("character", 10, char_text)

        # Scene context
        scene_npcs: list[dict[str, Any]] = []
        if current_scene:
            scene_npc_rows = await state_mgr.get_scene_npcs(current_scene.id)
            npc_names = []
            for snpc in scene_npc_rows:
                char = next((c for c in characters if c.id == snpc.character_id), None)
                name = char.name if char else snpc.character_id
                role_suffix = f" ({snpc.role_in_scene})" if snpc.role_in_scene else ""
                npc_names.append(f"{name}{role_suffix}")
                scene_npcs.append(
                    {
                        "character_id": snpc.character_id,
                        "name": name,
                        "role_in_scene": snpc.role_in_scene,
                    }
                )

            scene_text = "## Current Scene\n\n"
            scene_text += f"Scene: {current_scene.name}\n"
            if current_scene.description:
                scene_text += f"Description: {current_scene.description}\n"
            if npc_names:
                scene_text += f"NPCs present: {', '.join(npc_names)}\n"
            builder.inject("character", 5, scene_text)

        # Active events (world-state injection)
        if active_events:
            events_text = "## Active Events\n\n"
            for evt in active_events:
                vis_tag = "" if evt.visibility == "known" else " [hidden]"
                events_text += f"- [{evt.event_type}] {evt.name} ({evt.status}) [id: {evt.id}]{vis_tag}"
                if evt.description:
                    events_text += f" — {evt.description}"
                events_text += "\n"
            builder.inject("world-state", 20, events_text)

        session_world_state = world_state.get("session_world_state", {})
        if isinstance(session_world_state, dict) and session_world_state:
            world_state_json = json.dumps(
                session_world_state,
                ensure_ascii=False,
                indent=2,
            )
            if len(world_state_json) > 4000:
                world_state_json = world_state_json[:4000] + "\n... (truncated)"
            builder.inject(
                "world-state",
                15,
                "## Session World State\n\n"
                "The following JSON is the current persistent runtime world state "
                "for this session. Treat it as authoritative when narrating.\n\n"
                f"```json\n{world_state_json}\n```",
            )

        # 8. Inject plugin prompts and collect block declarations
        block_declarations: dict[str, BlockDeclaration] = {}
        pe = get_plugin_engine()
        try:
            if enabled_names:
                character_context = [
                    {
                        "id": c.id,
                        "name": c.name,
                        "role": c.role,
                        "description": c.description,
                        "attributes": json.loads(c.attributes_json)
                        if c.attributes_json
                        else {},
                        "inventory": json.loads(c.inventory_json)
                        if c.inventory_json
                        else [],
                    }
                    for c in characters
                ]
                player_context = next(
                    (c for c in character_context if c["role"] == "player"),
                    None,
                )
                npc_context = [c for c in character_context if c["role"] != "player"]
                context = {
                    "project": {"name": project.name, "world_doc": project.world_doc},
                    "characters": character_context,
                    "current_scene": {
                        "name": current_scene.name,
                        "description": current_scene.description,
                    }
                    if current_scene
                    else None,
                    "active_events": [
                        {
                            "id": e.id,
                            "event_type": e.event_type,
                            "name": e.name,
                            "description": e.description,
                            "status": e.status,
                            "visibility": e.visibility,
                        }
                        for e in active_events
                    ],
                    # Compatibility fields for plugin prompt templates.
                    "player": player_context,
                    "npcs": npc_context,
                    "scene_npcs": scene_npcs,
                    "world_state": world_state,
                    "memories": memories,
                    "runtime_settings": runtime_settings_by_plugin,
                    "runtime_settings_flat": runtime_settings_flat,
                    "story_images": story_images,
                    "archive": archive_context,
                }
                injections = pe.get_prompt_injections(enabled_names, context)
                for inj in injections:
                    content = str(inj.get("content", "") or "").strip()
                    if not content:
                        continue
                    builder.inject(
                        inj["position"],
                        inj["priority"],
                        content,
                    )
                # Collect block declarations from enabled plugins
                block_declarations = pe.get_block_declarations(enabled_names)
        except Exception:
            logger.exception("Failed to inject plugin prompts")

        # Chat history
        if save_user_msg:
            # Exclude the message we just saved (last in recent_messages)
            for i, msg in enumerate(recent_messages[:-1]):
                builder.inject("chat-history", i, f"{msg.role}: {msg.content}")
        else:
            # User message was not saved, so recent_messages doesn't include it
            for i, msg in enumerate(recent_messages):
                builder.inject("chat-history", i, f"{msg.role}: {msg.content}")

        # Current user message as last chat-history entry
        builder.inject(
            "chat-history", len(recent_messages) + 1, f"user: {user_content}"
        )

        # Pre-response instructions (block format guidance, built from plugin declarations)
        builder.inject(
            "pre-response",
            0,
            _build_pre_response_instructions(block_declarations),
        )
        if runtime_settings_prompt:
            builder.inject(
                "pre-response",
                5,
                runtime_settings_prompt,
            )

        # 9. Build messages and call LLM
        messages = builder.build()
        config = get_effective_config_for_project(project)
        logger.info(f"Using LLM: model={config.model}, source={config.source}")

        try:
            full_response = ""
            stream = await completion_with_config(
                messages,
                config,
                stream=True,
            )
            async for chunk in stream:
                full_response += chunk
                yield {"type": "chunk", "content": chunk, "turn_id": turn_id}

        except Exception as exc:
            logger.exception("LLM call failed")
            error_msg = _format_llm_error(exc, config.model)
            yield {"type": "error", "content": error_msg, "turn_id": turn_id}
            return

        # Log full LLM response for debugging
        logger.info("LLM response ({} chars): {}", len(full_response), full_response)

        # 10. Extract and dispatch all json:xxx blocks
        blocks = extract_blocks(full_response)
        if blocks:
            logger.info(
                "Extracted {} block(s): {}", len(blocks), [b["type"] for b in blocks]
            )
            # Log full block data for debugging
            for block in blocks:
                logger.debug("Block type={}, data={}", block["type"], block["data"])

        # Create event bus and register plugin event listeners
        event_bus = PluginEventBus()
        _register_event_listeners(event_bus, pe, enabled_names)

        block_context = BlockContext(
            session_id=session_id,
            project_id=project.id,
            db=db,
            state_mgr=state_mgr,
            event_bus=event_bus,
            autocommit=False,
            turn_id=turn_id,
        )

        processed_blocks: list[dict[str, Any]] = []
        clean_response = strip_blocks(full_response)
        has_content = clean_response.strip() or blocks
        should_increment_turn = bool(save_assistant_msg and has_content)
        stage_b_has_writes = bool(blocks)

        try:
            for idx, block in enumerate(blocks):
                block_id = f"{turn_id}:{idx}"
                block_type = str(block.get("type", "unknown"))
                block_data = block.get("data")
                declaration = (
                    block_declarations.get(block_type)
                    if block_declarations
                    else None
                )
                validation_errors = validate_block_data(
                    block_type,
                    block_data,
                    declaration,
                )
                if validation_errors:
                    logger.warning(
                        "Invalid block skipped: type={}, errors={}",
                        block_type,
                        validation_errors,
                    )
                    processed_blocks.append(
                        {
                            "type": "notification",
                            "data": {
                                "level": "error",
                                "title": "结构化数据已忽略",
                                "content": (
                                    f"无效 block: {block_type} "
                                    f"({'; '.join(validation_errors[:2])})"
                                ),
                            },
                            "block_id": f"{block_id}:validation_error",
                        }
                    )
                    continue

                enriched = await dispatch_block(
                    block, block_context, block_declarations
                )
                processed_blocks.append(
                    {
                        "type": enriched["type"],
                        "data": enriched["data"],
                        "block_id": block_id,
                    }
                )

            # Drain event bus (process any events emitted by block handlers)
            await event_bus.drain(block_context)

            # 11. Refresh current scene (may have changed due to scene_update block)
            updated_scene = await state_mgr.get_current_scene(session_id)
            updated_scene_id = updated_scene.id if updated_scene else current_scene_id

            # 12. Save assistant message with raw_content
            # Save when there's text content OR when there are blocks (e.g., json:guide with no narration)
            if save_assistant_msg and has_content:
                block_summary = [
                    {
                        "type": b["type"],
                        "data": b["data"],
                        "block_id": b.get("block_id"),
                    }
                    for b in processed_blocks
                ]
                logger.info(
                    "Saving assistant message: text_len={}, blocks={}, raw_len={}",
                    len(clean_response),
                    [b["type"] for b in processed_blocks],
                    len(full_response),
                )
                await state_mgr.add_message(
                    session_id,
                    "assistant",
                    clean_response,
                    message_type="narration",
                    metadata={"blocks": block_summary} if block_summary else None,
                    raw_content=full_response,
                    scene_id=updated_scene_id,
                )
                stage_b_has_writes = True

            # 13. Increment turn count
            if should_increment_turn:
                game_state = json.loads(game_session.game_state_json or "{}")
                game_state["turn_count"] = game_state.get("turn_count", 0) + 1
                game_session.game_state_json = json.dumps(game_state)
                db.add(game_session)
                stage_b_has_writes = True

            if stage_b_has_writes:
                await db.commit()

        except Exception:
            await db.rollback()
            logger.exception("Failed to finalize turn {}", turn_id)
            yield {
                "type": "error",
                "content": "回合状态保存失败，请重试",
                "turn_id": turn_id,
            }
            return

        for block in processed_blocks:
            yield {
                "type": block["type"],
                "data": block["data"],
                "block_id": block.get("block_id"),
                "turn_id": turn_id,
            }

        # 14. Auto archive summary (interval-based).
        if should_increment_turn and ARCHIVE_PLUGIN_NAME in enabled_names:
            try:
                created = await maybe_auto_archive_summary(
                    db, project, game_session
                )
                if created:
                    yield {
                        "type": "notification",
                        "data": {
                            "level": "info",
                            "title": "存档已更新",
                            "content": f"自动生成版本 v{created['version']}",
                        },
                        "turn_id": turn_id,
                    }
            except Exception:
                logger.exception("Auto archive summary failed")


def _register_event_listeners(
    event_bus: PluginEventBus,
    pe: PluginEngine,
    enabled_names: list[str],
) -> None:
    """Register event listeners declared in plugin PLUGIN.md ``events.listen``."""
    from backend.app.core.block_handlers import DeclarativeBlockHandler

    for name in enabled_names:
        data = pe.load(name)
        if not data:
            continue
        events_cfg = data["metadata"].get("events")
        if not events_cfg or not isinstance(events_cfg, dict):
            continue
        listen_cfg = events_cfg.get("listen")
        if not listen_cfg or not isinstance(listen_cfg, list):
            continue
        for entry in listen_cfg:
            if isinstance(entry, dict):
                for event_name, handler_cfg in entry.items():
                    actions = (
                        handler_cfg.get("actions", [])
                        if isinstance(handler_cfg, dict)
                        else []
                    )
                    if actions:
                        dh = DeclarativeBlockHandler(actions, name)

                        async def _listener(
                            event_data: dict,
                            ctx: "BlockContext",
                            _handler: DeclarativeBlockHandler = dh,
                        ) -> None:
                            await _handler.process(event_data, ctx)

                        event_bus.register(event_name, _listener)


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

    # Fallback: include exception type for debugging
    return f"LLM 调用失败 ({exc_type}): {exc}"


def _build_pre_response_instructions(
    block_declarations: dict[str, BlockDeclaration] | None = None,
) -> str:
    """Build the pre-response block format instructions for the LLM.

    When block_declarations are provided (from plugin PLUGIN.md frontmatter),
    instructions are dynamically assembled from each declaration's ``instruction``
    field. Falls back to a minimal generic message when no declarations exist.
    """
    header = (
        "Respond in character as the DM. You may include structured data blocks "
        "in your response using fenced code blocks.\n\n"
        "**IMPORTANT FORMAT RULE**: Every structured data block MUST use triple-backtick "
        "fences with the `json:<type>` tag. The correct format is:\n"
        "```\n"
        "```json:<type>\n"
        '{"key": "value"}\n'
        "```\n"
        "```\n"
        "Do NOT omit the triple backticks. Do NOT use plain `json:<type>` without fences.\n\n"
    )

    if block_declarations:
        sections: list[str] = []
        for i, (block_type, decl) in enumerate(block_declarations.items(), 1):
            if decl.instruction:
                sections.append(f"{i}. **{block_type}**:\n{decl.instruction.strip()}")
        if sections:
            header += "Available block types:\n\n"
            header += "\n\n".join(sections)
            header += (
                "\n\nInclude blocks at the end of your narrative text. "
                "You may include multiple blocks in a single response. "
                "Each block MUST be wrapped in triple-backtick fences as shown above."
            )
            return header

    # Fallback when no plugin declarations are available
    header += (
        "You may output structured data as ```json:<type>``` blocks at the end "
        "of your narrative text when game state changes occur."
    )
    return header
