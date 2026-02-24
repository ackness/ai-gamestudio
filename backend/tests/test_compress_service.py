"""Tests for compress_service — LLM-based history summarization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.compress_service import (
    build_compression_prompt,
    compress_history,
    should_compress,
)


# ---------------------------------------------------------------------------
# should_compress
# ---------------------------------------------------------------------------


def test_should_compress_below_threshold():
    assert should_compress(0.3, 0.7) is False


def test_should_compress_above_threshold():
    assert should_compress(0.75, 0.7) is True


def test_should_compress_at_threshold():
    assert should_compress(0.7, 0.7) is True


def test_should_compress_zero_context():
    assert should_compress(0.0, 0.7) is False


def test_should_compress_negative_context():
    assert should_compress(-0.1, 0.7) is False


def test_should_compress_default_threshold():
    # Default threshold is 0.7
    assert should_compress(0.5) is False
    assert should_compress(0.8) is True


# ---------------------------------------------------------------------------
# build_compression_prompt
# ---------------------------------------------------------------------------


def _make_message(role: str, content: str) -> MagicMock:
    """Create a mock message object with .role and .content attributes."""
    msg = MagicMock()
    msg.role = role
    msg.content = content
    return msg


def test_build_compression_prompt():
    messages = [
        _make_message("user", "I enter the tavern."),
        _make_message("assistant", "The bartender greets you warmly."),
    ]
    prompt = build_compression_prompt(messages)

    assert isinstance(prompt, list)
    assert len(prompt) == 2

    # System message
    assert prompt[0]["role"] == "system"
    assert "summar" in prompt[0]["content"].lower()

    # User message contains conversation text
    assert prompt[1]["role"] == "user"
    assert "I enter the tavern." in prompt[1]["content"]
    assert "The bartender greets you warmly." in prompt[1]["content"]


def test_build_compression_prompt_with_existing_summary():
    messages = [
        _make_message("user", "I attack the dragon."),
        _make_message("assistant", "The dragon breathes fire."),
    ]
    existing = "Previously, the hero arrived at the castle."
    prompt = build_compression_prompt(messages, existing_summary=existing)

    user_content = prompt[1]["content"]
    assert existing in user_content
    assert "I attack the dragon." in user_content


def test_build_compression_prompt_preserves_roles():
    messages = [
        _make_message("user", "Hello"),
        _make_message("assistant", "Welcome"),
        _make_message("system", "Game started"),
    ]
    prompt = build_compression_prompt(messages)
    user_content = prompt[1]["content"]
    assert "user" in user_content.lower() or "User" in user_content
    assert "assistant" in user_content.lower() or "Assistant" in user_content


def test_build_compression_prompt_empty_messages():
    prompt = build_compression_prompt([])
    assert isinstance(prompt, list)
    assert len(prompt) == 2


# ---------------------------------------------------------------------------
# compress_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_history_returns_summary():
    messages = [
        _make_message("user", "I explore the dungeon."),
        _make_message("assistant", "You find a treasure chest."),
    ]
    mock_config = MagicMock()

    with patch(
        "backend.app.services.compress_service.completion_with_config",
        new_callable=AsyncMock,
        return_value="The hero explored a dungeon and found treasure.",
    ) as mock_llm, patch(
        "backend.app.services.compress_service.resolve_llm_config",
        return_value=mock_config,
    ):
        result = await compress_history(
            messages_to_compress=messages,
            existing_summary="",
            model="test-model",
        )

    assert "summary" in result
    assert result["summary"] == "The hero explored a dungeon and found treasure."
    mock_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_compress_history_with_existing_summary():
    messages = [
        _make_message("user", "I fight the boss."),
    ]
    existing = "The hero has been travelling for days."
    mock_config = MagicMock()

    with patch(
        "backend.app.services.compress_service.completion_with_config",
        new_callable=AsyncMock,
        return_value="After days of travel, the hero fought the boss.",
    ), patch(
        "backend.app.services.compress_service.resolve_llm_config",
        return_value=mock_config,
    ):
        result = await compress_history(
            messages_to_compress=messages,
            existing_summary=existing,
            model="test-model",
        )

    assert result["summary"] == "After days of travel, the hero fought the boss."


@pytest.mark.asyncio
async def test_compress_history_fallback_on_error():
    messages = [
        _make_message("user", "Something."),
    ]
    existing = "Previous summary that should be preserved."
    mock_config = MagicMock()

    with patch(
        "backend.app.services.compress_service.completion_with_config",
        new_callable=AsyncMock,
        side_effect=Exception("LLM service unavailable"),
    ), patch(
        "backend.app.services.compress_service.resolve_llm_config",
        return_value=mock_config,
    ):
        result = await compress_history(
            messages_to_compress=messages,
            existing_summary=existing,
            model="test-model",
        )

    # Should fall back to existing summary, not crash
    assert result["summary"] == existing


@pytest.mark.asyncio
async def test_compress_history_fallback_empty_on_error_no_existing():
    messages = [
        _make_message("user", "Something."),
    ]
    mock_config = MagicMock()

    with patch(
        "backend.app.services.compress_service.completion_with_config",
        new_callable=AsyncMock,
        side_effect=Exception("LLM error"),
    ), patch(
        "backend.app.services.compress_service.resolve_llm_config",
        return_value=mock_config,
    ):
        result = await compress_history(
            messages_to_compress=messages,
            existing_summary="",
            model="test-model",
        )

    assert result["summary"] == ""


@pytest.mark.asyncio
async def test_compress_history_with_llm_overrides():
    messages = [
        _make_message("user", "Hello"),
    ]
    mock_config = MagicMock()
    overrides = {"api_key": "sk-test", "api_base": "https://custom.api"}

    with patch(
        "backend.app.services.compress_service.completion_with_config",
        new_callable=AsyncMock,
        return_value="Summary text.",
    ), patch(
        "backend.app.services.compress_service.resolve_llm_config",
        return_value=mock_config,
    ) as mock_resolve:
        result = await compress_history(
            messages_to_compress=messages,
            existing_summary="",
            model="test-model",
            llm_overrides=overrides,
        )

    assert result["summary"] == "Summary text."
    # Verify overrides were passed to resolve_llm_config
    call_kwargs = mock_resolve.call_args
    assert call_kwargs[1]["overrides"]["model"] == "test-model"
    assert call_kwargs[1]["overrides"]["api_key"] == "sk-test"
    assert call_kwargs[1]["overrides"]["api_base"] == "https://custom.api"
