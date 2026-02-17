#!/usr/bin/env python3
"""Simple test script to verify llm_config boundary cases."""

import sys

sys.path.insert(0, "/Users/wuyong/codes/game/ai-gamestudio")

from backend.app.core.llm_config import resolve_llm_config, _is_empty
from backend.app.models.project import Project
from backend.app.models.llm_profile import LlmProfile


def test_is_empty():
    """Test the _is_empty helper function."""
    assert _is_empty(None) is True
    assert _is_empty("") is True
    assert _is_empty("   ") is True  # whitespace only
    assert _is_empty("xxx") is False
    assert _is_empty("xxx ") is False  # has content
    print("✓ _is_empty tests passed")


def test_resolve_empty_string_fallback():
    """Test that empty string triggers fallback to settings (the key fix)."""
    from backend.app.core.config import settings

    # Create a project with model but empty api_key
    project = Project(
        name="Test",
        llm_model="deepseek/deepseek-chat",
        llm_api_key="",  # Empty string - should fallback
        llm_api_base="",
    )

    config = resolve_llm_config(project=project)

    assert config.model == "deepseek/deepseek-chat"
    # The key fix: empty string should trigger fallback to settings, not be used as-is
    assert config.api_key == settings.LLM_API_KEY  # Should fallback to settings
    assert config.source == "project"
    print("✓ Empty string fallback test passed (correctly falls back to settings)")


def test_resolve_none_fallback():
    """Test that None triggers fallback to settings."""
    from backend.app.core.config import settings

    project = Project(
        name="Test",
        llm_model="deepseek/deepseek-chat",
        llm_api_key=None,  # None - should fallback
        llm_api_base=None,
    )

    config = resolve_llm_config(project=project)

    assert config.model == "deepseek/deepseek-chat"
    # None should trigger fallback to settings
    assert config.api_key == settings.LLM_API_KEY
    assert config.source == "project"
    print("✓ None fallback test passed (correctly falls back to settings)")


def test_resolve_with_api_key():
    """Test that valid api_key is used directly."""
    project = Project(
        name="Test",
        llm_model="deepseek/deepseek-chat",
        llm_api_key="project-specific-key",
        llm_api_base="https://api.deepseek.com",
    )

    config = resolve_llm_config(project=project)

    assert config.model == "deepseek/deepseek-chat"
    assert config.api_key == "project-specific-key"
    assert config.api_base == "https://api.deepseek.com"
    assert config.source == "project"
    print("✓ Valid api_key test passed")


def test_config_is_empty_key():
    """Test the is_empty_key method."""
    from backend.app.core.llm_config import ResolvedLlmConfig

    # Empty key
    config1 = ResolvedLlmConfig(
        model="gpt-4o", api_key=None, api_base=None, source="test"
    )
    assert config1.is_empty_key() is True

    # Empty string key
    config2 = ResolvedLlmConfig(
        model="gpt-4o", api_key="", api_base=None, source="test"
    )
    assert config2.is_empty_key() is True

    # Whitespace only
    config3 = ResolvedLlmConfig(
        model="gpt-4o", api_key="   ", api_base=None, source="test"
    )
    assert config3.is_empty_key() is True

    # Valid key
    config4 = ResolvedLlmConfig(
        model="gpt-4o", api_key="sk-xxx", api_base=None, source="test"
    )
    assert config4.is_empty_key() is False

    print("✓ is_empty_key tests passed")


if __name__ == "__main__":
    print("Running llm_config boundary case tests...\n")

    test_is_empty()
    test_resolve_empty_string_fallback()
    test_resolve_none_fallback()
    test_resolve_with_api_key()
    test_config_is_empty_key()

    print("\n✅ All boundary case tests passed!")
