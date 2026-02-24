"""API endpoint for model pricing and context window information."""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.services.token_service import (
    get_model_context_window,
    get_model_pricing,
    format_token_count,
)

router = APIRouter()


@router.get("/api/model-info")
async def model_info(
    model: str = Query(..., description="Model name (e.g. deepseek/deepseek-chat)"),
):
    """Return pricing and context window info for a model."""
    ctx_window = get_model_context_window(model)
    pricing = get_model_pricing(model)
    return {
        "model": model,
        "max_input_tokens": ctx_window["max_input_tokens"],
        "max_output_tokens": ctx_window["max_output_tokens"],
        "max_input_tokens_display": format_token_count(ctx_window["max_input_tokens"]),
        "input_cost_per_token": pricing["input_cost_per_token"],
        "output_cost_per_token": pricing["output_cost_per_token"],
        "known": ctx_window["max_input_tokens"] > 0,
    }
