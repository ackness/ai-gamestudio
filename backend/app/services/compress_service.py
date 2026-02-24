"""Compress service — LLM-based history summarization for RPG game sessions.

When the conversation context grows too large relative to the model's token
limit, this service compresses older messages into a concise narrative summary
using a dedicated LLM call.  The summary preserves story-critical details
(NPCs, locations, stats, plot points) so the game can continue seamlessly.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from backend.app.core.llm_config import resolve_llm_config
from backend.app.core.llm_gateway import completion_with_config

_SYSTEM_PROMPT = """\
You are a narrative summarizer for an RPG game session. Your job is to compress
a conversation history into a concise but comprehensive summary that preserves
all information needed to continue the game seamlessly.

Focus on:
- Story background and current narrative arc
- World state changes (doors opened, items obtained, environment shifts)
- NPC relationships and key dialogue outcomes
- Character development (level ups, new abilities, personality shifts)
- Important locations visited and their significance
- Active and resolved plotlines
- Key decisions the player has made and their consequences

Rules:
- Write in the SAME LANGUAGE as the conversation
- Preserve all proper names, numbers, and stats exactly
- Be concise but do not omit any story-critical detail
- Write in third person, past tense
- Structure the summary with clear sections if the content warrants it
- Do NOT add any information that was not in the original conversation\
"""


def should_compress(context_usage: float, threshold: float = 0.7) -> bool:
    """Return True if context usage warrants compression.

    Args:
        context_usage: Fraction of context window used (0.0 to 1.0+).
        threshold: Minimum usage fraction to trigger compression.

    Returns:
        True if context_usage >= threshold AND context_usage > 0.
    """
    return context_usage > 0 and context_usage >= threshold


def build_compression_prompt(
    messages: list[Any],
    existing_summary: str = "",
) -> list[dict[str, str]]:
    """Build the LLM prompt for compressing conversation history.

    Args:
        messages: Message objects with ``.role`` and ``.content`` attributes.
        existing_summary: An earlier summary to incorporate (if any).

    Returns:
        A list of ``{"role": ..., "content": ...}`` dicts ready for the LLM.
    """
    # Format conversation lines
    lines: list[str] = []
    for msg in messages:
        role_label = msg.role.capitalize() if msg.role else "Unknown"
        lines.append(f"[{role_label}]: {msg.content}")

    conversation_text = "\n".join(lines)

    # Build user message
    parts: list[str] = []
    if existing_summary:
        parts.append(
            "Here is the existing summary from earlier in the session:\n"
            "---\n"
            f"{existing_summary}\n"
            "---\n"
        )
        parts.append(
            "Please incorporate the above summary with the new conversation "
            "below into a single unified summary.\n"
        )

    parts.append("Conversation to summarize:\n---\n" + conversation_text + "\n---")

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]


async def compress_history(
    messages_to_compress: list[Any],
    existing_summary: str,
    model: str,
    llm_overrides: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Compress conversation history into a narrative summary via LLM.

    On any error the function falls back to returning the existing summary
    so the caller never crashes.

    Args:
        messages_to_compress: Message objects to summarize.
        existing_summary: Prior summary text to incorporate.
        model: LLM model identifier.
        llm_overrides: Optional dict with ``api_key`` / ``api_base`` overrides.

    Returns:
        ``{"summary": "<compressed text>"}``
    """
    try:
        prompt = build_compression_prompt(messages_to_compress, existing_summary)

        overrides: dict[str, Any] = {"model": model}
        if llm_overrides:
            overrides.update(llm_overrides)

        config = resolve_llm_config(overrides=overrides)
        summary: str = await completion_with_config(  # type: ignore[assignment]
            messages=prompt,
            config=config,
            stream=False,
        )

        logger.info(
            "History compressed: {} messages -> {} chars",
            len(messages_to_compress),
            len(summary),
        )
        return {"summary": summary}

    except Exception:
        logger.exception("Failed to compress history, falling back to existing summary")
        return {"summary": existing_summary}
