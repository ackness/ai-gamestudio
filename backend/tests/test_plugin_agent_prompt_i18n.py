from __future__ import annotations

from pathlib import Path

from backend.app.services.plugin_agent_prompt import (
    _build_block_instructions,
    _build_tool_instructions,
    _resolve_base_prompt,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_resolve_base_prompt_prefers_default_before_english_for_zh(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write(plugin_root / "prompts/agent/base.md", "BASE_DEFAULT")
    _write(plugin_root / "prompts/agent/base.en.md", "BASE_EN")

    metadata = {
        "extensions": {
            "agent_prompt": {
                "base_file": "prompts/agent/base.md",
            }
        }
    }

    resolved = _resolve_base_prompt(
        plugin_root,
        metadata,
        fallback_content="FALLBACK",
        session_language="zh-CN",
    )

    assert resolved == "BASE_DEFAULT"


def test_resolve_base_prompt_uses_english_fallback_when_default_missing(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write(plugin_root / "prompts/agent/base.en.md", "BASE_EN")

    metadata = {
        "extensions": {
            "agent_prompt": {
                "base_file": "prompts/agent/base.md",
            }
        }
    }

    resolved = _resolve_base_prompt(
        plugin_root,
        metadata,
        fallback_content="FALLBACK",
        session_language="zh-CN",
    )

    assert resolved == "BASE_EN"


def test_build_block_instructions_uses_localized_output_file(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write(plugin_root / "prompts/agent/outputs/guide.md", "ZH guide output")
    _write(plugin_root / "prompts/agent/outputs/guide.en.md", "EN guide output")

    metadata = {
        "outputs": {
            "guide": {
                "instruction": "fallback instruction",
                "schema": {
                    "type": "object",
                    "properties": {"categories": {"type": "array"}},
                },
            }
        },
        "extensions": {
            "agent_prompt": {
                "output_files": {
                    "guide": "prompts/agent/outputs/guide.md",
                }
            }
        },
    }

    instructions = _build_block_instructions(
        metadata,
        plugin_name="guide",
        plugin_root=plugin_root,
        session_language="en",
    )

    assert "EN guide output" in instructions
    assert "ZH guide output" not in instructions


def test_build_tool_instructions_uses_localized_tool_file(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    _write(plugin_root / "prompts/agent/tools/emit.md", "ZH emit tool")
    _write(plugin_root / "prompts/agent/tools/emit.en.md", "EN emit tool")

    metadata = {
        "extensions": {
            "agent_prompt": {
                "tool_files": {
                    "emit": "prompts/agent/tools/emit.md",
                }
            }
        }
    }
    tools = [{"function": {"name": "emit"}}]

    instructions = _build_tool_instructions(
        plugin_root=plugin_root,
        metadata=metadata,
        tools=tools,
        session_language="en",
    )

    assert "EN emit tool" in instructions
    assert "ZH emit tool" not in instructions
