"""LLM Gateway - Unified interface for LLM calls via LiteLLM."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import litellm
from loguru import logger

from backend.app.core.llm_config import ResolvedLlmConfig, resolve_llm_config

# Suppress litellm's built-in verbose logging
litellm.suppress_debug_info = True


async def completion_with_config(
    messages: list[dict[str, str]],
    config: ResolvedLlmConfig,
    stream: bool = False,
    **kwargs: Any,
) -> str | AsyncIterator[str]:
    """Call the LLM via litellm using a ResolvedLlmConfig.

    This is the recommended interface for new code.
    """
    call_kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "stream": stream,
        **kwargs,
    }

    # Only add api_key if not empty
    if not config.is_empty_key():
        call_kwargs["api_key"] = config.api_key
    if config.api_base:
        call_kwargs["api_base"] = config.api_base

    try:
        if stream:
            return _stream_chunks(call_kwargs)
        else:
            response = await litellm.acompletion(**call_kwargs)
            return response.choices[0].message.content or ""
    except Exception:
        logger.exception("LLM call failed")
        raise


async def completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    stream: bool = False,
    api_key: str | None = None,
    api_base: str | None = None,
    **kwargs: Any,
) -> str | AsyncIterator[str]:
    """Call the LLM via litellm (legacy interface for backward compatibility).

    Uses resolve_llm_config internally to handle configuration priority.
    """
    config = resolve_llm_config(
        overrides={
            "model": model,
            "api_key": api_key,
            "api_base": api_base,
        }
    )
    return await completion_with_config(messages, config, stream, **kwargs)


async def _stream_chunks(call_kwargs: dict[str, Any]) -> AsyncIterator[str]:
    response = await litellm.acompletion(**call_kwargs)
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
