"""Tests for session messages API block/output contract."""
from __future__ import annotations

import json

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
async def test_get_messages_returns_output_envelope_and_filters_infra_blocks(
    client: AsyncClient,
) -> None:
    create_project = await client.post("/api/projects", json={"name": "My Game"})
    project_id = create_project.json()["id"]
    create_session = await client.post(f"/api/projects/{project_id}/sessions")
    session_id = create_session.json()["id"]

    from backend.app.db.engine import engine
    from backend.app.models.message import Message

    async with AsyncSession(engine) as db:
        msg = Message(
            session_id=session_id,
            role="assistant",
            content="Narration",
            message_type="narration",
            metadata_json=json.dumps(
            {
                "blocks": [
                    {
                        "type": "state_update",
                        "data": {"world": {"weather": "rain"}},
                        "block_id": "out-state",
                        "output": {
                            "id": "out-state",
                            "version": "1.0",
                            "type": "state_update",
                            "data": {"world": {"weather": "rain"}},
                            "meta": {"plugin": "state"},
                            "status": "done",
                        },
                    },
                    {
                        "type": "notification",
                        "data": {"level": "info", "title": "提示", "content": "已同步"},
                        "block_id": "out-note",
                        "output": {
                            "id": "out-note",
                            "version": "1.0",
                            "type": "notification",
                            "data": {"level": "info", "title": "提示", "content": "已同步"},
                            "meta": {"plugin": "state"},
                            "status": "done",
                        },
                    },
                    {
                        "type": "choice",
                        "data": {"prompt": "去哪？", "options": ["港口", "酒馆"]},
                        "block_id": "out-choice",
                        "output": {
                            "id": "out-choice",
                            "version": "1.0",
                            "type": "choice",
                            "data": {"prompt": "去哪？", "options": ["港口", "酒馆"]},
                            "meta": {"plugin": "guide"},
                            "status": "done",
                        },
                    },
                ]
            },
            ensure_ascii=False,
            ),
        )
        db.add(msg)
        await db.commit()

    resp = await client.get(f"/api/sessions/{session_id}/messages")
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload, list) and payload

    assistant = next((m for m in payload if m.get("role") == "assistant"), None)
    assert assistant is not None
    blocks = assistant.get("blocks")
    assert isinstance(blocks, list)

    block_types = [b.get("type") for b in blocks if isinstance(b, dict)]
    assert "state_update" not in block_types
    assert {"notification", "choice"}.issubset(set(block_types))

    notification = next(b for b in blocks if b.get("type") == "notification")
    assert notification.get("block_id") == "out-note"
    assert notification.get("output", {}).get("id") == "out-note"
    assert notification.get("output", {}).get("type") == "notification"

    choice = next(b for b in blocks if b.get("type") == "choice")
    assert choice.get("block_id") == "out-choice"
    assert choice.get("output", {}).get("id") == "out-choice"
    assert choice.get("output", {}).get("type") == "choice"
