from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.secret_store import get_secret_store
from backend.app.db.engine import get_session
from backend.app.models.llm_profile import LlmProfile
from backend.app.models.project import Project

router = APIRouter(prefix="/api/llm/profiles", tags=["llm-profiles"])


class LlmProfileCreate(BaseModel):
    name: str
    model: str
    api_key: str | None = None
    api_base: str | None = None


class LlmProfileUpdate(BaseModel):
    name: str | None = None
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None


class LlmProfileRead(BaseModel):
    id: str
    name: str
    model: str
    api_base: str | None = None
    has_api_key: bool = False
    created_at: datetime
    updated_at: datetime


class ApplyProfileBody(BaseModel):
    project_id: str


def _profile_has_api_key(profile: LlmProfile) -> bool:
    store = get_secret_store()
    if store.has_secret(profile.api_key_ref):
        return True
    return bool(profile.api_key and profile.api_key.strip())


def _set_profile_api_key(profile: LlmProfile, raw_key: str | None) -> None:
    store = get_secret_store()
    key = (raw_key or "").strip()
    if not key:
        store.delete_secret(profile.api_key_ref)
        profile.api_key_ref = None
        profile.api_key = None
        return
    profile.api_key_ref = store.set_secret(
        key,
        current_ref=profile.api_key_ref,
    )
    profile.api_key = None


def _resolve_profile_api_key(profile: LlmProfile) -> str | None:
    store = get_secret_store()
    from_ref = store.get_secret(profile.api_key_ref)
    if from_ref and from_ref.strip():
        return from_ref
    return profile.api_key


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


def _serialize_profile(profile: LlmProfile) -> LlmProfileRead:
    return LlmProfileRead(
        id=profile.id,
        name=profile.name,
        model=profile.model,
        api_base=profile.api_base,
        has_api_key=_profile_has_api_key(profile),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("", response_model=list[LlmProfileRead])
async def list_profiles(session: AsyncSession = Depends(get_session)):
    result = await session.exec(
        select(LlmProfile).order_by(LlmProfile.created_at.desc())  # type: ignore[arg-type]
    )
    return [_serialize_profile(profile) for profile in result.all()]


@router.post("", response_model=LlmProfileRead)
async def create_profile(
    body: LlmProfileCreate,
    session: AsyncSession = Depends(get_session),
):
    payload = body.model_dump()
    raw_api_key = payload.pop("api_key", None)
    profile = LlmProfile(**payload)
    if raw_api_key is not None:
        _set_profile_api_key(profile, raw_api_key)

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _serialize_profile(profile)


@router.put("/{profile_id}", response_model=LlmProfileRead)
async def update_profile(
    profile_id: str,
    body: LlmProfileUpdate,
    session: AsyncSession = Depends(get_session),
):
    profile = await session.get(LlmProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = body.model_dump(exclude_unset=True)
    if "api_key" in update_data:
        _set_profile_api_key(profile, update_data.pop("api_key"))
    _MUTABLE_FIELDS = {"name", "model", "api_base"}
    for key, value in update_data.items():
        if key in _MUTABLE_FIELDS:
            setattr(profile, key, value)
    profile.updated_at = datetime.now(timezone.utc)

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _serialize_profile(profile)


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    session: AsyncSession = Depends(get_session),
):
    profile = await session.get(LlmProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    get_secret_store().delete_secret(profile.api_key_ref)
    await session.delete(profile)
    await session.commit()
    return {"ok": True}


@router.post("/{profile_id}/apply")
async def apply_profile_to_project(
    profile_id: str,
    body: ApplyProfileBody,
    session: AsyncSession = Depends(get_session),
):
    profile = await session.get(LlmProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    project = await session.get(Project, body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.llm_model = profile.model
    _set_project_api_key(project, _resolve_profile_api_key(profile))
    project.llm_api_base = profile.api_base
    project.updated_at = datetime.now(timezone.utc)
    # Normalize profile key into secret store as well if it still uses legacy plaintext.
    if profile.api_key and not profile.api_key_ref:
        _set_profile_api_key(profile, profile.api_key)
        profile.updated_at = datetime.now(timezone.utc)
        session.add(profile)
    session.add(project)
    await session.commit()
    return {"ok": True}
