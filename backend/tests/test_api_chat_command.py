"""Tests for HTTP chat command fallback endpoint."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Override engine before app import
import backend.app.db.engine as engine_mod
import backend.app.api.chat as chat_api_mod


_TERMINAL_EVENT_TYPES = {"done", "error", "turn_end"}


def _assert_terminal_contract(events: list[dict]) -> None:
    assert events, "command response must include events"
    assert any(
        isinstance(evt, dict) and evt.get("type") in _TERMINAL_EVENT_TYPES
        for evt in events
    ), "command response must include at least one terminal event"


@pytest_asyncio.fixture
async def client():
    """Create a test client with an in-memory database."""
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    original_engine = engine_mod.engine
    original_chat_engine = chat_api_mod.engine
    engine_mod.engine = test_engine
    chat_api_mod.engine = test_engine

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
    chat_api_mod.engine = original_chat_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_chat_command_session_not_found(client: AsyncClient):
    resp = await client.post("/api/chat/nonexistent/command", json={"type": "message", "content": "hi"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"][0]["type"] == "error"
    assert data["events"][0]["content"] == "Session not found"
    assert data["terminal"]["status"] == "error"


@pytest.mark.asyncio
async def test_chat_command_unknown_type(client: AsyncClient):
    create_project = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_project.json()["id"]
    create_session = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = create_session.json()["id"]

    resp = await client.post(
        f"/api/chat/{session_id}/command",
        json={"type": "unknown_action"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"][0]["type"] == "error"
    assert "Unknown message type" in data["events"][0]["content"]
    assert data["terminal"]["status"] == "error"


@pytest.mark.asyncio
async def test_chat_command_empty_message(client: AsyncClient):
    create_project = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_project.json()["id"]
    create_session = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = create_session.json()["id"]

    resp = await client.post(
        f"/api/chat/{session_id}/command",
        json={"type": "message", "content": "   "},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"][0]["type"] == "error"
    assert data["events"][0]["content"] == "Empty message"
    assert data["terminal"]["status"] == "error"


@pytest.mark.asyncio
async def test_chat_command_forwards_llm_overrides(client: AsyncClient, monkeypatch):
    create_project = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_project.json()["id"]
    create_session = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = create_session.json()["id"]

    captured: dict[str, object] = {}

    async def fake_process_message(
        sid: str,
        user_content: str,
        *,
        save_user_msg: bool = True,
        save_assistant_msg: bool = True,
        llm_overrides: dict[str, str] | None = None,
        image_overrides: dict[str, str] | None = None,
    ):
        captured["sid"] = sid
        captured["content"] = user_content
        captured["save_user_msg"] = save_user_msg
        captured["save_assistant_msg"] = save_assistant_msg
        captured["llm_overrides"] = llm_overrides
        captured["image_overrides"] = image_overrides
        yield {"type": "chunk", "content": "ok", "turn_id": "turn-1"}

    monkeypatch.setattr(chat_api_mod, "process_message", fake_process_message)

    resp = await client.post(
        f"/api/chat/{session_id}/command",
        json={
            "type": "message",
            "content": "hello",
            "llm_overrides": {
                "model": "openrouter/deepseek/deepseek-chat",
                "api_key": "k-123",
                "api_base": "https://openrouter.ai/api/v1",
            },
            "image_overrides": {
                "model": "gemini-2.5-flash-image-preview",
                "api_key": "img-123",
                "api_base": "https://api.whatai.cc/v1/chat/completions",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    events = body["events"]
    _assert_terminal_contract(events)
    assert any(evt.get("type") == "done" for evt in events)
    assert body["terminal"]["status"] == "done"
    assert captured["sid"] == session_id
    assert captured["content"] == "hello"
    assert captured["llm_overrides"] == {
        "model": "openrouter/deepseek/deepseek-chat",
        "api_key": "k-123",
        "api_base": "https://openrouter.ai/api/v1",
    }
    assert captured["image_overrides"] == {
        "model": "gemini-2.5-flash-image-preview",
        "api_key": "img-123",
        "api_base": "https://api.whatai.cc/v1/chat/completions",
    }


@pytest.mark.asyncio
async def test_chat_command_message_contract_keeps_done_and_turn_end(
    client: AsyncClient, monkeypatch
):
    create_project = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_project.json()["id"]
    create_session = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = create_session.json()["id"]

    async def fake_process_message(
        sid: str,
        user_content: str,
        *,
        save_user_msg: bool = True,
        save_assistant_msg: bool = True,
        llm_overrides: dict[str, str] | None = None,
        image_overrides: dict[str, str] | None = None,
    ):
        assert sid == session_id
        assert user_content == "go"
        yield {"type": "chunk", "content": "ok", "turn_id": "turn-1"}
        yield {"type": "done", "content": "ok", "turn_id": "turn-1"}
        yield {"type": "turn_end", "turn_id": "turn-1"}

    monkeypatch.setattr(chat_api_mod, "process_message", fake_process_message)

    resp = await client.post(
        f"/api/chat/{session_id}/command",
        json={"type": "message", "content": "go"},
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    _assert_terminal_contract(events)
    event_types = [evt.get("type") for evt in events if isinstance(evt, dict)]
    assert "done" in event_types
    assert "turn_end" in event_types
    assert event_types[-1] == "turn_end"


@pytest.mark.asyncio
async def test_chat_command_message_contract_error_is_terminal(
    client: AsyncClient, monkeypatch
):
    create_project = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_project.json()["id"]
    create_session = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = create_session.json()["id"]

    async def fake_process_message(
        sid: str,
        user_content: str,
        *,
        save_user_msg: bool = True,
        save_assistant_msg: bool = True,
        llm_overrides: dict[str, str] | None = None,
        image_overrides: dict[str, str] | None = None,
    ):
        assert sid == session_id
        assert user_content == "go"
        yield {"type": "error", "content": "boom", "turn_id": "turn-1"}

    monkeypatch.setattr(chat_api_mod, "process_message", fake_process_message)

    resp = await client.post(
        f"/api/chat/{session_id}/command",
        json={"type": "message", "content": "go"},
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    _assert_terminal_contract(events)
    event_types = [evt.get("type") for evt in events if isinstance(evt, dict)]
    assert event_types == ["error"]
