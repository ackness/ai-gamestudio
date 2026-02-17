from __future__ import annotations

import pytest

from backend.app.models.character import Character
from backend.app.models.game_event import GameEvent
from backend.app.models.message import Message
from backend.app.models.scene import Scene
from backend.app.models.scene_npc import SceneNPC
from backend.app.services import image_service


@pytest.mark.asyncio
async def test_generate_story_image_requires_api_key(
    db_session,
    sample_project,
    sample_session,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(image_service.settings, "IMAGE_GEN_API_KEY", None)
    sample_project.image_model = "gemini-2.5-flash-image-preview"
    sample_project.image_api_key = None
    sample_project.image_api_key_ref = None
    sample_project.image_api_base = "https://api.whatai.cc/v1/chat/completions"
    db_session.add(sample_project)
    await db_session.commit()

    result = await image_service.generate_story_image(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
        title="Frame",
        story_background="The party entered the ruined hall.",
        prompt="A broken throne room lit by moonlight.",
        autocommit=True,
    )
    assert result["status"] == "error"
    assert "Image API key is not configured" in result["error"]


@pytest.mark.asyncio
async def test_generate_story_image_persists_and_links_previous(
    db_session,
    sample_project,
    sample_session,
    monkeypatch: pytest.MonkeyPatch,
):
    sample_project.image_model = "gemini-2.5-flash-image-preview"
    sample_project.image_api_key = "test-image-key"
    sample_project.image_api_base = "https://api.whatai.cc/v1/chat/completions"
    db_session.add(sample_project)
    await db_session.commit()

    counter = {"n": 0}

    captured_messages: list[object] = []

    async def fake_call_image_api(*, prompt: str, config, messages=None):  # noqa: ANN001
        captured_messages.append(messages)
        counter["n"] += 1
        return {
            "id": f"resp-{counter['n']}",
            "choices": [
                {
                    "message": {
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"https://img.example/{counter['n']}.png",
                                },
                            }
                        ]
                    }
                }
            ],
        }

    monkeypatch.setattr(image_service, "_call_image_api", fake_call_image_api)

    first = await image_service.generate_story_image(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
        title="Frame 1",
        story_background="A storm starts outside the town.",
        prompt="The party stands under the inn sign.",
        continuity_notes="Keep clothing color unchanged.",
        autocommit=True,
    )
    assert first["status"] == "ok"
    assert first["image_id"]
    assert first["reference_image_ids"] == []

    second = await image_service.generate_story_image(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
        title="Frame 2",
        story_background="Moments later, they run into the alley.",
        prompt="Rain splashes on cobblestones.",
        autocommit=True,
    )
    assert second["status"] == "ok"
    assert second["reference_image_ids"] == [first["image_id"]]
    assert int(second["debug"].get("reference_input_count") or 0) >= 1
    assert len(captured_messages) >= 2
    second_messages = captured_messages[1]
    assert isinstance(second_messages, list)
    first_message = second_messages[0] if second_messages else None
    assert isinstance(first_message, dict)
    content = first_message.get("content")
    assert isinstance(content, list)
    assert any(
        isinstance(item, dict) and item.get("type") == "image_url"
        for item in content
    )

    rows = await image_service.get_session_story_images(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
    )
    assert len(rows) == 2
    assert rows[0]["image_id"] == first["image_id"]
    assert rows[1]["image_id"] == second["image_id"]


@pytest.mark.asyncio
async def test_regenerate_story_image_creates_new_record(
    db_session,
    sample_project,
    sample_session,
    monkeypatch: pytest.MonkeyPatch,
):
    sample_project.image_model = "gemini-2.5-flash-image-preview"
    sample_project.image_api_key = "test-image-key"
    sample_project.image_api_base = "https://api.whatai.cc/v1/chat/completions"
    db_session.add(sample_project)
    await db_session.commit()

    counter = {"n": 0}

    async def fake_call_image_api(*, prompt: str, config, messages=None):  # noqa: ANN001
        counter["n"] += 1
        return {
            "id": f"resp-{counter['n']}",
            "choices": [
                {
                    "message": {
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"https://img.example/{counter['n']}.png",
                                },
                            }
                        ]
                    }
                }
            ],
        }

    monkeypatch.setattr(image_service, "_call_image_api", fake_call_image_api)

    first = await image_service.generate_story_image(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
        title="Frame A",
        story_background="The hero opens the ancient gate.",
        prompt="Blue runes glow on the stone door.",
        autocommit=True,
    )
    assert first["status"] == "ok"

    regenerated = await image_service.regenerate_story_image(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
        image_id=first["image_id"],
        reason="Need a brighter composition.",
        autocommit=True,
    )
    assert regenerated["status"] == "ok"
    assert regenerated["regenerated_from"] == first["image_id"]
    assert regenerated["image_id"] != first["image_id"]

    rows = await image_service.get_session_story_images(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
    )
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_generate_story_image_builds_debug_prompt_with_world_state_and_multi_scene(
    db_session,
    sample_project,
    sample_session,
    monkeypatch: pytest.MonkeyPatch,
):
    sample_project.image_model = "gemini-2.5-flash-image-preview"
    sample_project.image_api_key = "test-image-key"
    sample_project.image_api_base = "https://api.whatai.cc/v1/chat/completions"
    sample_project.world_doc = (
        "---\n"
        "title: Harbor World\n"
        "---\n\n"
        "The city survives under floating lanterns and old maritime laws."
    )
    db_session.add(sample_project)

    current_scene = Scene(
        session_id=sample_session.id,
        name="Harbor Alley",
        description="Wet stones and narrow alleys under hanging banners.",
        is_current=True,
    )
    protagonist = Character(
        session_id=sample_session.id,
        name="Eira",
        role="player",
    )
    active_event = GameEvent(
        session_id=sample_session.id,
        event_type="quest",
        name="Missing Cartographer",
        description="Find the cartographer before the tide gate closes.",
        status="active",
    )
    latest_narration = Message(
        session_id=sample_session.id,
        role="assistant",
        message_type="narration",
        content="Fog rolls in as bells ring from the north watchtower.",
    )
    db_session.add(current_scene)
    db_session.add(protagonist)
    db_session.add(
        SceneNPC(
            scene_id=current_scene.id,
            character_id=protagonist.id,
            role_in_scene="lead",
        )
    )
    db_session.add(active_event)
    db_session.add(latest_narration)
    await db_session.commit()

    captured_prompt = {"value": ""}

    async def fake_call_image_api(*, prompt: str, config, messages=None):  # noqa: ANN001
        captured_prompt["value"] = prompt
        return {
            "id": "resp-1",
            "choices": [
                {
                    "message": {
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "https://img.example/story.png"},
                            }
                        ]
                    }
                }
            ],
        }

    async def fake_resolve_runtime_settings(*args, **kwargs):  # noqa: ANN001
        return {
            "by_plugin": {
                "story-image": {
                    "style_preset": "cinematic",
                    "multi_scene_policy": "comic",
                    "reference_count": 2,
                    "strict_continuity": True,
                }
            }
        }

    monkeypatch.setattr(image_service, "_call_image_api", fake_call_image_api)
    monkeypatch.setattr(
        image_service,
        "resolve_runtime_settings",
        fake_resolve_runtime_settings,
    )

    result = await image_service.generate_story_image(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
        title="Chase Sequence",
        story_background="The guards spotted the party near the tide gate.",
        prompt="A chase through lantern-lit alleys with splashing puddles.",
        scene_frames=[
            "Frame 1: the party sprints under lanterns.",
            "Frame 2: a guard jumps over crates.",
        ],
        layout_preference="auto",
        autocommit=True,
    )

    assert result["status"] == "ok"
    generated_prompt = captured_prompt["value"]
    assert "[World Lore]" in generated_prompt
    assert "floating lanterns" in generated_prompt
    assert "[Current Text World State]" in generated_prompt
    assert "Current scene: Harbor Alley" in generated_prompt
    assert "NPCs in current scene: Eira (lead)" in generated_prompt
    assert "Active events:" in generated_prompt
    assert "Latest narration:" in generated_prompt
    assert "[Scene Frames]" in generated_prompt
    assert "multi-panel comic" in generated_prompt
    assert result["debug"]["generated_prompt"] == generated_prompt
    assert "Current scene: Harbor Alley" in str(result["debug"]["text_world_state"])

    rows = await image_service.get_session_story_images(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
    )
    assert len(rows) == 1
    assert rows[0]["generation_prompt"] == generated_prompt


def test_build_generation_prompt_honors_single_layout_preference():
    assembled = image_service._build_generation_prompt(
        world_lore="Lore text",
        text_world_state="State text",
        story_background="A multi-step sequence happens in one location.",
        prompt="Show the protagonist aiming a bow.",
        continuity_notes="Keep face and outfit unchanged.",
        references=[],
        previous_images=[],
        scene_frames=["beat 1", "beat 2"],
        layout_preference="single",
        runtime_settings={"multi_scene_policy": "comic"},
    )

    assert "single cinematic frame" in assembled
    assert "multi-panel comic" not in assembled
