"""Parse and apply search/replace edit blocks from LLM output."""
from __future__ import annotations

import re
from dataclasses import dataclass

BLOCK_RE = re.compile(
    r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE",
    re.DOTALL,
)


@dataclass
class Edit:
    old_text: str
    new_text: str


def parse_edits(llm_output: str) -> list[Edit]:
    return [Edit(m.group(1), m.group(2)) for m in BLOCK_RE.finditer(llm_output)]


def apply_edits(original: str, edits: list[Edit]) -> tuple[str, list[Edit]]:
    """Apply edits sequentially. Returns (result, applied_edits)."""
    result = original
    applied: list[Edit] = []
    for edit in edits:
        # Try exact match first, then stripped match as fallback
        idx = result.find(edit.old_text)
        if idx == -1:
            stripped = edit.old_text.strip()
            idx = result.find(stripped)
            if idx == -1:
                continue
            result = result[:idx] + edit.new_text + result[idx + len(stripped):]
        else:
            result = result[:idx] + edit.new_text + result[idx + len(edit.old_text):]
        applied.append(edit)
    return result, applied


def is_search_replace(text: str) -> bool:
    return bool(BLOCK_RE.search(text))
