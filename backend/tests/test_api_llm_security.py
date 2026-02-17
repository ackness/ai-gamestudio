"""Tests for LLM/project API security behavior (no plaintext key leakage)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import backend.app.db.engine as engine_mod
from backend.app.models.llm_profile import LlmProfile
from backend.app.models.project import Project


@pytest_asyncio.fixture
async def client():
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    original_engine = engine_mod.engine
    engine_mod.engine = test_engine

    async def override_get_session():
        async with AsyncSession(test_engine) as session:
            yield session

    from backend.app.main import app
    from backend.app.db.engine import get_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    engine_mod.engine = original_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_project_api_does_not_return_plaintext_llm_key(client: AsyncClient):
    create_resp = await client.post(
        "/api/projects",
        json={
            "name": "Secure Project",
            "llm_model": "deepseek/deepseek-chat",
            "llm_api_key": "sk-secret-project-key",
            "llm_api_base": "https://api.deepseek.com",
            "image_model": "gemini-2.5-flash-image-preview",
            "image_api_key": "sk-secret-image-key",
            "image_api_base": "https://api.whatai.cc/v1/chat/completions",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["has_llm_api_key"] is True
    assert created["has_image_api_key"] is True
    assert "llm_api_key" not in created
    assert "image_api_key" not in created

    project_id = created["id"]
    get_resp = await client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 200
    loaded = get_resp.json()
    assert loaded["has_llm_api_key"] is True
    assert loaded["has_image_api_key"] is True
    assert "llm_api_key" not in loaded
    assert "image_api_key" not in loaded

    async with AsyncSession(engine_mod.engine) as session:
        project = await session.get(Project, project_id)
        assert project is not None
        assert project.llm_api_key in (None, "")
        assert project.image_api_key in (None, "")
        assert isinstance(project.llm_api_key_ref, str)
        assert isinstance(project.image_api_key_ref, str)
        assert project.llm_api_key_ref
        assert project.image_api_key_ref


@pytest.mark.asyncio
async def test_llm_profiles_api_hides_keys_and_can_apply_profile(client: AsyncClient):
    profile_resp = await client.post(
        "/api/llm/profiles",
        json={
            "name": "Secure Profile",
            "model": "deepseek/deepseek-chat",
            "api_key": "sk-secret-profile-key",
            "api_base": "https://api.deepseek.com",
        },
    )
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["has_api_key"] is True
    assert "api_key" not in profile
    profile_id = profile["id"]

    project_resp = await client.post("/api/projects", json={"name": "Target Project"})
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

    apply_resp = await client.post(
        f"/api/llm/profiles/{profile_id}/apply",
        json={"project_id": project_id},
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["ok"] is True

    project_get = await client.get(f"/api/projects/{project_id}")
    assert project_get.status_code == 200
    project_data = project_get.json()
    assert project_data["llm_model"] == "deepseek/deepseek-chat"
    assert project_data["llm_api_base"] == "https://api.deepseek.com"
    assert project_data["has_llm_api_key"] is True
    assert "llm_api_key" not in project_data

    async with AsyncSession(engine_mod.engine) as session:
        profile_row = await session.get(LlmProfile, profile_id)
        project_row = await session.get(Project, project_id)
        assert profile_row is not None
        assert project_row is not None
        assert profile_row.api_key in (None, "")
        assert project_row.llm_api_key in (None, "")
        assert isinstance(profile_row.api_key_ref, str)
        assert isinstance(project_row.llm_api_key_ref, str)
        assert profile_row.api_key_ref
        assert project_row.llm_api_key_ref
