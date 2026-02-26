from __future__ import annotations

import json

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.game_state import GameStateManager


@pytest.mark.asyncio
async def test_session_world_state_merge_and_delete(
    db_session: AsyncSession,
    sample_project,
    sample_session,
):
    mgr = GameStateManager(db_session)

    await mgr.update_world_state(
        sample_session.id,
        {
            "corruption": {"value": 1, "mark": None},
            "region": "ruins",
        },
    )
    await mgr.update_world_state(
        sample_session.id,
        {
            "corruption": {"value": 2},
            "_delete": ["region"],
        },
    )

    world = await mgr.get_session_world_state(sample_session.id)
    assert world["corruption"]["value"] == 2
    assert "mark" in world["corruption"]
    assert "region" not in world


@pytest.mark.asyncio
async def test_get_world_state_includes_project_context_and_runtime(
    db_session: AsyncSession,
    sample_project,
    sample_session,
):
    mgr = GameStateManager(db_session)
    await mgr.update_world_state(
        sample_session.id,
        {"weather": "storm"},
    )

    payload = await mgr.get_world_state(sample_session.id, sample_project.id)
    assert payload["project_name"] == sample_project.name
    assert payload["world_doc"] == sample_project.world_doc
    assert payload["session_world_state"]["weather"] == "storm"


@pytest.mark.asyncio
async def test_upsert_character_resolves_player_alias(
    db_session: AsyncSession,
    sample_session,
):
    mgr = GameStateManager(db_session)
    player = await mgr.upsert_character(
        sample_session.id,
        {"name": "Ayla", "role": "player", "attributes": {"hp": 100}},
    )

    updated = await mgr.upsert_character(
        sample_session.id,
        {"character_id": "player", "attributes": {"hp": 92}},
    )
    assert updated.id == player.id
    assert json.loads(updated.attributes_json)["hp"] == 92


@pytest.mark.asyncio
async def test_upsert_character_rejects_unknown_id_without_name(
    db_session: AsyncSession,
    sample_session,
):
    mgr = GameStateManager(db_session)
    before = await mgr.get_characters(sample_session.id)

    with pytest.raises(ValueError):
        await mgr.upsert_character(
            sample_session.id,
            {"character_id": "npc_missing_id", "attributes": {"hp": 1}},
        )

    after = await mgr.get_characters(sample_session.id)
    assert len(after) == len(before)
