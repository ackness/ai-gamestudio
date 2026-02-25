from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.config import settings
from backend.app.core.game_state import GameStateManager
from backend.app.core.plugin_engine import BlockDeclaration, PluginEngine
from backend.app.core.plugin_registry import get_plugin_engine
from backend.app.models.project import Project
from backend.app.models.session import GameSession
from backend.app.services.archive_service import (
    ensure_archive_initialized,
    get_archive_prompt_context,
)
from backend.app.services.plugin_service import get_enabled_plugins, storage_get
from backend.app.services.runtime_settings_service import (
    resolve_runtime_settings,
)


@dataclass
class TurnContext:
    session: GameSession
    project: Project
    characters: list[Any] = field(default_factory=list)
    scenes: list[Any] = field(default_factory=list)
    active_events: list[Any] = field(default_factory=list)
    world_state: dict[str, Any] = field(default_factory=dict)
    memories: list[dict[str, Any]] = field(default_factory=list)
    story_images: list[dict[str, Any]] = field(default_factory=list)
    enabled_names: list[str] = field(default_factory=list)
    archive_context: dict[str, Any] = field(default_factory=dict)
    runtime_settings_by_plugin: dict[str, Any] = field(default_factory=dict)
    runtime_settings_flat: dict[str, Any] = field(default_factory=dict)
    block_declarations: dict[str, BlockDeclaration] = field(default_factory=dict)
    capability_declarations: list[dict[str, Any]] = field(default_factory=list)
    current_scene: Any | None = None
    current_scene_id: str | None = None
    scene_npcs: list[dict[str, Any]] = field(default_factory=list)
    compression_summary: str = ""
    recent_messages: list[Any] = field(default_factory=list)
    pe: PluginEngine | None = None


async def build_turn_context(
    db: SQLModelAsyncSession,
    session_id: str,
    state_mgr: GameStateManager,
) -> TurnContext | None:
    """Load all data needed for a turn. Returns None if session/project not found."""
    game_session = await db.get(GameSession, session_id)
    if not game_session:
        return None

    project = await db.get(Project, game_session.project_id)
    if not project:
        return None

    await ensure_archive_initialized(db, project.id, session_id)

    current_scene = await state_mgr.get_current_scene(session_id)
    current_scene_id = current_scene.id if current_scene else None

    # Resolve enabled plugins
    enabled_names: list[str] = []
    archive_context: dict[str, Any] = {}
    runtime_settings_by_plugin: dict[str, Any] = {}
    runtime_settings_flat: dict[str, Any] = {}
    try:
        enabled = await get_enabled_plugins(db, project.id, world_doc=project.world_doc)
        enabled_names = [p["plugin_name"] for p in enabled]
        if "memory" in enabled_names:
            archive_context = await get_archive_prompt_context(db, project.id, session_id)
        resolved = await resolve_runtime_settings(
            db, project_id=project.id, session_id=session_id, enabled_plugins=enabled_names,
        )
        runtime_settings_by_plugin = dict(resolved.get("by_plugin") or {})
        runtime_settings_flat = dict(resolved.get("values") or {})
    except Exception:
        logger.exception("Failed to resolve enabled plugins")

    # History
    history_limit = 12 if archive_context.get("has_snapshot") else 30
    recent_messages = await state_mgr.get_messages(session_id, limit=history_limit)

    characters = await state_mgr.get_characters(session_id)
    active_events = await state_mgr.get_active_events(session_id)
    world_state = await state_mgr.get_world_state(session_id, project.id)

    # Memory plugin
    memories = await _load_memories(db, project.id, enabled_names)

    # Compression summary (memory plugin subsumes auto-compress)
    compression_summary = await _load_compression_summary(db, project.id, enabled_names)

    # Adjust history limit based on compression
    if compression_summary:
        ac_settings = runtime_settings_by_plugin.get("memory", {})
        keep_recent = int(ac_settings.get("keep_recent_messages", 6))
        history_limit = min(history_limit, keep_recent + 4)
        recent_messages = await state_mgr.get_messages(session_id, limit=history_limit)

    # Story image plugin
    story_images = await _load_story_images(db, project.id, session_id, enabled_names)

    # Plugin prompt injections and block/capability declarations
    block_declarations: dict[str, BlockDeclaration] = {}
    capability_declarations: list[dict[str, Any]] = []
    pe = get_plugin_engine()

    scene_npcs: list[dict[str, Any]] = []
    if current_scene:
        scene_npc_rows = await state_mgr.get_scene_npcs(current_scene.id)
        for snpc in scene_npc_rows:
            char = next((c for c in characters if c.id == snpc.character_id), None)
            name = char.name if char else snpc.character_id
            scene_npcs.append({
                "character_id": snpc.character_id,
                "name": name,
                "role_in_scene": snpc.role_in_scene,
            })

    try:
        if enabled_names:
            block_declarations = pe.get_block_declarations(enabled_names)
            try:
                capability_declarations = pe.get_capability_declarations(
                    enabled_names, settings.PLUGINS_DIR
                )
            except Exception:
                logger.exception("Failed to get capability declarations")
    except Exception:
        logger.exception("Failed to get block declarations")

    return TurnContext(
        session=game_session,
        project=project,
        characters=characters,
        active_events=active_events,
        world_state=world_state,
        memories=memories,
        compression_summary=compression_summary,
        story_images=story_images,
        enabled_names=enabled_names,
        archive_context=archive_context,
        runtime_settings_by_plugin=runtime_settings_by_plugin,
        runtime_settings_flat=runtime_settings_flat,
        block_declarations=block_declarations,
        capability_declarations=capability_declarations,
        current_scene=current_scene,
        current_scene_id=current_scene_id,
        scene_npcs=scene_npcs,
        recent_messages=recent_messages,
        pe=pe,
    )


async def _load_memories(
    db: SQLModelAsyncSession, project_id: str, enabled_names: list[str],
) -> list[dict[str, Any]]:
    if "memory" not in enabled_names:
        return []
    memories: list[dict[str, Any]] = []
    try:
        short_term = await storage_get(db, project_id, "memory", "short-term-memory")
        long_term = await storage_get(db, project_id, "memory", "long-term-memory")
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
                memories.append({"timestamp": raw_item.get("timestamp", ""), "content": content})
            elif isinstance(raw_item, str) and raw_item.strip():
                memories.append({"timestamp": "", "content": raw_item.strip()})
    except Exception:
        logger.exception("Failed to load memory plugin storage")
    return memories


async def _load_compression_summary(
    db: SQLModelAsyncSession, project_id: str, enabled_names: list[str],
) -> str:
    """Load the compression summary from plugin storage (memory subsumes auto-compress)."""
    if "memory" not in enabled_names:
        return ""
    try:
        data = await storage_get(db, project_id, "auto-compress", "compression-summary")
        if isinstance(data, dict):
            return str(data.get("summary", ""))
        if isinstance(data, str):
            return data
        return ""
    except Exception:
        logger.exception("Failed to load compression summary")
        return ""


async def _load_story_images(
    db: SQLModelAsyncSession, project_id: str, session_id: str, enabled_names: list[str],
) -> list[dict[str, Any]]:
    if "image" not in enabled_names:
        return []
    try:
        from backend.app.services.image_service import (
            build_story_image_prompt_context,
            get_session_story_images,
        )
        raw_images = await get_session_story_images(db, project_id=project_id, session_id=session_id)
        return build_story_image_prompt_context(raw_images)
    except Exception:
        logger.exception("Failed to load story-image plugin storage")
        return []
