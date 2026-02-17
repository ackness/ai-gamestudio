from __future__ import annotations

import pytest

from backend.app.services.runtime_settings_service import (
    get_runtime_settings_schema,
    patch_runtime_settings,
    render_settings_template,
    resolve_runtime_settings,
)


def test_schema_contains_core_fields():
    fields = get_runtime_settings_schema(["core-blocks"])
    keys = {field["key"] for field in fields}
    assert "core-blocks.narrative_tone" in keys
    assert "core-blocks.pacing" in keys
    assert "core-blocks.response_length" in keys


@pytest.mark.asyncio
async def test_resolve_runtime_settings_merges_project_and_session_overrides(
    db_session,
    sample_project,
    sample_session,
):
    enabled = ["core-blocks", "story-image"]

    await patch_runtime_settings(
        db_session,
        project_id=sample_project.id,
        enabled_plugins=enabled,
        scope="project",
        values={
            "core-blocks.narrative_tone": "grim",
            "story-image.reference_count": 4,
        },
        autocommit=True,
    )

    await patch_runtime_settings(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
        enabled_plugins=enabled,
        scope="session",
        values={
            "story-image.prompt_template": "BG={{story_background}} FRAME={{frame_prompt}}",
        },
        autocommit=True,
    )

    resolved = await resolve_runtime_settings(
        db_session,
        project_id=sample_project.id,
        session_id=sample_session.id,
        enabled_plugins=enabled,
    )

    assert resolved["values"]["core-blocks.narrative_tone"] == "grim"
    assert resolved["values"]["story-image.reference_count"] == 4
    assert (
        resolved["by_plugin"]["story-image"]["prompt_template"]
        == "BG={{story_background}} FRAME={{frame_prompt}}"
    )


@pytest.mark.asyncio
async def test_patch_runtime_settings_rejects_unknown_key(db_session, sample_project):
    with pytest.raises(ValueError, match="Unknown runtime setting key"):
        await patch_runtime_settings(
            db_session,
            project_id=sample_project.id,
            enabled_plugins=["core-blocks"],
            scope="project",
            values={"unknown.key": "x"},
            autocommit=False,
        )


def test_render_settings_template():
    rendered = render_settings_template(
        "tone={{ tone }} pacing={{pacing}}",
        {"tone": "grim", "pacing": "fast"},
    )
    assert rendered == "tone=grim pacing=fast"
