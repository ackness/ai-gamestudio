"""Tests for runtime settings API endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import backend.app.db.engine as engine_mod
from backend.tests.constants import RUNTIME_STATE_KEYS


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
async def test_runtime_settings_schema_and_patch(client: AsyncClient):
    project_resp = await client.post("/api/projects", json={"name": "Settings Project"})
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

    schema_resp = await client.get(
        f"/api/runtime-settings/schema?project_id={project_id}"
    )
    assert schema_resp.status_code == 200
    schema_data = schema_resp.json()
    keys = {field["key"] for field in schema_data["fields"]}
    assert RUNTIME_STATE_KEYS["narrative_tone"] in keys

    patch_resp = await client.patch(
        "/api/runtime-settings",
        json={
            "project_id": project_id,
            "scope": "project",
            "values": {RUNTIME_STATE_KEYS["narrative_tone"]: "grim"},
        },
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["ok"] is True
    assert patched["values"][RUNTIME_STATE_KEYS["narrative_tone"]] == "grim"

    get_resp = await client.get(f"/api/runtime-settings?project_id={project_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["values"][RUNTIME_STATE_KEYS["narrative_tone"]] == "grim"


@pytest.mark.asyncio
async def test_runtime_settings_patch_unknown_key_returns_400(client: AsyncClient):
    project_resp = await client.post("/api/projects", json={"name": "Settings Project"})
    project_id = project_resp.json()["id"]

    patch_resp = await client.patch(
        "/api/runtime-settings",
        json={
            "project_id": project_id,
            "scope": "project",
            "values": {"unknown.key": "x"},
        },
    )
    assert patch_resp.status_code == 400
