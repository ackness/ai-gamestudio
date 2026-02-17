from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.core.game_state import GameStateManager
from backend.app.models.character import Character
from backend.app.models.session import GameSession
from backend.app.services.archive_service import (
    create_archive_summary,
    list_archive_versions,
    restore_archive_version,
)


@pytest.mark.asyncio
async def test_create_archive_summary_creates_version(
    db_session, sample_project, sample_session
):
    project_id = sample_project.id
    session_id = sample_session.id

    state_mgr = GameStateManager(db_session)
    await state_mgr.add_message(session_id, "user", "我进入酒馆")
    await state_mgr.add_message(session_id, "assistant", "你看到吧台后有一位老板")

    game_session = await db_session.get(GameSession, session_id)
    assert game_session is not None
    game_session.game_state_json = json.dumps({"turn_count": 3})
    db_session.add(game_session)
    await db_session.commit()

    mock_json = json.dumps(
        {
            "title": "酒馆开局",
            "summary": "玩家进入酒馆并获得初步线索，当前暂无冲突。",
            "key_facts": ["地点: 酒馆"],
            "pending_threads": ["调查可疑陌生人"],
            "next_focus": ["与老板对话"],
        },
        ensure_ascii=False,
    )

    with patch(
        "backend.app.services.archive_service.completion",
        new=AsyncMock(return_value=mock_json),
    ):
        created = await create_archive_summary(
            db_session,
            project=sample_project,
            game_session=game_session,
            trigger="manual",
        )

    assert created["version"] == 1
    assert created["trigger"] == "manual"

    versions = await list_archive_versions(
        db_session,
        project_id=project_id,
        session_id=session_id,
    )
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["active"] is True


@pytest.mark.asyncio
async def test_restore_archive_version_restores_state(
    db_session, sample_project, sample_session
):
    project_id = sample_project.id
    session_id = sample_session.id

    state_mgr = GameStateManager(db_session)

    # Baseline state for version v1
    hero = Character(
        session_id=session_id,
        name="Hero",
        role="player",
        attributes_json=json.dumps({"hp": 100}),
        inventory_json=json.dumps(["sword"]),
    )
    db_session.add(hero)
    game_session = await db_session.get(GameSession, session_id)
    assert game_session is not None
    game_session.phase = "playing"
    game_session.game_state_json = json.dumps({"turn_count": 5})
    db_session.add(game_session)
    await db_session.commit()

    with patch(
        "backend.app.services.archive_service.completion",
        new=AsyncMock(return_value='{"title":"v1","summary":"snapshot"}'),
    ):
        created = await create_archive_summary(
            db_session,
            project=sample_project,
            game_session=game_session,
            trigger="manual",
        )

    assert created["version"] == 1

    # Mutate current state away from v1
    hero.name = "Changed Hero"
    sample_session.phase = "ended"
    db_session.add(hero)
    db_session.add(sample_session)
    await db_session.commit()

    restored = await restore_archive_version(
        db_session,
        project_id=project_id,
        session_id=session_id,
        version=1,
        mode="hard",
    )

    assert restored["ok"] is True
    assert restored["version"] == 1

    # State should match snapshot value (Hero / playing)
    chars = await state_mgr.get_characters(session_id)
    assert len(chars) == 1
    assert chars[0].name == "Hero"

    refreshed_session = await db_session.get(GameSession, session_id)
    assert refreshed_session is not None
    assert refreshed_session.phase == "playing"


@pytest.mark.asyncio
async def test_restore_archive_version_fork_creates_new_session(
    db_session, sample_project, sample_session
):
    project_id = sample_project.id
    source_session_id = sample_session.id

    state_mgr = GameStateManager(db_session)

    hero = Character(
        session_id=source_session_id,
        name="Hero",
        role="player",
        attributes_json=json.dumps({"hp": 100}),
        inventory_json=json.dumps(["sword"]),
    )
    db_session.add(hero)
    game_session = await db_session.get(GameSession, source_session_id)
    assert game_session is not None
    game_session.phase = "playing"
    game_session.game_state_json = json.dumps({"turn_count": 5})
    db_session.add(game_session)
    await db_session.commit()

    with patch(
        "backend.app.services.archive_service.completion",
        new=AsyncMock(return_value='{"title":"v1","summary":"snapshot"}'),
    ):
        created = await create_archive_summary(
            db_session,
            project=sample_project,
            game_session=game_session,
            trigger="manual",
        )
    assert created["version"] == 1

    restored = await restore_archive_version(
        db_session,
        project_id=project_id,
        session_id=source_session_id,
        version=1,
        mode="fork",
    )

    assert restored["ok"] is True
    assert restored["mode"] == "fork"
    fork_session_id = restored["new_session_id"]
    assert fork_session_id != source_session_id

    source_chars = await state_mgr.get_characters(source_session_id)
    fork_chars = await state_mgr.get_characters(fork_session_id)
    assert len(source_chars) == 1
    assert len(fork_chars) == 1
    assert source_chars[0].id != fork_chars[0].id
    assert fork_chars[0].name == "Hero"
