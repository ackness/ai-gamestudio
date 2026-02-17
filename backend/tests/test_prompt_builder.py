"""Tests for PromptBuilder: injection positions, priority ordering, build output."""
from __future__ import annotations

import pytest

from backend.app.core.prompt_builder import POSITIONS, PromptBuilder


class TestPromptBuilder:
    def test_empty_builder(self):
        builder = PromptBuilder()
        assert builder.build() == []

    def test_system_injection(self):
        builder = PromptBuilder()
        builder.inject("system", 0, "You are a DM.")
        messages = builder.build()
        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert "You are a DM." in messages[0]["content"]

    def test_multiple_system_positions_combine(self):
        builder = PromptBuilder()
        builder.inject("system", 0, "System instructions")
        builder.inject("character", 10, "Character info")
        builder.inject("world-state", 20, "World state data")
        builder.inject("memory", 30, "Memory context")
        messages = builder.build()
        # All four positions should be combined into one system message
        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        content = messages[0]["content"]
        assert "System instructions" in content
        assert "Character info" in content
        assert "World state data" in content
        assert "Memory context" in content

    def test_priority_ordering_within_position(self):
        builder = PromptBuilder()
        builder.inject("system", 100, "Low priority")
        builder.inject("system", 0, "High priority")
        messages = builder.build()
        content = messages[0]["content"]
        # High priority (0) should come before low priority (100)
        assert content.index("High priority") < content.index("Low priority")

    def test_chat_history_creates_separate_messages(self):
        builder = PromptBuilder()
        builder.inject("system", 0, "System")
        builder.inject("chat-history", 0, "user: Hello")
        builder.inject("chat-history", 1, "assistant: Hi there!")
        builder.inject("chat-history", 2, "user: What now?")
        messages = builder.build()
        # 1 system + 3 chat messages
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "Hi there!"
        assert messages[3]["role"] == "user"

    def test_pre_response_appended_last(self):
        builder = PromptBuilder()
        builder.inject("system", 0, "System")
        builder.inject("chat-history", 0, "user: Hello")
        builder.inject("pre-response", 0, "Remember to include state updates.")
        messages = builder.build()
        assert len(messages) == 3
        assert messages[-1]["role"] == "system"
        assert "state updates" in messages[-1]["content"]

    def test_invalid_position_raises(self):
        builder = PromptBuilder()
        with pytest.raises(ValueError, match="Invalid position"):
            builder.inject("invalid-position", 0, "content")

    def test_full_pipeline(self):
        """Simulate a realistic prompt build with all positions."""
        builder = PromptBuilder()
        builder.inject("system", 0, "You are the DM of a dark fantasy RPG.")
        builder.inject("character", 10, "Player: Elara, a ranger")
        builder.inject("world-state", 50, "Location: Dark Forest")
        builder.inject("memory", 10, "Previously: Elara defeated a wolf")
        builder.inject("chat-history", 0, "user: I look around the forest.")
        builder.inject("chat-history", 1, "assistant: You see ancient trees...")
        builder.inject("chat-history", 2, "user: I move deeper into the forest.")
        builder.inject("pre-response", 0, "Include state_update if needed.")

        messages = builder.build()

        # Structure: 1 system + 3 chat + 1 pre-response
        assert len(messages) == 5
        assert messages[0]["role"] == "system"
        assert "DM" in messages[0]["content"]
        assert "Elara" in messages[0]["content"]
        assert "Dark Forest" in messages[0]["content"]
        assert "wolf" in messages[0]["content"]
        assert messages[-1]["role"] == "system"
        assert "state_update" in messages[-1]["content"]

    def test_all_positions_are_valid(self):
        """Ensure all declared POSITIONS are accepted."""
        for pos in POSITIONS:
            builder = PromptBuilder()
            builder.inject(pos, 0, f"content for {pos}")
            # Should not raise
            builder.build()
