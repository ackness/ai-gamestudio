from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.secret_store import get_secret_store
from backend.app.db.engine import get_session
from backend.app.models.project import Project
from backend.app.services.data_cleanup import delete_project_data

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    id: str | None = None  # optional: caller may supply a specific UUID (e.g. re-sync after cold start)
    name: str
    description: str | None = None
    world_doc: str = ""
    init_prompt: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_api_base: str | None = None
    image_model: str | None = None
    image_api_key: str | None = None
    image_api_base: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    world_doc: str | None = None
    init_prompt: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_api_base: str | None = None
    image_model: str | None = None
    image_api_key: str | None = None
    image_api_base: str | None = None


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str | None = None
    world_doc: str = ""
    init_prompt: str | None = None
    llm_model: str | None = None
    llm_api_base: str | None = None
    has_llm_api_key: bool = False
    image_model: str | None = None
    image_api_base: str | None = None
    has_image_api_key: bool = False
    created_at: datetime
    updated_at: datetime


def _project_has_api_key(project: Project) -> bool:
    store = get_secret_store()
    if store.has_secret(project.llm_api_key_ref):
        return True
    return bool(project.llm_api_key and project.llm_api_key.strip())


def _project_has_image_api_key(project: Project) -> bool:
    store = get_secret_store()
    if store.has_secret(project.image_api_key_ref):
        return True
    return bool(project.image_api_key and project.image_api_key.strip())


def _set_project_api_key(project: Project, raw_key: str | None) -> None:
    store = get_secret_store()
    key = (raw_key or "").strip()
    if not key:
        store.delete_secret(project.llm_api_key_ref)
        project.llm_api_key_ref = None
        project.llm_api_key = None
        return
    project.llm_api_key_ref = store.set_secret(
        key,
        current_ref=project.llm_api_key_ref,
    )
    project.llm_api_key = None


def _set_project_image_api_key(project: Project, raw_key: str | None) -> None:
    store = get_secret_store()
    key = (raw_key or "").strip()
    if not key:
        store.delete_secret(project.image_api_key_ref)
        project.image_api_key_ref = None
        project.image_api_key = None
        return
    project.image_api_key_ref = store.set_secret(
        key,
        current_ref=project.image_api_key_ref,
    )
    project.image_api_key = None


def _serialize_project(project: Project) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        world_doc=project.world_doc,
        init_prompt=project.init_prompt,
        llm_model=project.llm_model,
        llm_api_base=project.llm_api_base,
        has_llm_api_key=_project_has_api_key(project),
        image_model=project.image_model,
        image_api_base=project.image_api_base,
        has_image_api_key=_project_has_image_api_key(project),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post("", response_model=ProjectRead)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
):
    payload = body.model_dump()
    raw_api_key = payload.pop("llm_api_key", None)
    raw_image_api_key = payload.pop("image_api_key", None)
    specified_id = payload.pop("id", None)

    # If a specific ID was supplied (e.g. frontend re-syncing after cold start), upsert it.
    if specified_id:
        existing = await session.get(Project, specified_id)
        if existing:
            return _serialize_project(existing)
        project = Project(id=specified_id, **payload)
    else:
        project = Project(**payload)

    if raw_api_key is not None:
        _set_project_api_key(project, raw_api_key)
    if raw_image_api_key is not None:
        _set_project_image_api_key(project, raw_image_api_key)

    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _serialize_project(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Project).order_by(Project.created_at.desc()))  # type: ignore[arg-type]
    return [_serialize_project(project) for project in result.all()]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _serialize_project(project)


@router.put("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = body.model_dump(exclude_unset=True)
    if "llm_api_key" in update_data:
        _set_project_api_key(project, update_data.pop("llm_api_key"))
    if "image_api_key" in update_data:
        _set_project_image_api_key(project, update_data.pop("image_api_key"))
    _MUTABLE_FIELDS = {
        "name", "description", "world_doc", "init_prompt",
        "llm_model", "llm_api_base", "image_model", "image_api_base",
    }
    for key, value in update_data.items():
        if key in _MUTABLE_FIELDS:
            setattr(project, key, value)
    project.updated_at = datetime.now(timezone.utc)

    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _serialize_project(project)


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    get_secret_store().delete_secret(project.llm_api_key_ref)
    get_secret_store().delete_secret(project.image_api_key_ref)
    await delete_project_data(session, project_id=project_id, autocommit=False)
    await session.delete(project)
    await session.commit()
    return {"ok": True}
