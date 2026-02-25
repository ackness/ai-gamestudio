"""Token counting, cost calculation, and model info via LiteLLM."""

from __future__ import annotations

from dataclasses import dataclass

import litellm
from loguru import logger


@dataclass
class TokenUsage:
    """Tracks token counts and costs for a single LLM turn."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cost: float = 0.0
    completion_cost: float = 0.0
    total_cost: float = 0.0


def count_message_tokens(model: str, messages: list[dict[str, str]]) -> int:
    """Count tokens in *messages* for *model* using LiteLLM's tokenizer.

    Falls back to a rough character-based estimate (chars / 4) when the
    tokenizer is unavailable or the model is unknown.
    """
    try:
        return litellm.token_counter(model=model, messages=messages)
    except Exception:
        logger.warning(
            "token_counter failed for model={}, falling back to char estimate",
            model,
        )
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4


def get_model_context_window(model: str) -> dict[str, int]:
    """Return ``{"max_input_tokens": …, "max_output_tokens": …}`` for *model*.

    Returns zeros for both fields when the model is not recognised.
    """
    try:
        info = litellm.get_model_info(model)
        return {
            "max_input_tokens": info.get("max_input_tokens", 0) or 0,
            "max_output_tokens": info.get("max_output_tokens", 0) or 0,
        }
    except Exception:
        logger.warning("get_model_info failed for model={}", model)
        return {"max_input_tokens": 0, "max_output_tokens": 0}


def calculate_turn_cost(
    model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Calculate the total USD cost for a single LLM turn.

    Uses ``litellm.cost_per_token`` which returns
    ``(prompt_cost, completion_cost)``.  Returns ``0.0`` on error.
    """
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return prompt_cost + completion_cost
    except Exception:
        logger.warning("cost_per_token failed for model={}", model)
        return 0.0


def get_model_pricing(model: str) -> dict[str, float]:
    """Return per-token pricing for *model*.

    Returns ``{"input_cost_per_token": …, "output_cost_per_token": …}``.
    Returns zeros when the model is not recognised.
    """
    try:
        info = litellm.get_model_info(model)
        return {
            "input_cost_per_token": info.get("input_cost_per_token", 0.0) or 0.0,
            "output_cost_per_token": info.get("output_cost_per_token", 0.0) or 0.0,
        }
    except Exception:
        logger.warning("get_model_pricing failed for model={}", model)
        return {"input_cost_per_token": 0.0, "output_cost_per_token": 0.0}


def format_token_count(count: int) -> str:
    """Format a token count for human display.

    Examples: 500 -> "500", 1500 -> "1.5k", 1_000_000 -> "1.0M",
    1_500_000_000 -> "1.5B".
    """
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1000:
        return f"{count / 1000:.1f}k"
    return str(count)
