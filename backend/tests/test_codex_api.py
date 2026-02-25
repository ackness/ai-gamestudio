"""Test codex API endpoint."""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import backend.app.db.engine as engine_mod


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
async def test_get_codex_entries(client: AsyncClient):
    # Create a project
    resp = await client.post("/api/projects", json={"name": "Codex Test"})
    assert resp.status_code == 200
    project_id = resp.json()["id"]

    # Seed codex entries via plugin storage
    from backend.app.models.plugin_storage import PluginStorage

    entries = [
        {"action": "unlock", "category": "location", "entry_id": "cave", "title": "Cave", "content": "A dark cave", "tags": ["danger"]},
        {"action": "unlock", "category": "monster", "entry_id": "wolf", "title": "Wolf", "content": "A grey wolf", "tags": ["enemy"]},
        {"action": "unlock", "category": "location", "entry_id": "town", "title": "Town", "content": "A safe town", "tags": ["safe"]},
    ]

    # Insert directly via a fresh session from the test engine
    async with AsyncSession(engine_mod.engine) as session:
        storage = PluginStorage(
            id=str(uuid.uuid4()),
            project_id=project_id,
            plugin_name="codex",
            key="codex-entries",
            value_json=json.dumps(entries),
        )
        session.add(storage)
        await session.commit()

    resp = await client.get(f"/api/plugins/codex/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["entries"]) == 3
    assert len(data["by_category"]["location"]) == 2
    assert len(data["by_category"]["monster"]) == 1


@pytest.mark.asyncio
async def test_get_codex_empty_project(client: AsyncClient):
    resp = await client.get("/api/plugins/codex/nonexistent-project")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["entries"] == []
    assert data["by_category"] == {}
