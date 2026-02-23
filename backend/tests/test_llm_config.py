from __future__ import annotations

from backend.app.core.config import settings
from backend.app.core.llm_config import resolve_llm_config


def test_overrides_api_base_without_model_is_applied():
    cfg = resolve_llm_config(overrides={"api_base": "https://example.com/v1"})
    assert cfg.source == "call_kwargs"
    assert cfg.api_base == "https://example.com/v1"
    assert cfg.model == settings.LLM_MODEL


def test_overrides_api_key_without_model_is_applied():
    cfg = resolve_llm_config(overrides={"api_key": "sk-test"})
    assert cfg.source == "call_kwargs"
    assert cfg.api_key == "sk-test"
    assert cfg.model == settings.LLM_MODEL

