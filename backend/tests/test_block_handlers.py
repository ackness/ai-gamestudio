from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.core.block_handlers import BlockContext, StateUpdateHandler


class _DummyStateManager:
    def __init__(self) -> None:
        self.updated_world: dict[str, Any] | None = None

    async def upsert_character(self, session_id: str, char_data: dict[str, Any]) -> Any:  # noqa: ARG002
        return SimpleNamespace(
            id="char-1",
            name="Hero",
            role="player",
            description="desc",
            personality="bold",
            attributes_json="{invalid-json",
            inventory_json="[broken-json",
        )

    async def update_world_state(self, session_id: str, world: dict[str, Any]) -> None:  # noqa: ARG002
        self.updated_world = dict(world)

    async def get_session_world_state(self, session_id: str) -> dict[str, Any]:  # noqa: ARG002
        return {"weather": "rain"}


class _RejectingStateManager(_DummyStateManager):
    async def upsert_character(self, session_id: str, char_data: dict[str, Any]) -> Any:  # noqa: ARG002
        raise ValueError("invalid character reference")


@pytest.mark.asyncio
async def test_state_update_handler_tolerates_corrupted_character_json() -> None:
    handler = StateUpdateHandler()
    mgr = _DummyStateManager()
    ctx = BlockContext(
        session_id="session-1",
        project_id="project-1",
        db=None,  # not used by StateUpdateHandler
        state_mgr=mgr,
        autocommit=False,
    )

    result = await handler.process(
        {"characters": [{"name": "Hero"}], "world": {"weather": "rain"}},
        ctx,
    )

    assert result is not None
    assert result["characters"][0]["attributes"] == {}
    assert result["characters"][0]["inventory"] == []
    assert result["world"] == {"weather": "rain"}


@pytest.mark.asyncio
async def test_state_update_handler_skips_invalid_character_delta() -> None:
    handler = StateUpdateHandler()
    mgr = _RejectingStateManager()
    ctx = BlockContext(
        session_id="session-1",
        project_id="project-1",
        db=None,
        state_mgr=mgr,
        autocommit=False,
    )

    result = await handler.process(
        {"characters": [{"character_id": "player"}], "world": {"weather": "rain"}},
        ctx,
    )

    assert result is not None
    assert "characters" not in result
    assert result["world"] == {"weather": "rain"}
