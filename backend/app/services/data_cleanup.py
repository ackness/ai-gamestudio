from __future__ import annotations

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.character import Character
from backend.app.models.game_event import GameEvent
from backend.app.models.message import Message
from backend.app.models.plugin_storage import PluginStorage
from backend.app.models.scene import Scene
from backend.app.models.scene_npc import SceneNPC
from backend.app.models.session import GameSession


async def delete_session_data(
    session: AsyncSession,
    *,
    session_id: str,
    project_id: str | None = None,
    autocommit: bool = False,
) -> None:
    """Delete one game session and all known dependent records."""
    scene_ids = list(
        (
            await session.exec(
                select(Scene.id).where(Scene.session_id == session_id)
            )
        ).all()
    )
    if scene_ids:
        await session.exec(delete(SceneNPC).where(SceneNPC.scene_id.in_(scene_ids)))

    await session.exec(delete(Scene).where(Scene.session_id == session_id))
    await session.exec(delete(GameEvent).where(GameEvent.session_id == session_id))
    await session.exec(delete(Message).where(Message.session_id == session_id))
    await session.exec(delete(Character).where(Character.session_id == session_id))

    if project_id:
        await session.exec(
            delete(PluginStorage).where(
                PluginStorage.project_id == project_id,
                PluginStorage.key.like(f"session:{session_id}%"),
            )
        )

    await session.exec(delete(GameSession).where(GameSession.id == session_id))

    if autocommit:
        await session.commit()
    else:
        await session.flush()


async def delete_project_data(
    session: AsyncSession,
    *,
    project_id: str,
    autocommit: bool = False,
) -> None:
    """Delete all sessions and plugin storage records under one project."""
    session_ids = list(
        (
            await session.exec(
                select(GameSession.id).where(GameSession.project_id == project_id)
            )
        ).all()
    )
    for session_id in session_ids:
        await delete_session_data(
            session,
            session_id=session_id,
            project_id=project_id,
            autocommit=False,
        )

    await session.exec(delete(PluginStorage).where(PluginStorage.project_id == project_id))
    await session.exec(delete(GameSession).where(GameSession.project_id == project_id))

    if autocommit:
        await session.commit()
    else:
        await session.flush()
