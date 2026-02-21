"""Tests for world templates API endpoints."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import backend.app.db.engine as engine_mod


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    """Create a test client with an in-memory database and temp templates dir."""
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


@pytest.fixture
def templates_dir(tmp_path: Path):
    """Create a temporary templates directory with test files."""
    d = tmp_path / "templates" / "worlds"
    d.mkdir(parents=True)

    (d / "test-world.md").write_text(
        '---\nname: "Test World"\ndescription: A test world\n'
        "genre: fantasy\ntags: [magic, adventure]\nlanguage: en\n---\n\n"
        "# Test World\n\n## World Background\n\nA test world for testing.\n",
        encoding="utf-8",
    )

    (d / "another.md").write_text(
        '---\nname: "Another World"\ndescription: Another test\n'
        "genre: sci-fi\ntags: [space]\nlanguage: en\n---\n\n"
        "# Another World\n\nSci-fi setting.\n",
        encoding="utf-8",
    )

    return d


@pytest.mark.asyncio
async def test_list_world_templates(client: AsyncClient, templates_dir: Path):
    with patch("backend.app.api.templates.settings") as mock_settings:
        mock_settings.TEMPLATES_DIR = str(templates_dir)
        resp = await client.get("/api/templates/worlds")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    slugs = {t["slug"] for t in data}
    assert "test-world" in slugs
    assert "another" in slugs

    # Verify metadata of one template
    test_world = next(t for t in data if t["slug"] == "test-world")
    assert test_world["name"] == "Test World"
    assert test_world["genre"] == "fantasy"
    assert "magic" in test_world["tags"]


@pytest.mark.asyncio
async def test_get_world_template(client: AsyncClient, templates_dir: Path):
    with patch("backend.app.api.templates.settings") as mock_settings:
        mock_settings.TEMPLATES_DIR = str(templates_dir)
        resp = await client.get("/api/templates/worlds/test-world")

    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "test-world"
    assert data["name"] == "Test World"
    assert "# Test World" in data["content"]
    assert "---" in data["raw"]  # raw includes frontmatter


@pytest.mark.asyncio
async def test_get_world_template_not_found(client: AsyncClient, templates_dir: Path):
    with patch("backend.app.api.templates.settings") as mock_settings:
        mock_settings.TEMPLATES_DIR = str(templates_dir)
        resp = await client.get("/api/templates/worlds/nonexistent")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_world(client: AsyncClient):
    mock_result = "# Generated World\n\n## World Background\n\nAI generated content."

    async def mock_stream():
        yield mock_result

    with patch("backend.app.api.templates.completion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = mock_stream()
        resp = await client.post(
            "/api/templates/worlds/generate",
            json={"genre": "fantasy", "setting": "medieval", "language": "en"},
        )

    assert resp.status_code == 200
    assert mock_result in resp.text
    mock_completion.assert_called_once()

    # Verify the messages structure passed to completion
    call_args = mock_completion.call_args
    messages = call_args[0][0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "fantasy" in messages[1]["content"]
