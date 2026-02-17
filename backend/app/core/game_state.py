from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.character import Character
from backend.app.models.game_event import GameEvent
from backend.app.models.message import Message
from backend.app.models.project import Project
from backend.app.models.scene import Scene
from backend.app.models.scene_npc import SceneNPC
from backend.app.models.session import GameSession


class GameStateManager:
    def __init__(self, session: AsyncSession, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit

    async def _finalize_write(
        self,
        instance: object | None = None,
        *,
        refresh: bool = False,
    ) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
        if refresh and instance is not None:
            await self.session.refresh(instance)

    async def get_messages(
        self, session_id: str, limit: int = 50
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())  # type: ignore[union-attr]
            .limit(limit)
        )
        result = await self.session.exec(stmt)
        messages = list(result.all())
        messages.reverse()  # chronological order
        return messages

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_type: str = "chat",
        metadata: dict | None = None,
        raw_content: str | None = None,
        scene_id: str | None = None,
    ) -> Message:
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            message_type=message_type,
            metadata_json=json.dumps(metadata) if metadata else None,
            raw_content=raw_content,
            scene_id=scene_id,
        )
        self.session.add(msg)
        await self._finalize_write(msg, refresh=True)
        return msg

    async def get_characters(self, session_id: str) -> list[Character]:
        stmt = select(Character).where(Character.session_id == session_id)
        result = await self.session.exec(stmt)
        return list(result.all())

    @staticmethod
    def _deep_merge_dict(
        base: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            current = merged.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                merged[key] = GameStateManager._deep_merge_dict(current, value)
            else:
                merged[key] = value
        return merged

    async def get_session_world_state(self, session_id: str) -> dict[str, Any]:
        game_session = await self.session.get(GameSession, session_id)
        if not game_session:
            return {}
        try:
            game_state = json.loads(game_session.game_state_json or "{}")
        except Exception:
            return {}
        world_state = game_state.get("world_state", {})
        return world_state if isinstance(world_state, dict) else {}

    async def get_world_state(
        self,
        session_id: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        world_state = await self.get_session_world_state(session_id)

        payload: dict[str, Any] = {"session_world_state": world_state}
        if project_id:
            stmt = select(Project).where(Project.id == project_id)
            result = await self.session.exec(stmt)
            project = result.first()
            if project:
                payload["world_doc"] = project.world_doc
                payload["project_name"] = project.name
        return payload

    async def update_world_state(self, session_id: str, updates: dict) -> None:
        game_session = await self.session.get(GameSession, session_id)
        if not game_session:
            return

        try:
            game_state = json.loads(game_session.game_state_json or "{}")
        except Exception:
            game_state = {}
        if not isinstance(game_state, dict):
            game_state = {}

        current_world_state = game_state.get("world_state", {})
        if not isinstance(current_world_state, dict):
            current_world_state = {}

        delete_keys_raw = updates.get("_delete")
        delete_keys: list[str] = []
        if isinstance(delete_keys_raw, list):
            for item in delete_keys_raw:
                if isinstance(item, str) and item:
                    delete_keys.append(item)

        patch = {k: v for k, v in updates.items() if k != "_delete"}
        if patch:
            current_world_state = self._deep_merge_dict(current_world_state, patch)
        for key in delete_keys:
            current_world_state.pop(key, None)

        game_state["world_state"] = current_world_state
        game_session.game_state_json = json.dumps(game_state, ensure_ascii=False)
        game_session.updated_at = datetime.now(timezone.utc)
        self.session.add(game_session)
        await self._finalize_write()

    # ---- Scene methods ----

    async def create_scene(
        self, session_id: str, name: str, description: str | None = None
    ) -> Scene:
        scene = Scene(session_id=session_id, name=name, description=description)
        self.session.add(scene)
        await self._finalize_write(scene, refresh=True)
        return scene

    async def get_current_scene(self, session_id: str) -> Scene | None:
        stmt = select(Scene).where(
            Scene.session_id == session_id, Scene.is_current == True  # noqa: E712
        )
        result = await self.session.exec(stmt)
        return result.first()

    async def set_current_scene(self, session_id: str, scene_id: str) -> None:
        # Unset all current scenes for this session
        stmt = select(Scene).where(
            Scene.session_id == session_id, Scene.is_current == True  # noqa: E712
        )
        result = await self.session.exec(stmt)
        for scene in result.all():
            scene.is_current = False
            self.session.add(scene)
        # Set the target scene as current
        target = await self.session.get(Scene, scene_id)
        if target:
            target.is_current = True
            target.updated_at = datetime.now(timezone.utc)
            self.session.add(target)
        await self._finalize_write()

    async def get_scenes(self, session_id: str) -> list[Scene]:
        stmt = (
            select(Scene)
            .where(Scene.session_id == session_id)
            .order_by(Scene.created_at.asc())  # type: ignore[arg-type]
        )
        result = await self.session.exec(stmt)
        return list(result.all())

    async def add_scene_npc(
        self, scene_id: str, character_id: str, role_in_scene: str | None = None
    ) -> SceneNPC:
        npc = SceneNPC(
            scene_id=scene_id, character_id=character_id, role_in_scene=role_in_scene
        )
        self.session.add(npc)
        await self._finalize_write(npc, refresh=True)
        return npc

    async def get_scene_npcs(self, scene_id: str) -> list[SceneNPC]:
        stmt = select(SceneNPC).where(SceneNPC.scene_id == scene_id)
        result = await self.session.exec(stmt)
        return list(result.all())

    # ---- Event methods ----

    async def create_event(
        self,
        session_id: str,
        event_type: str,
        name: str,
        description: str,
        parent_event_id: str | None = None,
        source: str = "dm",
        visibility: str = "known",
        metadata: dict | None = None,
    ) -> GameEvent:
        event = GameEvent(
            session_id=session_id,
            event_type=event_type,
            name=name,
            description=description,
            parent_event_id=parent_event_id,
            source=source,
            visibility=visibility,
            metadata_json=json.dumps(metadata) if metadata else "{}",
        )
        self.session.add(event)
        await self._finalize_write(event, refresh=True)
        return event

    async def get_active_events(self, session_id: str) -> list[GameEvent]:
        stmt = (
            select(GameEvent)
            .where(
                GameEvent.session_id == session_id,
                GameEvent.status == "active",
            )
            .order_by(GameEvent.created_at.asc())  # type: ignore[arg-type]
        )
        result = await self.session.exec(stmt)
        return list(result.all())

    async def update_event(self, event_id: str, **updates: object) -> GameEvent | None:
        event = await self.session.get(GameEvent, event_id)
        if not event:
            return None
        for key, value in updates.items():
            if hasattr(event, key):
                setattr(event, key, value)
        event.updated_at = datetime.now(timezone.utc)
        self.session.add(event)
        await self._finalize_write(event, refresh=True)
        return event

    # ---- Character upsert ----

    async def upsert_character(self, session_id: str, data: dict) -> Character:
        character_id = data.get("character_id") or data.get("id")
        if character_id:
            existing = await self.session.get(Character, character_id)
            if existing:
                self._apply_character_updates(existing, data)
                self.session.add(existing)
                await self._finalize_write(existing, refresh=True)
                return existing
        # Fallback: match by name within the same session to avoid duplicates
        name = data.get("name")
        if name:
            stmt = select(Character).where(
                Character.session_id == session_id,
                Character.name == name,
            )
            result = await self.session.exec(stmt)
            existing = result.first()
            if existing:
                self._apply_character_updates(existing, data)
                self.session.add(existing)
                await self._finalize_write(existing, refresh=True)
                return existing
        # Create new character
        char = Character(
            session_id=session_id,
            name=data.get("name", "未知角色"),
            role=data.get("role", "npc"),
            description=data.get("description"),
            personality=data.get("personality"),
            attributes_json=json.dumps(data.get("attributes", {})),
            inventory_json=json.dumps(data.get("inventory", [])),
        )
        self.session.add(char)
        await self._finalize_write(char, refresh=True)
        return char

    @staticmethod
    def _apply_character_updates(existing: Character, data: dict) -> None:
        for key in ("name", "role", "description", "personality"):
            if key in data:
                setattr(existing, key, data[key])
        if "attributes" in data:
            current = json.loads(existing.attributes_json) if existing.attributes_json else {}
            current.update(data["attributes"])
            existing.attributes_json = json.dumps(current)
        if "inventory" in data:
            existing.inventory_json = json.dumps(data["inventory"])
        existing.updated_at = datetime.now(timezone.utc)
