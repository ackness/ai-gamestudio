"""Tests for token_service — token counting, cost calculation, and model info."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.services.token_service import (
    TokenUsage,
    calculate_turn_cost,
    count_message_tokens,
    format_token_count,
    get_model_context_window,
    get_model_pricing,
)


# ---------------------------------------------------------------------------
# count_message_tokens
# ---------------------------------------------------------------------------

def test_count_message_tokens_returns_int():
    """token_counter returns an int count when litellm succeeds."""
    messages = [{"role": "user", "content": "Hello world"}]
    with patch("backend.app.services.token_service.litellm") as mock_litellm:
        mock_litellm.token_counter.return_value = 42
        result = count_message_tokens("deepseek/deepseek-chat", messages)
    assert result == 42
    assert isinstance(result, int)
    mock_litellm.token_counter.assert_called_once_with(
        model="deepseek/deepseek-chat", messages=messages
    )


def test_count_message_tokens_fallback_on_error():
    """Falls back to chars/4 estimate when litellm raises."""
    messages = [
        {"role": "user", "content": "A" * 100},
        {"role": "assistant", "content": "B" * 200},
    ]
    with patch("backend.app.services.token_service.litellm") as mock_litellm:
        mock_litellm.token_counter.side_effect = Exception("tokenizer unavailable")
        result = count_message_tokens("unknown/model", messages)
    # Total chars = 100 + 200 = 300, fallback = 300 / 4 = 75
    assert result == 75
    assert isinstance(result, int)


# ---------------------------------------------------------------------------
# get_model_context_window
# ---------------------------------------------------------------------------

def test_get_model_context_window_known_model():
    """Returns max_input_tokens and max_output_tokens from litellm model info."""
    with patch("backend.app.services.token_service.litellm") as mock_litellm:
        mock_litellm.get_model_info.return_value = {
            "max_input_tokens": 131072,
            "max_output_tokens": 8192,
        }
        result = get_model_context_window("deepseek/deepseek-chat")
    assert result == {"max_input_tokens": 131072, "max_output_tokens": 8192}


def test_get_model_context_window_unknown_model():
    """Returns zeros when litellm cannot find model info."""
    with patch("backend.app.services.token_service.litellm") as mock_litellm:
        mock_litellm.get_model_info.side_effect = Exception("model not found")
        result = get_model_context_window("unknown/model")
    assert result == {"max_input_tokens": 0, "max_output_tokens": 0}


# ---------------------------------------------------------------------------
# calculate_turn_cost
# ---------------------------------------------------------------------------

def test_calculate_turn_cost():
    """Returns total cost (prompt + completion) for known model."""
    with patch("backend.app.services.token_service.litellm") as mock_litellm:
        # cost_per_token returns (prompt_cost, completion_cost)
        mock_litellm.cost_per_token.return_value = (0.00028, 0.00021)
        result = calculate_turn_cost("deepseek/deepseek-chat", 1000, 500)
    assert result == pytest.approx(0.00049)
    mock_litellm.cost_per_token.assert_called_once_with(
        model="deepseek/deepseek-chat",
        prompt_tokens=1000,
        completion_tokens=500,
    )


def test_calculate_turn_cost_unknown_model():
    """Returns 0.0 when litellm raises for unknown model."""
    with patch("backend.app.services.token_service.litellm") as mock_litellm:
        mock_litellm.cost_per_token.side_effect = Exception("unknown model")
        result = calculate_turn_cost("unknown/model", 1000, 500)
    assert result == 0.0


# ---------------------------------------------------------------------------
# get_model_pricing
# ---------------------------------------------------------------------------

def test_get_model_pricing():
    """Returns per-token pricing from litellm model info."""
    with patch("backend.app.services.token_service.litellm") as mock_litellm:
        mock_litellm.get_model_info.return_value = {
            "input_cost_per_token": 2.8e-07,
            "output_cost_per_token": 4.2e-07,
        }
        result = get_model_pricing("deepseek/deepseek-chat")
    assert result == {
        "input_cost_per_token": 2.8e-07,
        "output_cost_per_token": 4.2e-07,
    }


def test_get_model_pricing_unknown_model():
    """Returns zeros when model is not found."""
    with patch("backend.app.services.token_service.litellm") as mock_litellm:
        mock_litellm.get_model_info.side_effect = Exception("not found")
        result = get_model_pricing("unknown/model")
    assert result == {"input_cost_per_token": 0.0, "output_cost_per_token": 0.0}


# ---------------------------------------------------------------------------
# format_token_count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "count,expected",
    [
        (0, "0"),
        (500, "500"),
        (999, "999"),
        (1000, "1.0k"),
        (1500, "1.5k"),
        (10000, "10.0k"),
        (999999, "1000.0k"),
        (1000000, "1.0M"),
        (1500000, "1.5M"),
        (1500000000, "1.5B"),
    ],
)
def test_format_token_count(count: int, expected: str):
    assert format_token_count(count) == expected


# ---------------------------------------------------------------------------
# TokenUsage dataclass
# ---------------------------------------------------------------------------

def test_token_usage_dataclass():
    """TokenUsage stores all token/cost fields and computes totals."""
    usage = TokenUsage(
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        prompt_cost=0.00028,
        completion_cost=0.00021,
        total_cost=0.00049,
    )
    assert usage.prompt_tokens == 1000
    assert usage.completion_tokens == 500
    assert usage.total_tokens == 1500
    assert usage.prompt_cost == pytest.approx(0.00028)
    assert usage.completion_cost == pytest.approx(0.00021)
    assert usage.total_cost == pytest.approx(0.00049)


def test_token_usage_defaults():
    """TokenUsage fields default to zero."""
    usage = TokenUsage()
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0
    assert usage.prompt_cost == 0.0
    assert usage.completion_cost == 0.0
    assert usage.total_cost == 0.0
