"""Tests for project CRUD API endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

# Override engine before app import
import backend.app.db.engine as engine_mod
from backend.app.models.character import Character
from backend.app.models.game_event import GameEvent
from backend.app.models.plugin_storage import PluginStorage
from backend.app.models.scene import Scene
from backend.app.models.scene_npc import SceneNPC
from backend.app.models.session import GameSession


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
    payload = resp.json()
    assert payload["status"] == "ok"
    assert isinstance(payload.get("storage_persistent"), bool)
    assert isinstance(payload.get("auth_required"), bool)


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
async def test_list_sessions_project_not_found(client: AsyncClient):
    resp = await client.get("/api/projects/non-existent-project/sessions")
    assert resp.status_code == 404


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


@pytest.mark.asyncio
async def test_delete_session_cascades_related_data(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "Cascade Project"})
    project_id = create_resp.json()["id"]
    session_resp = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = session_resp.json()["id"]

    async with AsyncSession(engine_mod.engine, expire_on_commit=False) as db:
        char = Character(session_id=session_id, name="NPC")
        scene = Scene(session_id=session_id, name="Town", is_current=True)
        db.add(char)
        db.add(scene)
        await db.commit()
        await db.refresh(char)
        await db.refresh(scene)

        db.add(
            SceneNPC(
                scene_id=scene.id,
                character_id=char.id,
                role_in_scene="shopkeeper",
            )
        )
        db.add(
            GameEvent(
                session_id=session_id,
                event_type="quest",
                name="Find Artifact",
                description="Locate the missing relic.",
            )
        )
        db.add(
            PluginStorage(
                project_id=project_id,
                plugin_name="runtime-settings",
                key=f"session:{session_id}",
                value_json='{"pacing":"slow"}',
            )
        )
        db.add(
            PluginStorage(
                project_id=project_id,
                plugin_name="story-image",
                key=f"session:{session_id}:images",
                value_json="[]",
            )
        )
        await db.commit()

    delete_resp = await client.delete(f"/api/sessions/{session_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"ok": True}

    async with AsyncSession(engine_mod.engine, expire_on_commit=False) as db:
        session_rows = list(
            (
                await db.exec(
                    select(GameSession).where(GameSession.id == session_id)
                )
            ).all()
        )
        character_rows = list(
            (
                await db.exec(
                    select(Character).where(Character.session_id == session_id)
                )
            ).all()
        )
        scene_rows = list(
            (
                await db.exec(
                    select(Scene).where(Scene.session_id == session_id)
                )
            ).all()
        )
        event_rows = list(
            (
                await db.exec(
                    select(GameEvent).where(GameEvent.session_id == session_id)
                )
            ).all()
        )
        session_storage_rows = list(
            (
                await db.exec(
                    select(PluginStorage).where(
                        PluginStorage.project_id == project_id,
                        PluginStorage.key.like(f"session:{session_id}%"),
                    )
                )
            ).all()
        )

    assert session_rows == []
    assert character_rows == []
    assert scene_rows == []
    assert event_rows == []
    assert session_storage_rows == []


@pytest.mark.asyncio
async def test_delete_project_cascades_sessions_and_storage(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "Cascade Project"})
    project_id = create_resp.json()["id"]
    session_resp = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = session_resp.json()["id"]

    async with AsyncSession(engine_mod.engine, expire_on_commit=False) as db:
        db.add(
            PluginStorage(
                project_id=project_id,
                plugin_name="runtime-settings",
                key="project",
                value_json='{"story-image.style_preset":"cinematic"}',
            )
        )
        db.add(
            Character(session_id=session_id, name="Orphan Candidate")
        )
        await db.commit()

    delete_resp = await client.delete(f"/api/projects/{project_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"ok": True}

    sessions_resp = await client.get(f"/api/projects/{project_id}/sessions")
    assert sessions_resp.status_code == 404

    async with AsyncSession(engine_mod.engine, expire_on_commit=False) as db:
        session_rows = list(
            (
                await db.exec(
                    select(GameSession).where(GameSession.project_id == project_id)
                )
            ).all()
        )
        storage_rows = list(
            (
                await db.exec(
                    select(PluginStorage).where(PluginStorage.project_id == project_id)
                )
            ).all()
        )

    assert session_rows == []
    assert storage_rows == []
