"""Tests for project CRUD API endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Override engine before app import
import backend.app.db.engine as engine_mod


@pytest_asyncio.fixture
async def client():
    """Create a test client with an in-memory database."""
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Patch the engine and session factory
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
async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient):
    resp = await client.post(
        "/api/projects",
        json={"name": "My Game", "description": "A test game"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "My Game"
    assert data["description"] == "A test game"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient):
    # Create two projects
    await client.post("/api/projects", json={"name": "Game 1"})
    await client.post("/api/projects", json={"name": "Game 2"})

    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_resp.json()["id"]

    resp = await client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "My Game"


@pytest.mark.asyncio
async def test_get_project_not_found(client: AsyncClient):
    resp = await client.get("/api/projects/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/projects/{project_id}",
        json={"name": "Updated Game", "world_doc": "# New World"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Game"
    assert data["world_doc"] == "# New World"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify deleted
    resp = await client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_session_for_project(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_resp.json()["id"]

    resp = await client.post(f"/api/projects/{project_id}/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_sessions(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_resp.json()["id"]

    await client.post(f"/api/projects/{project_id}/sessions")
    await client.post(f"/api/projects/{project_id}/sessions")

    resp = await client.get(f"/api/projects/{project_id}/sessions")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_session_state(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_resp.json()["id"]

    session_resp = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = session_resp.json()["id"]

    resp = await client.get(f"/api/sessions/{session_id}/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["world"] == {}
    assert data["turn_count"] == 0
