from __future__ import annotations

import copy
import json
from typing import Any

from loguru import logger


def safe_json_loads(
    raw: str | bytes | bytearray | None,
    *,
    fallback: Any = None,
    context: str = "json",
) -> Any:
    """Best-effort JSON decode with bounded logging and safe fallback."""
    if raw is None:
        return copy.deepcopy(fallback)

    try:
        return json.loads(raw)
    except Exception:
        preview = str(raw)
        if len(preview) > 200:
            preview = preview[:200] + "..."
        logger.warning("Invalid JSON in {}: {}", context, preview)
        return copy.deepcopy(fallback)

