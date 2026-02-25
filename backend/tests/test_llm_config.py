from __future__ import annotations

from backend.app.core.config import settings
from backend.app.core.llm_config import resolve_llm_config


def test_overrides_api_base_without_api_key_is_ignored():
    """Security: api_base override without api_key is ignored to prevent server key leakage."""
    cfg = resolve_llm_config(overrides={"api_base": "https://example.com/v1"})
    assert cfg.source == "call_kwargs"
    # api_base should fall back to server default since no api_key was provided
    assert cfg.api_base == settings.LLM_API_BASE
    assert cfg.model == settings.LLM_MODEL


def test_overrides_api_base_with_api_key_is_applied():
    """When both api_base and api_key are provided, the override is applied."""
    cfg = resolve_llm_config(overrides={"api_base": "https://example.com/v1", "api_key": "sk-user"})
    assert cfg.source == "call_kwargs"
    assert cfg.api_base == "https://example.com/v1"
    assert cfg.api_key == "sk-user"


def test_overrides_api_key_without_model_is_applied():
    cfg = resolve_llm_config(overrides={"api_key": "sk-test"})
    assert cfg.source == "call_kwargs"
    assert cfg.api_key == "sk-test"
    assert cfg.model == settings.LLM_MODEL

