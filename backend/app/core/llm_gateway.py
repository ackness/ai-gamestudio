"""LLM Gateway - Unified interface for LLM calls via LiteLLM."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import litellm
from loguru import logger

from backend.app.core.llm_config import ResolvedLlmConfig, resolve_llm_config
from backend.app.core.network_safety import ApiBaseValidationError, ensure_safe_api_base

# Suppress litellm's built-in verbose logging
litellm.suppress_debug_info = True


# ---------------------------------------------------------------------------
# LlmResult — accumulator for token usage from streaming / non-streaming calls
# ---------------------------------------------------------------------------


@dataclass
class LlmResult:
    """Accumulates content and token usage from an LLM call."""

    content: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def create_stream_result() -> LlmResult:
    """Factory: create a fresh LlmResult accumulator for a streaming call."""
    return LlmResult()


# ---------------------------------------------------------------------------
# Public completion helpers
# ---------------------------------------------------------------------------


async def completion_with_config(
    messages: list[dict[str, str]],
    config: ResolvedLlmConfig,
    stream: bool = False,
    *,
    result_acc: LlmResult | None = None,
    **kwargs: Any,
) -> str | AsyncIterator[str]:
    """Call the LLM via litellm using a ResolvedLlmConfig.

    This is the recommended interface for new code.

    If *result_acc* is provided the token usage reported by the provider
    will be written into it (works for both streaming and non-streaming).
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
        try:
            safe_api_base = ensure_safe_api_base(config.api_base, purpose="LLM")
        except ApiBaseValidationError as exc:
            raise ValueError(str(exc)) from exc
        if safe_api_base:
            call_kwargs["api_base"] = safe_api_base

    try:
        if stream:
            return _stream_chunks(call_kwargs, result_acc=result_acc)
        else:
            response = await litellm.acompletion(**call_kwargs)
            # Populate result_acc from non-streaming response usage
            if result_acc is not None and hasattr(response, "usage") and response.usage:
                result_acc.prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                result_acc.completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0
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
    *,
    result_acc: LlmResult | None = None,
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
    return await completion_with_config(messages, config, stream, result_acc=result_acc, **kwargs)


# ---------------------------------------------------------------------------
# Internal streaming helper
# ---------------------------------------------------------------------------


async def _stream_chunks(
    call_kwargs: dict[str, Any],
    *,
    result_acc: LlmResult | None = None,
) -> AsyncIterator[str]:
    """Yield text chunks from a streaming LLM response.

    If *result_acc* is provided, token usage from the final streaming chunk
    (when the provider sends ``usage`` with ``stream_options.include_usage``)
    will be recorded in it.
    """
    call_kwargs.setdefault("stream_options", {"include_usage": True})
    response = await litellm.acompletion(**call_kwargs)
    async for chunk in response:
        # Capture usage data if present (typically on the last chunk)
        if hasattr(chunk, "usage") and chunk.usage and result_acc is not None:
            result_acc.prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
            result_acc.completion_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
