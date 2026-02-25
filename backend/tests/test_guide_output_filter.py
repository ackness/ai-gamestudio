"""Test that _build_block_instructions filters outputs based on runtime_settings."""
from backend.app.services.plugin_agent import _build_block_instructions


def _guide_metadata():
    return {
        "outputs": {
            "guide": {
                "instruction": "输出 guide 建议",
                "schema": {
                    "type": "object",
                    "properties": {"categories": {"type": "array"}},
                    "required": ["categories"],
                },
            },
            "choices": {
                "instruction": "输出 choices 选项",
                "schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "options": {"type": "array"},
                    },
                    "required": ["prompt", "options"],
                },
            },
        },
        "extensions": {
            "runtime_settings": {
                "fields": {
                    "guide_mode": {
                        "type": "enum",
                        "default": "guide",
                        "options": [
                            {"value": "guide"},
                            {"value": "choices"},
                        ],
                        "output_gate": {
                            "guide": "guide",
                            "choices": "choices",
                        },
                    }
                }
            }
        },
    }


def test_guide_mode_filters_choices():
    result = _build_block_instructions(
        _guide_metadata(),
        plugin_name="guide",
        runtime_settings={"guide_mode": "guide"},
    )
    assert "### guide" in result
    assert "### choices" not in result


def test_choices_mode_filters_guide():
    result = _build_block_instructions(
        _guide_metadata(),
        plugin_name="guide",
        runtime_settings={"guide_mode": "choices"},
    )
    assert "### choices" in result
    assert "### guide" not in result


def test_no_settings_uses_default():
    result = _build_block_instructions(
        _guide_metadata(),
        plugin_name="guide",
        runtime_settings={},
    )
    # default is "guide", so should filter to guide only
    assert "### guide" in result
    assert "### choices" not in result


def test_no_output_gate_includes_all():
    meta = {
        "outputs": {
            "foo": {
                "instruction": "foo inst",
                "schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            "bar": {
                "instruction": "bar inst",
                "schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    }
    result = _build_block_instructions(
        meta, plugin_name="test", runtime_settings={}
    )
    assert "### foo" in result
    assert "### bar" in result
