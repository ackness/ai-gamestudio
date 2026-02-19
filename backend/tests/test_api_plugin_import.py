from __future__ import annotations

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
async def test_validate_plugin_import_accepts_json_body(client: AsyncClient):
    resp = await client.post(
        "/api/plugins/import/validate",
        json={"plugin_dir": "plugins/story-image"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["valid"] is True
    assert payload["errors"] == []


@pytest.mark.asyncio
async def test_validate_plugin_import_accepts_query_param(client: AsyncClient):
    resp = await client.post(
        "/api/plugins/import/validate?plugin_dir=plugins/story-image",
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["valid"] is True
    assert payload["errors"] == []
