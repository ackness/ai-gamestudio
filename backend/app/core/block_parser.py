"""Generic ``json:xxx`` code-block parser.

LLM responses may contain fenced blocks like::

    ```json:state_update
    {"characters": [...]}
    ```

Some weaker models omit the fences and produce::

    json:state_update
    {"characters": [...]}

This module extracts *all* such blocks into a uniform structure so the
framework doesn't need per-type regexes.
"""

from __future__ import annotations

import json
import re

from loguru import logger

# Strict: ```json:type ... ```
BLOCK_RE = re.compile(r"```json:\s*([\w-]+)\s*\n(.*?)```", re.DOTALL)

# Loose marker: "json:type" on its own line, possibly preceded by markdown
# heading (### json:type) and optionally followed by a ```json fence.
_MARKER_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:#{1,6}\s+)?json:\s*([\w-]+)[ \t]*\n"
    r"(?:[ \t]*```(?:json)?[ \t]*\n)?",
)


def _find_json_object(text: str, start: int) -> tuple[str, int, int] | None:
    """From *start*, skip whitespace and extract a balanced ``{...}`` object.

    Returns ``(body, begin, end)`` where *begin*/*end* are indices into *text*,
    or ``None`` if no valid object is found.
    """
    i = start
    while i < len(text) and text[i] in " \t\n\r":
        i += 1
    if i >= len(text) or text[i] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for j in range(i, len(text)):
        ch = text[j]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1], i, j + 1
    return None


def extract_blocks(text: str) -> list[dict]:
    """Return every ``json:<type>`` block found in *text*.

    Each item is ``{"type": "<block_type>", "data": <parsed>, "raw": "<match>"}``
    where *raw* is the full matched string (including fences / markers) for
    later stripping.  Blocks whose JSON body fails to parse are silently
    skipped.

    Extraction runs in two passes:
      1. **Strict** — properly fenced `` ```json:type ... ``` `` blocks.
      2. **Loose** (fallback) — bare ``json:type`` markers followed by a JSON
         object, for models that omit the triple-backtick fences.
    """
    results: list[dict] = []
    matched_spans: list[tuple[int, int]] = []

    # --- Pass 1: strict fenced blocks ---
    for m in BLOCK_RE.finditer(text):
        block_type = m.group(1)
        body = m.group(2).strip()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed json:{} block", block_type)
            continue
        results.append({"type": block_type, "data": data, "raw": m.group(0)})
        matched_spans.append((m.start(), m.end()))

    # --- Pass 2: loose markers (fallback) ---
    for m in _MARKER_RE.finditer(text):
        # Skip if this region overlaps with a strict match
        if any(s <= m.start() < e for s, e in matched_spans):
            continue

        block_type = m.group(1)
        found = _find_json_object(text, m.end())
        if not found:
            continue
        body_str, _body_start, body_end = found
        try:
            data = json.loads(body_str)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed loose json:{} block", block_type)
            continue

        # Consume optional trailing ``` fence
        raw_end = body_end
        rest = text[raw_end:].lstrip(" \t")
        if rest.startswith("```"):
            raw_end = text.index("```", raw_end) + 3

        raw_start = m.start() + 1 if text[m.start()] == "\n" else m.start()
        raw = text[raw_start:raw_end]
        results.append({"type": block_type, "data": data, "raw": raw})
        matched_spans.append((raw_start, raw_end))

    return results


def strip_blocks(text: str) -> str:
    """Remove all ``json:xxx`` blocks (fenced and loose) from *text*."""
    blocks = extract_blocks(text)
    for block in blocks:
        text = text.replace(block["raw"], "", 1)
    return text.strip()
