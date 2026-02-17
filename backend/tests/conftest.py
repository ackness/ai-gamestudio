from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Force test database URL before any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["PLUGINS_DIR"] = "plugins"
os.environ["SECRET_STORE_DIR"] = "/tmp/ai-gamestudio-test-secrets"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    import backend.app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        yield session


@pytest_asyncio.fixture
async def sample_project(db_session: AsyncSession):
    from backend.app.models.project import Project

    project = Project(
        name="Test Game",
        description="A test project",
        world_doc="# Test World\n\nA dark fantasy world.",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def sample_session(db_session: AsyncSession, sample_project):
    from backend.app.models.session import GameSession

    game_session = GameSession(project_id=sample_project.id)
    db_session.add(game_session)
    await db_session.commit()
    await db_session.refresh(game_session)
    return game_session
