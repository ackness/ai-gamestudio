from __future__ import annotations

from types import SimpleNamespace

import pytest

import backend.app.services.chat_service as svc_mod
from backend.app.core.block_handlers import BlockContext


@pytest.mark.asyncio
async def test_dispatch_blocks_stage_keeps_output_contract_for_ui_and_status_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    async def fake_dispatch(block, context, block_declarations, capability_executor):  # noqa: ANN001, ARG001
        called.append(str(block.get("type", "")))
        return block

    monkeypatch.setattr(svc_mod, "dispatch_block", fake_dispatch)

    blocks = [
        {
            "type": "story_image",
            "id": "out-image",
            "status": "generating",
            "data": {"status": "generating", "title": "林间夜雨"},
        },
        {
            "type": "choice",
            "id": "out-choice",
            "data": {"prompt": "如何行动？", "options": ["潜行", "突袭"]},
        },
        {
            "type": "form",
            "id": "out-form",
            "data": {
                "id": "dialogue",
                "title": "对话输入",
                "fields": [{"name": "reply", "label": "回复", "type": "text"}],
            },
        },
        {
            "type": "notification",
            "id": "out-note",
            "data": {"level": "info", "title": "提示", "content": "你听见脚步声"},
        },
        {
            "type": "event",
            "id": "out-event",
            "data": {
                "action": "create",
                "event_type": "quest",
                "name": "调查失踪案",
                "description": "城北出现失踪人口",
            },
        },
        {
            "type": "character_sheet",
            "id": "out-character",
            "data": {"character_id": "new", "name": "艾琳"},
        },
        {
            "type": "scene_update",
            "id": "out-scene",
            "data": {"action": "move", "name": "雾港码头"},
        },
        {
            "type": "state_update",
            "id": "out-state",
            "data": {"world": {"weather": "rain"}},
        },
        {
            "type": "audio_clip",
            "id": "out-audio",
            "data": {"url": "https://example.invalid/voice.mp3"},
        },
        {
            "type": "video_clip",
            "id": "out-video",
            "data": {"url": "https://example.invalid/cutscene.mp4"},
        },
    ]

    block_context = BlockContext(
        session_id="session-1",
        project_id="project-1",
        db=None,
        state_mgr=SimpleNamespace(),
        autocommit=False,
        turn_id="turn-1",
    )

    events, persisted = await svc_mod._dispatch_blocks_stage(
        blocks,
        block_context=block_context,
        block_declarations={},
        turn_id="turn-1",
        emit_front_events=True,
        log_prefix="contract-test",
    )

    # state_update should be forwarded for frontend state synchronization.
    emitted_types = [evt["type"] for evt in events]
    assert set(emitted_types) == {
        "story_image",
        "choice",
        "form",
        "notification",
        "event",
        "character_sheet",
        "scene_update",
        "state_update",
        "audio_clip",
        "video_clip",
    }

    for evt in events:
        assert evt["turn_id"] == "turn-1"
        assert evt["output"]["id"] == evt["block_id"]
        assert evt["output"]["type"] == evt["type"]
        assert evt["output"]["data"] == evt["data"]
        assert evt["output"]["version"] == "1.0"
        assert evt["output"]["status"] in {"done", "generating"}

    persisted_types = [item["type"] for item in persisted]
    assert "state_update" not in persisted_types
    assert set(persisted_types) == set(emitted_types) - {"state_update"}

    # Ensure status-related blocks still pass through the dispatch stage.
    assert "notification" in called
    assert "event" in called
    assert "character_sheet" in called
    assert "scene_update" in called
