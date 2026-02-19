from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocketDisconnect

import backend.app.db.engine as engine_mod
from backend.app.core.config import settings

_ACCESS_KEY = "test-access-key"


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "access_key_ws.sqlite"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    import backend.app.models  # noqa: F401

    async def _setup() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(_setup())

    original_engine = engine_mod.engine
    original_access_key = settings.ACCESS_KEY
    engine_mod.engine = test_engine
    settings.ACCESS_KEY = _ACCESS_KEY

    async def override_get_session():
        async with AsyncSession(test_engine) as session:
            yield session

    from backend.app.main import app
    from backend.app.db.engine import get_session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides.clear()
    settings.ACCESS_KEY = original_access_key
    engine_mod.engine = original_engine

    async def _teardown() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await test_engine.dispose()

    asyncio.run(_teardown())


def _auth_headers() -> dict[str, str]:
    return {"X-Access-Key": _ACCESS_KEY}


def _create_session(client: TestClient) -> str:
    create_project = client.post(
        "/api/projects",
        json={"name": "Auth Session Project"},
        headers=_auth_headers(),
    )
    assert create_project.status_code == 200
    project_id = create_project.json()["id"]

    create_session = client.post(
        f"/api/projects/{project_id}/sessions",
        json={},
        headers=_auth_headers(),
    )
    assert create_session.status_code == 200
    return str(create_session.json()["id"])


def test_http_requires_access_key(client: TestClient):
    denied = client.get("/api/projects")
    assert denied.status_code == 401

    allowed = client.get("/api/projects", headers=_auth_headers())
    assert allowed.status_code == 200


def test_chat_websocket_requires_access_key(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    session_id = _create_session(client)

    async def _mock_session_exists(_: str) -> bool:
        return True

    monkeypatch.setattr("backend.app.api.chat._session_exists", _mock_session_exists)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/chat/{session_id}") as ws:
            ws.receive_json()
    assert exc.value.code == 4401

    with client.websocket_connect(
        f"/ws/chat/{session_id}?access_key={_ACCESS_KEY}"
    ) as ws:
        ws.send_json({"type": "unknown_message_type"})
        event = ws.receive_json()
        assert event["type"] == "error"


def test_debug_log_websocket_requires_access_key(client: TestClient):
    session_id = _create_session(client)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/debug-log/{session_id}") as ws:
            ws.receive_json()
    assert exc.value.code == 4401

    with client.websocket_connect(
        f"/ws/debug-log/{session_id}?access_key={_ACCESS_KEY}"
    ) as ws:
        ws.close()
