from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.project import Project


async def create_project(
    session: AsyncSession,
    name: str,
    description: str | None = None,
    world_doc: str = "",
    llm_model: str | None = None,
) -> Project:
    project = Project(
        name=name,
        description=description,
        world_doc=world_doc,
        llm_model=llm_model,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    return await session.get(Project, project_id)


async def list_projects(session: AsyncSession) -> list[Project]:
    result = await session.exec(select(Project).order_by(Project.created_at.desc()))  # type: ignore[arg-type]
    return list(result.all())


async def update_project(
    session: AsyncSession,
    project_id: str,
    **updates: object,
) -> Project | None:
    project = await session.get(Project, project_id)
    if not project:
        return None
    for key, value in updates.items():
        if value is not None and hasattr(project, key):
            setattr(project, key, value)
    project.updated_at = datetime.now(timezone.utc)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project_id: str) -> bool:
    project = await session.get(Project, project_id)
    if not project:
        return False
    await session.delete(project)
    await session.commit()
    return True
