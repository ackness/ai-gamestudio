from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.llm_config import get_effective_config_for_project
from backend.app.core.llm_gateway import completion
from backend.app.models.character import Character
from backend.app.models.game_event import GameEvent
from backend.app.models.message import Message
from backend.app.models.project import Project
from backend.app.models.scene import Scene
from backend.app.models.scene_npc import SceneNPC
from backend.app.models.session import GameSession
from backend.app.services.plugin_service import storage_get, storage_set

ARCHIVE_PLUGIN_NAME = "archive"
DEFAULT_SUMMARY_INTERVAL_TURNS = 8
DEFAULT_MAX_VERSIONS = 30


def _meta_key(session_id: str) -> str:
    return f"session:{session_id}:meta"


def _versions_key(session_id: str) -> str:
    return f"session:{session_id}:versions"


def _config_key() -> str:
    return "config"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime | None) -> str:
    return (dt or _utcnow()).isoformat()


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return _utcnow()
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return _utcnow()


def _loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _turn_count(game_session: GameSession) -> int:
    state = _loads_json(game_session.game_state_json, {})
    raw = state.get("turn_count", 0)
    try:
        return int(raw)
    except Exception:
        return 0


async def ensure_archive_initialized(
    db: AsyncSession,
    project_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Ensure archive plugin storage exists for a session."""
    meta = await storage_get(db, project_id, ARCHIVE_PLUGIN_NAME, _meta_key(session_id))
    if meta:
        return meta

    config = await storage_get(db, project_id, ARCHIVE_PLUGIN_NAME, _config_key()) or {}
    interval = int(config.get("summary_interval_turns", DEFAULT_SUMMARY_INTERVAL_TURNS))

    initial_state = await _collect_state_snapshot(db, project_id, session_id)
    meta = {
        "current_version": 0,
        "active_version": 0,
        "last_snapshot_turn": 0,
        "last_snapshot_at": None,
        "summary_interval_turns": interval,
        "initial_state": initial_state,
    }

    await storage_set(db, project_id, ARCHIVE_PLUGIN_NAME, _meta_key(session_id), meta)
    if (
        await storage_get(
            db, project_id, ARCHIVE_PLUGIN_NAME, _versions_key(session_id)
        )
        is None
    ):
        await storage_set(
            db, project_id, ARCHIVE_PLUGIN_NAME, _versions_key(session_id), []
        )

    return meta


async def get_archive_prompt_context(
    db: AsyncSession,
    project_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Return compact archive context for prompt injection."""
    meta = await ensure_archive_initialized(db, project_id, session_id)
    versions = (
        await storage_get(
            db, project_id, ARCHIVE_PLUGIN_NAME, _versions_key(session_id)
        )
        or []
    )
    active_version = int(meta.get("active_version", 0) or 0)
    active_entry = _find_version(versions, active_version)

    if not active_entry:
        return {
            "has_snapshot": False,
            "active_version": 0,
            "latest_version": int(meta.get("current_version", 0) or 0),
        }

    return {
        "has_snapshot": True,
        "active_version": active_entry.get("version", 0),
        "latest_version": int(meta.get("current_version", 0) or 0),
        "summary": active_entry.get("summary", ""),
        "title": active_entry.get("title", ""),
        "key_facts": active_entry.get("key_facts", []),
        "pending_threads": active_entry.get("pending_threads", []),
        "next_focus": active_entry.get("next_focus", []),
        "turn": active_entry.get("turn", 0),
        "last_snapshot_at": active_entry.get("created_at"),
    }


async def list_archive_versions(
    db: AsyncSession,
    project_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    meta = await ensure_archive_initialized(db, project_id, session_id)
    versions = (
        await storage_get(
            db, project_id, ARCHIVE_PLUGIN_NAME, _versions_key(session_id)
        )
        or []
    )
    active_version = int(meta.get("active_version", 0) or 0)

    view: list[dict[str, Any]] = []
    for entry in versions:
        summary = str(entry.get("summary", ""))
        view.append(
            {
                "version": int(entry.get("version", 0) or 0),
                "created_at": entry.get("created_at"),
                "trigger": entry.get("trigger", "manual"),
                "title": entry.get("title", ""),
                "summary": summary,
                "summary_excerpt": (summary[:120] + "...")
                if len(summary) > 120
                else summary,
                "turn": int(entry.get("turn", 0) or 0),
                "active": int(entry.get("version", 0) or 0) == active_version,
            }
        )

    view.sort(key=lambda item: item["version"], reverse=True)
    return view


async def maybe_auto_archive_summary(
    db: AsyncSession,
    project: Project,
    game_session: GameSession,
) -> dict[str, Any] | None:
    """Auto summarize every N turns if archive plugin is active."""
    meta = await ensure_archive_initialized(db, project.id, game_session.id)
    interval = int(
        meta.get("summary_interval_turns", DEFAULT_SUMMARY_INTERVAL_TURNS)
        or DEFAULT_SUMMARY_INTERVAL_TURNS
    )
    if interval <= 0:
        return None

    current_turn = _turn_count(game_session)
    last_turn = int(meta.get("last_snapshot_turn", 0) or 0)

    if current_turn <= 0 or current_turn - last_turn < interval:
        return None

    return await create_archive_summary(
        db,
        project=project,
        game_session=game_session,
        trigger="auto",
        reason=f"interval:{interval}",
    )


async def create_archive_summary(
    db: AsyncSession,
    project: Project,
    game_session: GameSession,
    trigger: str = "manual",
    reason: str | None = None,
) -> dict[str, Any]:
    """Create a new archive version by asking LLM to summarize recent actions."""
    meta = await ensure_archive_initialized(db, project.id, game_session.id)
    versions = (
        await storage_get(
            db, project.id, ARCHIVE_PLUGIN_NAME, _versions_key(game_session.id)
        )
        or []
    )

    current_turn = _turn_count(game_session)
    last_snapshot_turn = int(meta.get("last_snapshot_turn", 0) or 0)
    last_snapshot_at = (
        _parse_iso(meta.get("last_snapshot_at"))
        if meta.get("last_snapshot_at")
        else None
    )

    actions = await _collect_actions_since(
        db,
        session_id=game_session.id,
        since=last_snapshot_at,
        limit=48,
    )

    current_state = await _collect_state_snapshot(db, project.id, game_session.id)

    llm_result = await _summarize_with_llm(
        project=project,
        meta=meta,
        current_turn=current_turn,
        trigger=trigger,
        reason=reason,
        actions=actions,
        current_state=current_state,
    )

    next_version = int(meta.get("current_version", 0) or 0) + 1
    now_iso = _to_iso(_utcnow())
    entry = {
        "version": next_version,
        "created_at": now_iso,
        "trigger": trigger,
        "reason": reason,
        "turn": current_turn,
        "source_turn_range": [last_snapshot_turn + 1, current_turn],
        "source_message_count": len(actions),
        "title": llm_result.get("title") or f"Version {next_version}",
        "summary": llm_result.get("summary", ""),
        "key_facts": llm_result.get("key_facts", []),
        "pending_threads": llm_result.get("pending_threads", []),
        "next_focus": llm_result.get("next_focus", []),
        "state_snapshot": current_state,
    }

    versions.append(entry)

    config = await storage_get(db, project.id, ARCHIVE_PLUGIN_NAME, _config_key()) or {}
    max_versions = int(
        config.get("max_versions", DEFAULT_MAX_VERSIONS) or DEFAULT_MAX_VERSIONS
    )
    if max_versions > 0 and len(versions) > max_versions:
        versions = versions[-max_versions:]

    meta["current_version"] = next_version
    meta["active_version"] = next_version
    meta["last_snapshot_turn"] = current_turn
    meta["last_snapshot_at"] = now_iso
    if "summary_interval_turns" not in meta:
        meta["summary_interval_turns"] = int(
            config.get("summary_interval_turns", DEFAULT_SUMMARY_INTERVAL_TURNS)
        )

    await storage_set(
        db, project.id, ARCHIVE_PLUGIN_NAME, _versions_key(game_session.id), versions
    )
    await storage_set(
        db, project.id, ARCHIVE_PLUGIN_NAME, _meta_key(game_session.id), meta
    )

    return {
        "version": next_version,
        "created_at": now_iso,
        "trigger": trigger,
        "title": entry["title"],
        "summary": entry["summary"],
        "turn": current_turn,
        "active": True,
    }


async def restore_archive_version(
    db: AsyncSession,
    project_id: str,
    session_id: str,
    version: int,
    *,
    mode: str = "fork",
) -> dict[str, Any]:
    """Restore session and world state to a saved archive version.

    Modes:
    - ``hard``: overwrite the current session in place.
    - ``fork``: restore into a new session branch (default).
    """
    if mode not in {"hard", "fork"}:
        raise ValueError(f"Invalid restore mode: {mode}")

    meta = await ensure_archive_initialized(db, project_id, session_id)
    versions = (
        await storage_get(
            db, project_id, ARCHIVE_PLUGIN_NAME, _versions_key(session_id)
        )
        or []
    )

    target = _find_version(versions, version)
    if target is None:
        raise ValueError(f"Archive version {version} not found")

    snapshot = target.get("state_snapshot") or {}
    if mode == "hard":
        await _apply_state_snapshot(
            db,
            project_id,
            session_id,
            snapshot,
            reuse_ids=True,
            restore_note=f"已恢复到存档版本 v{version}（覆盖当前会话）",
        )

        # Keep the full version history, only move active pointer.
        meta["active_version"] = version
        meta["last_snapshot_turn"] = int(target.get("turn", 0) or 0)
        meta["last_snapshot_at"] = _to_iso(_utcnow())
        await storage_set(
            db,
            project_id,
            ARCHIVE_PLUGIN_NAME,
            _meta_key(session_id),
            meta,
        )

        return {
            "ok": True,
            "mode": "hard",
            "session_id": session_id,
            "version": version,
            "title": target.get("title", ""),
            "summary": target.get("summary", ""),
            "phase": snapshot.get("session", {}).get("phase", "playing"),
        }

    # Fork mode: create a new session and restore snapshot there.
    fork_session = GameSession(project_id=project_id)
    db.add(fork_session)
    await db.commit()
    await db.refresh(fork_session)

    await _apply_state_snapshot(
        db,
        project_id,
        fork_session.id,
        snapshot,
        reuse_ids=False,
        restore_note=(
            f"已从会话 {session_id} 分叉恢复到存档版本 v{version}"
        ),
    )

    now_iso = _to_iso(_utcnow())
    copied_versions = json.loads(json.dumps(versions, ensure_ascii=False))
    fork_meta = {
        "current_version": int(meta.get("current_version", 0) or 0),
        "active_version": version,
        "last_snapshot_turn": int(target.get("turn", 0) or 0),
        "last_snapshot_at": now_iso,
        "summary_interval_turns": int(
            meta.get("summary_interval_turns", DEFAULT_SUMMARY_INTERVAL_TURNS)
            or DEFAULT_SUMMARY_INTERVAL_TURNS
        ),
        "initial_state": meta.get("initial_state") or snapshot,
    }
    await storage_set(
        db,
        project_id,
        ARCHIVE_PLUGIN_NAME,
        _versions_key(fork_session.id),
        copied_versions,
    )
    await storage_set(
        db,
        project_id,
        ARCHIVE_PLUGIN_NAME,
        _meta_key(fork_session.id),
        fork_meta,
    )

    return {
        "ok": True,
        "mode": "fork",
        "session_id": fork_session.id,
        "new_session_id": fork_session.id,
        "source_session_id": session_id,
        "version": version,
        "title": target.get("title", ""),
        "summary": target.get("summary", ""),
        "phase": snapshot.get("session", {}).get("phase", "playing"),
    }


def _find_version(
    versions: list[dict[str, Any]], version: int
) -> dict[str, Any] | None:
    for item in versions:
        if int(item.get("version", 0) or 0) == int(version):
            return item
    return None


async def _collect_actions_since(
    db: AsyncSession,
    session_id: str,
    since: datetime | None,
    limit: int,
) -> list[dict[str, str]]:
    stmt = select(Message).where(Message.session_id == session_id)
    if since is not None:
        stmt = stmt.where(Message.created_at > since)
    stmt = stmt.order_by(Message.created_at.asc())  # type: ignore[arg-type]
    result = await db.exec(stmt)
    rows = list(result.all())

    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]

    actions: list[dict[str, str]] = []
    for msg in rows:
        if msg.role not in {"user", "assistant", "system"}:
            continue
        content = (msg.content or "").strip()
        if not content:
            continue
        if len(content) > 500:
            content = content[:500] + "..."
        actions.append({"role": msg.role, "content": content})
    return actions


async def _collect_state_snapshot(
    db: AsyncSession,
    project_id: str,
    session_id: str,
) -> dict[str, Any]:
    game_session = await db.get(GameSession, session_id)

    char_stmt = (
        select(Character)
        .where(Character.session_id == session_id)
        .order_by(Character.created_at.asc())  # type: ignore[arg-type]
    )
    characters = list((await db.exec(char_stmt)).all())

    scene_stmt = (
        select(Scene)
        .where(Scene.session_id == session_id)
        .order_by(Scene.created_at.asc())  # type: ignore[arg-type]
    )
    scenes = list((await db.exec(scene_stmt)).all())

    scene_ids = [s.id for s in scenes]
    scene_npcs: list[SceneNPC] = []
    if scene_ids:
        npc_stmt = select(SceneNPC).where(SceneNPC.scene_id.in_(scene_ids))
        scene_npcs = list((await db.exec(npc_stmt)).all())

    event_stmt = (
        select(GameEvent)
        .where(GameEvent.session_id == session_id)
        .order_by(GameEvent.created_at.asc())  # type: ignore[arg-type]
    )
    events = list((await db.exec(event_stmt)).all())

    return {
        "session": {
            "status": game_session.status if game_session else "active",
            "phase": game_session.phase if game_session else "init",
            "game_state": _loads_json(
                game_session.game_state_json if game_session else "{}", {}
            ),
        },
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "role": c.role,
                "description": c.description,
                "personality": c.personality,
                "attributes": _loads_json(c.attributes_json, {}),
                "inventory": _loads_json(c.inventory_json, []),
                "created_at": _to_iso(c.created_at),
                "updated_at": _to_iso(c.updated_at),
            }
            for c in characters
        ],
        "scenes": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "is_current": s.is_current,
                "metadata": _loads_json(s.metadata_json, {}),
                "created_at": _to_iso(s.created_at),
                "updated_at": _to_iso(s.updated_at),
            }
            for s in scenes
        ],
        "scene_npcs": [
            {
                "id": n.id,
                "scene_id": n.scene_id,
                "character_id": n.character_id,
                "role_in_scene": n.role_in_scene,
                "created_at": _to_iso(n.created_at),
            }
            for n in scene_npcs
        ],
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "name": e.name,
                "description": e.description,
                "status": e.status,
                "parent_event_id": e.parent_event_id,
                "source": e.source,
                "visibility": e.visibility,
                "metadata": _loads_json(e.metadata_json, {}),
                "created_at": _to_iso(e.created_at),
                "updated_at": _to_iso(e.updated_at),
            }
            for e in events
        ],
    }


async def _apply_state_snapshot(
    db: AsyncSession,
    project_id: str,
    session_id: str,
    snapshot: dict[str, Any],
    *,
    reuse_ids: bool = True,
    restore_note: str | None = None,
) -> None:
    game_session = await db.get(GameSession, session_id)
    if game_session is None:
        raise ValueError("Session not found")

    # Clear old runtime state first.
    old_scene_ids_stmt = select(Scene.id).where(Scene.session_id == session_id)
    old_scene_ids = list((await db.exec(old_scene_ids_stmt)).all())
    if old_scene_ids:
        await db.exec(delete(SceneNPC).where(SceneNPC.scene_id.in_(old_scene_ids)))

    await db.exec(delete(Scene).where(Scene.session_id == session_id))
    await db.exec(delete(GameEvent).where(GameEvent.session_id == session_id))
    await db.exec(delete(Message).where(Message.session_id == session_id))
    await db.exec(delete(Character).where(Character.session_id == session_id))

    session_data = snapshot.get("session", {})
    game_session.status = session_data.get("status", "active")
    game_session.phase = session_data.get("phase", "playing")
    game_state = session_data.get("game_state", {})
    if isinstance(game_state, str):
        game_session.game_state_json = game_state
    else:
        game_session.game_state_json = json.dumps(game_state, ensure_ascii=False)
    game_session.updated_at = _utcnow()
    db.add(game_session)

    char_id_map: dict[str, str] = {}
    for item in snapshot.get("characters", []):
        source_id = str(item.get("id", "") or "")
        target_id = source_id if (reuse_ids and source_id) else str(uuid.uuid4())
        if source_id:
            char_id_map[source_id] = target_id
        db.add(
            Character(
                id=target_id,
                session_id=session_id,
                name=item.get("name", "Unknown"),
                role=item.get("role", "npc"),
                description=item.get("description"),
                personality=item.get("personality"),
                attributes_json=json.dumps(
                    item.get("attributes", {}), ensure_ascii=False
                ),
                inventory_json=json.dumps(
                    item.get("inventory", []), ensure_ascii=False
                ),
                created_at=_parse_iso(item.get("created_at")),
                updated_at=_parse_iso(item.get("updated_at")),
            )
        )

    scene_id_map: dict[str, str] = {}
    for item in snapshot.get("scenes", []):
        source_id = str(item.get("id", "") or "")
        target_id = source_id if (reuse_ids and source_id) else str(uuid.uuid4())
        if source_id:
            scene_id_map[source_id] = target_id
        db.add(
            Scene(
                id=target_id,
                session_id=session_id,
                name=item.get("name", "Unknown Scene"),
                description=item.get("description"),
                is_current=bool(item.get("is_current", False)),
                metadata_json=json.dumps(item.get("metadata", {}), ensure_ascii=False),
                created_at=_parse_iso(item.get("created_at")),
                updated_at=_parse_iso(item.get("updated_at")),
            )
        )

    event_id_map: dict[str, str] = {}
    for item in snapshot.get("events", []):
        source_id = str(item.get("id", "") or "")
        target_id = source_id if (reuse_ids and source_id) else str(uuid.uuid4())
        if source_id:
            event_id_map[source_id] = target_id
        raw_parent = str(item.get("parent_event_id", "") or "")
        if raw_parent and raw_parent in event_id_map:
            parent_id = event_id_map[raw_parent]
        else:
            parent_id = raw_parent if (reuse_ids and raw_parent) else None
        db.add(
            GameEvent(
                id=target_id,
                session_id=session_id,
                event_type=item.get("event_type", "world"),
                name=item.get("name", "Unknown Event"),
                description=item.get("description", ""),
                status=item.get("status", "active"),
                parent_event_id=parent_id,
                source=item.get("source", "dm"),
                visibility=item.get("visibility", "known"),
                metadata_json=json.dumps(item.get("metadata", {}), ensure_ascii=False),
                created_at=_parse_iso(item.get("created_at")),
                updated_at=_parse_iso(item.get("updated_at")),
            )
        )

    for item in snapshot.get("scene_npcs", []):
        source_scene_id = str(item.get("scene_id", "") or "")
        source_char_id = str(item.get("character_id", "") or "")
        target_scene_id = scene_id_map.get(source_scene_id, source_scene_id)
        target_char_id = char_id_map.get(source_char_id, source_char_id)
        if not target_scene_id or not target_char_id:
            continue
        source_id = str(item.get("id", "") or "")
        target_id = source_id if (reuse_ids and source_id) else str(uuid.uuid4())
        db.add(
            SceneNPC(
                id=target_id,
                scene_id=target_scene_id,
                character_id=target_char_id,
                role_in_scene=item.get("role_in_scene"),
                created_at=_parse_iso(item.get("created_at")),
            )
        )

    # Keep a single compressed restore marker message.
    if not restore_note:
        restore_note = f"已恢复到存档版本，当前阶段: {game_session.phase}"
    db.add(
        Message(
            session_id=session_id,
            role="system",
            content=restore_note,
            message_type="system_event",
            created_at=_utcnow(),
        )
    )

    await db.commit()


async def _summarize_with_llm(
    project: Project,
    meta: dict[str, Any],
    current_turn: int,
    trigger: str,
    reason: str | None,
    actions: list[dict[str, str]],
    current_state: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "world_doc": project.world_doc,
        "initial_state": meta.get("initial_state", {}),
        "current_version": int(meta.get("current_version", 0) or 0),
        "active_version": int(meta.get("active_version", 0) or 0),
        "turn": current_turn,
        "trigger": trigger,
        "reason": reason,
        "actions": actions,
        "current_state": current_state,
    }

    messages = [
        {
            "role": "system",
            "content": (
                "你是RPG游戏的存档压缩器。"
                "你要把世界观、起始状态、当前状态和最近动作压缩成可继续游玩的摘要。"
                "必须返回严格 JSON，不要输出任何额外文本。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请总结并返回 JSON，字段为: "
                "title(string), summary(string), key_facts(string[]), pending_threads(string[]), next_focus(string[]).\n"
                "要求: summary 控制在 120-220 中文字，强调状态变化与未完成线索。\n"
                f"输入数据:\n{json.dumps(payload, ensure_ascii=False)}"
            ),
        },
    ]

    try:
        config = get_effective_config_for_project(project)
        raw = await completion(
            messages,
            model=config.model,
            stream=False,
            api_key=config.api_key,
            api_base=config.api_base,
        )
    except Exception:
        logger.exception("Archive summary LLM call failed")
        raw = ""

    parsed = _try_parse_summary_json(str(raw or ""))
    if parsed:
        return parsed

    fallback = str(raw or "").strip() or "本轮状态已更新，暂无可用结构化摘要。"
    if len(fallback) > 240:
        fallback = fallback[:240] + "..."
    return {
        "title": f"Turn {current_turn} Snapshot",
        "summary": fallback,
        "key_facts": [],
        "pending_threads": [],
        "next_focus": [],
    }


def _try_parse_summary_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\\s*", "", text)
        text = re.sub(r"\\s*```$", "", text)

    candidate = text
    if "{" in candidate and "}" in candidate:
        candidate = candidate[candidate.find("{") : candidate.rfind("}") + 1]

    try:
        data = json.loads(candidate)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    return {
        "title": str(data.get("title", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "key_facts": [str(x) for x in data.get("key_facts", []) if str(x).strip()],
        "pending_threads": [
            str(x) for x in data.get("pending_threads", []) if str(x).strip()
        ],
        "next_focus": [str(x) for x in data.get("next_focus", []) if str(x).strip()],
    }
