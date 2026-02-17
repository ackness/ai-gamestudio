"""Tests for DeclarativeBlockHandler."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.block_handlers import BlockContext, DeclarativeBlockHandler, dispatch_block
from backend.app.core.event_bus import PluginEventBus
from backend.app.core.game_state import GameStateManager
from backend.app.core.plugin_engine import BlockDeclaration


@pytest_asyncio.fixture
async def block_context():
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    from backend.app.models.project import Project
    from backend.app.models.session import GameSession

    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        project = Project(name="Test", world_doc="# Test")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        game_session = GameSession(project_id=project.id)
        session.add(game_session)
        await session.commit()
        await session.refresh(game_session)

        state_mgr = GameStateManager(session)
        event_bus = PluginEventBus()
        ctx = BlockContext(
            session_id=game_session.id,
            project_id=project.id,
            db=session,
            state_mgr=state_mgr,
            event_bus=event_bus,
        )
        yield ctx

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_storage_write_action(block_context):
    handler = DeclarativeBlockHandler(
        actions=[{"type": "storage_write", "key": "test-key"}],
        plugin_name="test-plugin",
    )
    data = {"foo": "bar"}
    result = await handler.process(data, block_context)
    assert result == data

    from backend.app.services.plugin_service import storage_get

    stored = await storage_get(
        block_context.db,
        block_context.project_id,
        "test-plugin",
        "test-key",
    )
    assert stored == {"foo": "bar"}


@pytest.mark.asyncio
async def test_emit_event_action(block_context):
    handler = DeclarativeBlockHandler(
        actions=[{"type": "emit_event", "event": "test-event"}],
        plugin_name="test-plugin",
    )
    data = {"value": 42}
    await handler.process(data, block_context)

    # Event should be queued in the bus
    assert len(block_context.event_bus._queue) == 1
    assert block_context.event_bus._queue[0] == ("test-event", {"value": 42})


@pytest.mark.asyncio
async def test_dispatch_block_uses_declaration(block_context):
    block = {"type": "custom_test", "data": {"x": 1}}
    declarations = {
        "custom_test": BlockDeclaration(
            block_type="custom_test",
            plugin_name="test-plugin",
            handler={"actions": [{"type": "storage_write", "key": "dispatched"}]},
        ),
    }
    result = await dispatch_block(block, block_context, declarations)
    assert result["type"] == "custom_test"

    from backend.app.services.plugin_service import storage_get

    stored = await storage_get(
        block_context.db,
        block_context.project_id,
        "test-plugin",
        "dispatched",
    )
    assert stored == {"x": 1}


@pytest.mark.asyncio
async def test_dispatch_block_builtin_takes_priority(block_context):
    """Built-in handlers should take priority over plugin declarations."""
    block = {"type": "state_update", "data": {"characters": []}}
    declarations = {
        "state_update": BlockDeclaration(
            block_type="state_update",
            plugin_name="override-plugin",
            handler={"actions": [{"type": "storage_write", "key": "should-not-reach"}]},
        ),
    }
    result = await dispatch_block(block, block_context, declarations)
    assert result["type"] == "state_update"

    # The built-in handler should have processed it, not the declarative one
    from backend.app.services.plugin_service import storage_get

    stored = await storage_get(
        block_context.db,
        block_context.project_id,
        "override-plugin",
        "should-not-reach",
    )
    assert stored is None
