"""Tests for chat service: message processing, state update parsing."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.block_parser import extract_blocks, strip_blocks


class TestExtractBlocks:
    def test_extracts_state_update(self):
        text = """
Here is the story...

```json:state_update
{"hp": 80, "location": "forest"}
```

The adventure continues.
"""
        blocks = extract_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "state_update"
        assert blocks[0]["data"]["hp"] == 80
        assert blocks[0]["data"]["location"] == "forest"

    def test_no_blocks_returns_empty(self):
        text = "Just a regular response without any blocks."
        assert extract_blocks(text) == []

    def test_invalid_json_skipped(self):
        text = """
```json:state_update
{invalid json here}
```
"""
        assert extract_blocks(text) == []

    def test_nested_objects(self):
        data = {
            "characters": {"hero": {"hp": 95}},
            "world": {"time": "night"},
        }
        text = f"Story...\n\n```json:state_update\n{json.dumps(data)}\n```"
        blocks = extract_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["data"]["characters"]["hero"]["hp"] == 95

    def test_empty_state_update(self):
        text = "```json:state_update\n{}\n```"
        blocks = extract_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["data"] == {}

    def test_multiple_block_types(self):
        text = """Story text.

```json:state_update
{"hp": 50}
```

```json:choices
{"prompt": "What next?", "type": "single", "options": ["A", "B"]}
```
"""
        blocks = extract_blocks(text)
        assert len(blocks) == 2
        assert blocks[0]["type"] == "state_update"
        assert blocks[1]["type"] == "choices"
        assert blocks[1]["data"]["options"] == ["A", "B"]

    def test_strip_blocks(self):
        text = "Hello\n\n```json:state_update\n{}\n```\n\nWorld"
        assert strip_blocks(text) == "Hello\n\n\n\nWorld"


@pytest.mark.asyncio
async def test_process_message_streams_chunks():
    """Test that process_message yields chunk events from LLM streaming."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Create test data
    async with AsyncSession(test_engine) as session:
        from backend.app.models.project import Project
        from backend.app.models.session import GameSession

        project = Project(name="Test", world_doc="# Test World")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        game_session = GameSession(project_id=project.id)
        session.add(game_session)
        await session.commit()
        await session.refresh(game_session)
        session_id = game_session.id

    # Mock the LLM to return a simple stream (mock completion_with_config instead of completion)
    async def mock_completion_with_config(messages, config, stream=False, **kwargs):
        async def gen():
            for chunk in ["Hello, ", "adventurer", "!"]:
                yield chunk

        return gen()

    # Patch engine and dependencies in chat_service module
    import backend.app.services.chat_service as svc_mod

    original_engine = svc_mod.engine
    svc_mod.engine = test_engine

    with (
        patch.object(
            svc_mod, "completion_with_config", side_effect=mock_completion_with_config
        ),
        patch.object(
            svc_mod, "get_enabled_plugins", new_callable=AsyncMock, return_value=[]
        ),
    ):
        events = []
        async for event in svc_mod.process_message(session_id, "I enter the cave"):
            events.append(event)

    svc_mod.engine = original_engine

    # Should have chunk events
    chunk_events = [e for e in events if e["type"] == "chunk"]
    assert len(chunk_events) == 3
    assert chunk_events[0]["content"] == "Hello, "
    assert chunk_events[1]["content"] == "adventurer"
    assert chunk_events[2]["content"] == "!"
    assert all(isinstance(e.get("turn_id"), str) and e["turn_id"] for e in chunk_events)
    assert len({e["turn_id"] for e in chunk_events}) == 1

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_process_message_handles_state_updates():
    """Test that state_update blocks in LLM output produce state_update events."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(test_engine) as session:
        from backend.app.models.project import Project
        from backend.app.models.session import GameSession

        project = Project(name="Test", world_doc="# Test World")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        game_session = GameSession(project_id=project.id)
        session.add(game_session)
        await session.commit()
        await session.refresh(game_session)
        session_id = game_session.id

    state_json = json.dumps({"world": {"hp": 90}})
    response_text = f"You take damage!\n\n```json:state_update\n{state_json}\n```"

    async def mock_completion_with_config(messages, config, stream=False, **kwargs):
        async def gen():
            yield response_text

        return gen()

    import backend.app.services.chat_service as svc_mod

    original_engine = svc_mod.engine
    svc_mod.engine = test_engine

    with (
        patch.object(
            svc_mod, "completion_with_config", side_effect=mock_completion_with_config
        ),
        patch.object(
            svc_mod, "get_enabled_plugins", new_callable=AsyncMock, return_value=[]
        ),
    ):
        events = []
        async for event in svc_mod.process_message(session_id, "I fight the dragon"):
            events.append(event)

    svc_mod.engine = original_engine

    state_events = [e for e in events if e["type"] == "state_update"]
    assert len(state_events) == 1
    assert state_events[0]["data"]["world"]["hp"] == 90
    assert isinstance(state_events[0].get("turn_id"), str)
    assert state_events[0]["turn_id"]

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_process_message_invalid_state_update_skips_write():
    """Invalid state_update blocks should not write DB state and should emit a warning notification."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(test_engine) as session:
        from backend.app.models.project import Project
        from backend.app.models.session import GameSession

        project = Project(name="Test", world_doc="# Test World")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        game_session = GameSession(project_id=project.id)
        session.add(game_session)
        await session.commit()
        await session.refresh(game_session)
        session_id = game_session.id

    bad_state_json = json.dumps({"hp": 90})
    response_text = f"```json:state_update\n{bad_state_json}\n```"

    async def mock_completion_with_config(messages, config, stream=False, **kwargs):
        async def gen():
            yield response_text

        return gen()

    import backend.app.services.chat_service as svc_mod

    original_engine = svc_mod.engine
    svc_mod.engine = test_engine

    with (
        patch.object(
            svc_mod, "completion_with_config", side_effect=mock_completion_with_config
        ),
        patch.object(
            svc_mod, "get_enabled_plugins", new_callable=AsyncMock, return_value=[]
        ),
    ):
        events = []
        async for event in svc_mod.process_message(session_id, "test"):
            events.append(event)

    svc_mod.engine = original_engine

    state_events = [e for e in events if e["type"] == "state_update"]
    assert state_events == []

    notification_events = [e for e in events if e["type"] == "notification"]
    assert len(notification_events) == 1
    assert notification_events[0]["data"]["level"] == "error"

    async with AsyncSession(test_engine) as session:
        from backend.app.models.character import Character
        from backend.app.core.game_state import GameStateManager

        state_mgr = GameStateManager(session)
        world = await state_mgr.get_session_world_state(session_id)
        assert "hp" not in world

        char_stmt = select(Character).where(Character.session_id == session_id)
        chars = list((await session.exec(char_stmt)).all())
        assert chars == []

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_process_message_persists_world_state_and_injects_into_next_prompt():
    """Session world state should persist in DB and be injected on subsequent turns."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(test_engine) as session:
        from backend.app.models.project import Project
        from backend.app.models.session import GameSession

        project = Project(name="Test", world_doc="# Test World")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        game_session = GameSession(project_id=project.id)
        session.add(game_session)
        await session.commit()
        await session.refresh(game_session)
        session_id = game_session.id

    responses = [
        '```json:state_update\n{"world":{"corruption":{"value":2},"region":"ruins"}}\n```',
        "The journey continues.",
    ]
    captured_messages: list[list[dict[str, str]]] = []

    async def mock_completion_with_config(messages, config, stream=False, **kwargs):
        idx = len(captured_messages)
        captured_messages.append(messages)
        text = responses[idx]

        async def gen():
            yield text

        return gen()

    import backend.app.services.chat_service as svc_mod

    original_engine = svc_mod.engine
    svc_mod.engine = test_engine

    with (
        patch.object(
            svc_mod, "completion_with_config", side_effect=mock_completion_with_config
        ),
        patch.object(
            svc_mod, "get_enabled_plugins", new_callable=AsyncMock, return_value=[]
        ),
    ):
        async for _ in svc_mod.process_message(session_id, "first"):
            pass
        async for _ in svc_mod.process_message(session_id, "second"):
            pass

    svc_mod.engine = original_engine

    assert len(captured_messages) == 2
    second_system_prompt = captured_messages[1][0]["content"]
    assert "Session World State" in second_system_prompt
    assert '"corruption"' in second_system_prompt
    assert '"value": 2' in second_system_prompt
    assert '"region": "ruins"' in second_system_prompt

    async with AsyncSession(test_engine) as session:
        from backend.app.core.game_state import GameStateManager

        state_mgr = GameStateManager(session)
        world = await state_mgr.get_session_world_state(session_id)
        assert world["corruption"]["value"] == 2
        assert world["region"] == "ruins"

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_process_message_rolls_back_stage_b_when_block_handler_fails():
    """When block handling fails, stage-B writes should rollback atomically."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(test_engine) as session:
        from backend.app.models.project import Project
        from backend.app.models.session import GameSession

        project = Project(name="Test", world_doc="# Test World")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        game_session = GameSession(project_id=project.id)
        session.add(game_session)
        await session.commit()
        await session.refresh(game_session)
        session_id = game_session.id

    response_text = (
        "Narration.\n\n"
        "```json:state_update\n"
        '{"world": {"weather": "rain"}}\n'
        "```"
    )

    async def mock_completion_with_config(messages, config, stream=False, **kwargs):
        async def gen():
            yield response_text

        return gen()

    import backend.app.services.chat_service as svc_mod

    original_engine = svc_mod.engine
    svc_mod.engine = test_engine

    with (
        patch.object(
            svc_mod, "completion_with_config", side_effect=mock_completion_with_config
        ),
        patch.object(
            svc_mod, "get_enabled_plugins", new_callable=AsyncMock, return_value=[]
        ),
        patch.object(
            svc_mod,
            "dispatch_block",
            side_effect=RuntimeError("synthetic handler failure"),
        ),
    ):
        events = []
        async for event in svc_mod.process_message(session_id, "test rollback"):
            events.append(event)

    svc_mod.engine = original_engine

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "回合状态保存失败" in error_events[0]["content"]

    async with AsyncSession(test_engine) as session:
        from backend.app.models.character import Character
        from backend.app.models.message import Message
        from backend.app.models.session import GameSession

        msg_stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())  # type: ignore[arg-type]
        )
        messages = list((await session.exec(msg_stmt)).all())
        # Stage A user message may commit, stage B should be rolled back.
        assert [m.role for m in messages] == ["user"]

        chars_stmt = select(Character).where(Character.session_id == session_id)
        chars = list((await session.exec(chars_stmt)).all())
        assert chars == []

        stored_session = await session.get(GameSession, session_id)
        assert stored_session is not None
        game_state = json.loads(stored_session.game_state_json or "{}")
        assert int(game_state.get("turn_count", 0) or 0) == 0

    await test_engine.dispose()



@pytest.mark.asyncio
async def test_process_message_yields_token_usage_event():
    """process_message should yield a token_usage event with cost and context info."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Create test data
    async with AsyncSession(test_engine) as session:
        from backend.app.models.project import Project
        from backend.app.models.session import GameSession

        project = Project(name="Test", world_doc="# Test World")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        game_session = GameSession(project_id=project.id)
        session.add(game_session)
        await session.commit()
        await session.refresh(game_session)
        session_id = game_session.id

    # Mock the LLM to return a simple stream and populate result_acc
    async def mock_completion_with_config(messages, config, stream=False, **kwargs):
        result_acc = kwargs.get("result_acc")
        if result_acc is not None:
            result_acc.prompt_tokens = 150
            result_acc.completion_tokens = 50

        async def gen():
            for chunk in ["Hello, ", "adventurer", "!"]:
                yield chunk

        return gen()

    import backend.app.services.chat_service as svc_mod

    original_engine = svc_mod.engine

    svc_mod.engine = test_engine

    with (
        patch.object(
            svc_mod, "completion_with_config", side_effect=mock_completion_with_config
        ),
        patch.object(
            svc_mod, "get_enabled_plugins", new_callable=AsyncMock, return_value=[]
        ),
        patch.object(
            svc_mod, "count_message_tokens", return_value=100
        ),
        patch.object(
            svc_mod, "get_model_context_window",
            return_value={"max_input_tokens": 1000, "max_output_tokens": 100},
        ),
        patch.object(
            svc_mod, "calculate_turn_cost", return_value=0.0025
        ),
    ):
        events = []
        async for event in svc_mod.process_message(session_id, "I enter the cave"):
            events.append(event)

    svc_mod.engine = original_engine

    # Should have a token_usage event
    token_events = [e for e in events if e["type"] == "token_usage"]
    assert len(token_events) == 1

    data = token_events[0]["data"]
    assert data["prompt_tokens"] == 150
    assert data["completion_tokens"] == 50
    assert data["total_tokens"] == 200
    assert data["turn_cost"] == 0.0025
    assert data["context_usage"] == round(150 / 1000, 4)
    assert data["max_input_tokens"] == 1000
    assert isinstance(data["model"], str)
    # Cumulative totals should match single-turn values
    assert data["total_prompt_tokens"] == 150
    assert data["total_completion_tokens"] == 50
    assert data["total_cost"] == 0.0025

    # Verify turn_id is consistent across events
    turn_ids = {e["turn_id"] for e in events if "turn_id" in e}
    assert len(turn_ids) == 1

    await test_engine.dispose()


@pytest.mark.asyncio
async def test_process_message_token_usage_uses_estimates_when_no_actual():
    """token_usage event should fall back to estimates when result_acc has no tokens."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import backend.app.models  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(test_engine) as session:
        from backend.app.models.project import Project
        from backend.app.models.session import GameSession

        project = Project(name="Test", world_doc="# Test World")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        game_session = GameSession(project_id=project.id)
        session.add(game_session)
        await session.commit()
        await session.refresh(game_session)
        session_id = game_session.id

    # Mock LLM without populating result_acc (simulates provider not returning usage)
    async def mock_completion_with_config(messages, config, stream=False, **kwargs):
        async def gen():
            yield "Short reply"

        return gen()

    import backend.app.services.chat_service as svc_mod

    original_engine = svc_mod.engine
    svc_mod.engine = test_engine

    with (
        patch.object(
            svc_mod, "completion_with_config", side_effect=mock_completion_with_config
        ),
        patch.object(
            svc_mod, "get_enabled_plugins", new_callable=AsyncMock, return_value=[]
        ),
        patch.object(
            svc_mod, "count_message_tokens", return_value=200
        ),
        patch.object(
            svc_mod, "get_model_context_window",
            return_value={"max_input_tokens": 2000, "max_output_tokens": 500},
        ),
        patch.object(
            svc_mod, "calculate_turn_cost", return_value=0.001
        ),
    ):
        events = []
        async for event in svc_mod.process_message(session_id, "test"):
            events.append(event)

    svc_mod.engine = original_engine

    token_events = [e for e in events if e["type"] == "token_usage"]
    assert len(token_events) == 1

    data = token_events[0]["data"]
    # Should fall back to estimated prompt tokens (200)
    assert data["prompt_tokens"] == 200
    # completion_tokens should fall back to len("Short reply") // 4 = 2 (at least 1)
    assert data["completion_tokens"] == max(1, len("Short reply") // 4)
    assert data["context_usage"] == round(200 / 2000, 4)

    await test_engine.dispose()
