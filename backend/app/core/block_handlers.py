from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.game_state import GameStateManager

if TYPE_CHECKING:
    from backend.app.core.capability_executor import CapabilityExecutor
    from backend.app.core.event_bus import PluginEventBus
    from backend.app.core.plugin_engine import BlockDeclaration


@dataclass
class BlockContext:
    session_id: str
    project_id: str
    db: AsyncSession
    state_mgr: GameStateManager
    event_bus: PluginEventBus | None = field(default=None)
    autocommit: bool = True
    turn_id: str | None = None
    image_overrides: dict[str, str] | None = None
    llm_overrides: dict[str, str] | None = None


class BlockHandler(Protocol):
    async def process(self, data: dict, context: BlockContext) -> dict | None: ...


# ---- Registry ----

_handlers: dict[str, BlockHandler] = {}


def register_block_handler(block_type: str, handler: BlockHandler) -> None:
    _handlers[block_type] = handler


def get_block_handler(block_type: str) -> BlockHandler | None:
    return _handlers.get(block_type)


async def dispatch_block(
    block: dict,
    context: BlockContext,
    block_declarations: dict[str, BlockDeclaration] | None = None,
    capability_executor: "CapabilityExecutor | None" = None,
) -> dict | list[dict]:
    """Look up handler for block type, call process, return (possibly enriched) block.

    For plugin_use blocks, returns a list of result blocks from CapabilityExecutor.
    For all other blocks, returns a single block dict.
    """
    block_type = block.get("type", "")

    # 0. plugin_use → CapabilityExecutor
    if block_type == "plugin_use" and capability_executor is not None:
        result = await capability_executor.execute(
            block.get("data", {}),
            context={"session_id": context.session_id, "project_id": context.project_id},
        )
        if result.success and result.result_blocks:
            return result.result_blocks
        elif not result.success:
            logger.warning("plugin_use failed: {}", result.error)
            return {"type": "notification", "data": {
                "level": "warning",
                "title": "Plugin capability failed",
                "content": result.error,
            }}
        return block

    # 1. Check built-in handler registry (highest priority, backward compatible)
    handler = get_block_handler(block_type)
    if handler is not None:
        result = await handler.process(block.get("data", {}), context)
        if result is not None:
            block["data"] = result
        return block

    # 2. Check plugin-declared handlers
    if block_declarations and block_type in block_declarations:
        decl = block_declarations[block_type]
        if decl.handler and decl.handler.get("actions"):
            dh = DeclarativeBlockHandler(decl.handler["actions"], decl.plugin_name)
            result = await dh.process(block.get("data", {}), context)
            if result is not None:
                block["data"] = result
            return block

    # 3. No handler — pass through unchanged (forwarded to frontend)
    return block


class DeclarativeBlockHandler:
    """Processes blocks based on declarative actions from PLUGIN.md handler config."""

    def __init__(self, actions: list[dict], plugin_name: str):
        self.actions = actions
        self.plugin_name = plugin_name

    async def process(self, data: dict, context: BlockContext) -> dict | None:
        from backend.app.services.plugin_service import storage_set

        for action in self.actions:
            action_type = action.get("type", "")
            try:
                if action_type == "builtin":
                    # Delegate to a registered built-in handler
                    builtin = get_block_handler(action["handler_name"])
                    if builtin:
                        result = await builtin.process(data, context)
                        if result is not None:
                            data = result

                elif action_type == "storage_write":
                    key = action.get("key", "data")
                    await storage_set(
                        context.db,
                        context.project_id,
                        self.plugin_name,
                        key,
                        data,
                        autocommit=context.autocommit,
                    )

                elif action_type == "emit_event":
                    event_name = action.get("event")
                    if event_name and context.event_bus:
                        context.event_bus.emit(event_name, data)

                elif action_type == "update_character":
                    await context.state_mgr.upsert_character(
                        context.session_id, data
                    )

                elif action_type == "create_event":
                    await context.state_mgr.create_event(
                        session_id=context.session_id,
                        event_type=data.get("event_type", "world"),
                        name=data.get("name", "未知事件"),
                        description=data.get("description", ""),
                    )

                else:
                    logger.warning(
                        "Unknown declarative action type '%s' in plugin '%s'",
                        action_type,
                        self.plugin_name,
                    )
            except Exception:
                logger.exception(
                    "Declarative action '%s' failed in plugin '%s'",
                    action_type,
                    self.plugin_name,
                )
                # In transaction mode, fail fast so caller can rollback stage writes.
                if not context.autocommit:
                    raise
        return data


# ---- Built-in handlers ----


class StateUpdateHandler:
    async def process(self, data: dict, context: BlockContext) -> dict | None:
        import json as _json

        mgr = context.state_mgr
        # Update characters and collect enriched records with DB ids
        if "characters" in data:
            enriched = []
            for char_data in data["characters"]:
                char = await mgr.upsert_character(context.session_id, char_data)
                enriched.append(
                    {
                        "id": char.id,
                        "name": char.name,
                        "role": char.role,
                        "description": char.description,
                        "personality": char.personality,
                        "attributes": _json.loads(char.attributes_json)
                        if char.attributes_json
                        else {},
                        "inventory": _json.loads(char.inventory_json)
                        if char.inventory_json
                        else [],
                    }
                )
            data["characters"] = enriched
        # Update world state
        if "world" in data:
            await mgr.update_world_state(context.session_id, data["world"])
            data["world"] = await mgr.get_session_world_state(context.session_id)
        return data


class CharacterSheetHandler:
    async def process(self, data: dict, context: BlockContext) -> dict | None:
        mgr = context.state_mgr
        character_id = data.get("character_id")
        if character_id == "new" or not character_id:
            # Create new character
            char = await mgr.upsert_character(context.session_id, data)
            data["character_id"] = char.id
        else:
            # Update existing character
            data["id"] = character_id
            char = await mgr.upsert_character(context.session_id, data)
            data["character_id"] = char.id
        return data


class SceneUpdateHandler:
    async def _ensure_npc(self, mgr: GameStateManager, session_id: str, npc: dict) -> str | None:
        """Ensure NPC has a Character record, create if not exists."""
        char_id = npc.get("character_id")
        if not char_id:
            return None
        from backend.app.models.character import Character

        existing = await mgr.session.get(Character, char_id)
        if not existing:
            char = await mgr.upsert_character(session_id, {
                "character_id": char_id,
                "name": npc.get("name", "未知角色"),
                "role": "npc",
                "description": npc.get("description"),
            })
            return char.id
        return char_id

    async def process(self, data: dict, context: BlockContext) -> dict | None:
        mgr = context.state_mgr
        action = data.get("action", "move")

        if action == "move":
            scene_name = data.get("name", "未知地点")
            description = data.get("description")
            scene = await mgr.create_scene(
                context.session_id, scene_name, description
            )
            await mgr.set_current_scene(context.session_id, scene.id)
            # Add NPCs if specified
            for npc in data.get("npcs", []):
                char_id = await self._ensure_npc(mgr, context.session_id, npc)
                if char_id:
                    await mgr.add_scene_npc(
                        scene.id, char_id, npc.get("role_in_scene")
                    )
            data["scene_id"] = scene.id

        elif action == "update":
            scene = await mgr.get_current_scene(context.session_id)
            if scene:
                if "description" in data:
                    scene.description = data["description"]
                    from datetime import datetime, timezone

                    scene.updated_at = datetime.now(timezone.utc)
                    mgr.session.add(scene)
                    if context.autocommit:
                        await mgr.session.commit()
                    else:
                        await mgr.session.flush()
                # Add new NPCs
                for npc in data.get("npcs", []):
                    char_id = await self._ensure_npc(mgr, context.session_id, npc)
                    if char_id:
                        await mgr.add_scene_npc(
                            scene.id, char_id, npc.get("role_in_scene")
                        )
                data["scene_id"] = scene.id

        return data


class EventHandler:
    async def process(self, data: dict, context: BlockContext) -> dict | None:
        mgr = context.state_mgr
        action = data.get("action", "create")

        if action == "create":
            event = await mgr.create_event(
                session_id=context.session_id,
                event_type=data.get("event_type", "world"),
                name=data.get("name", "未知事件"),
                description=data.get("description", ""),
                parent_event_id=data.get("parent_event_id"),
                source=data.get("source", "dm"),
                visibility=data.get("visibility", "known"),
                metadata=data.get("metadata"),
            )
            data["event_id"] = event.id

        elif action == "evolve":
            parent_id = data.get("event_id") or data.get("parent_event_id")
            if parent_id:
                await mgr.update_event(parent_id, status="evolved")
                child = await mgr.create_event(
                    session_id=context.session_id,
                    event_type=data.get("event_type", "world"),
                    name=data.get("name", "演变事件"),
                    description=data.get("description", ""),
                    parent_event_id=parent_id,
                    source=data.get("source", "dm"),
                    visibility=data.get("visibility", "known"),
                    metadata=data.get("metadata"),
                )
                data["event_id"] = child.id

        elif action in ("resolve", "end"):
            event_id = data.get("event_id")
            if event_id:
                status = "resolved" if action == "resolve" else "ended"
                await mgr.update_event(event_id, status=status)

        return data


class StoryImageHandler:
    async def process(self, data: dict, context: BlockContext) -> dict | None:
        if not isinstance(data, dict):
            return {
                "status": "error",
                "error": "story_image block data must be an object",
                "can_regenerate": True,
            }

        title = str(data.get("title") or "Story Image")
        story_background = str(data.get("story_background") or "")
        prompt = str(data.get("prompt") or "")
        continuity_notes = str(data.get("continuity_notes") or "")
        refs = data.get("reference_image_ids")
        reference_image_ids = (
            [str(item).strip() for item in refs if str(item).strip()]
            if isinstance(refs, list)
            else []
        )
        raw_scene_frames = data.get("scene_frames")
        scene_frames = (
            [str(item).strip() for item in raw_scene_frames if str(item).strip()]
            if isinstance(raw_scene_frames, list)
            else []
        )
        layout_preference = str(data.get("layout_preference") or "auto")

        # Return a "generating" placeholder immediately.
        # The actual generation is deferred to a background task by the caller
        # (see chat.py _stream_process_message) so it does NOT block the
        # WebSocket message loop.
        return {
            "status": "generating",
            "title": title,
            "story_background": story_background,
            "prompt": prompt,
            "continuity_notes": continuity_notes,
            "reference_image_ids": reference_image_ids,
            "scene_frames": scene_frames,
            "layout_preference": layout_preference,
            "can_regenerate": False,
            "_deferred": True,
            "_generation_params": {
                "project_id": context.project_id,
                "session_id": context.session_id,
                "title": title,
                "story_background": story_background,
                "prompt": prompt,
                "continuity_notes": continuity_notes,
                "reference_image_ids": reference_image_ids,
                "scene_frames": scene_frames,
                "layout_preference": layout_preference,
                "turn_id": context.turn_id,
                "image_overrides": context.image_overrides,
                "llm_overrides": context.llm_overrides,
            },
        }


# ---- Register built-in handlers at import time ----

register_block_handler("state_update", StateUpdateHandler())
register_block_handler("character_sheet", CharacterSheetHandler())
register_block_handler("scene_update", SceneUpdateHandler())
register_block_handler("event", EventHandler())
register_block_handler("story_image_builtin", StoryImageHandler())
