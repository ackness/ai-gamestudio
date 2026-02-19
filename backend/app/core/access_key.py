from __future__ import annotations

import secrets
from collections.abc import Mapping

from backend.app.core.config import settings


def _expected_access_key() -> str:
    return str(settings.ACCESS_KEY or "").strip()


def access_key_required() -> bool:
    return bool(_expected_access_key())


def _header_access_key(headers: Mapping[str, str]) -> str:
    # Header names are case-insensitive in ASGI implementations.
    return str(headers.get("X-Access-Key") or headers.get("x-access-key") or "").strip()


def _query_access_key(query_params: Mapping[str, str] | None) -> str:
    if not query_params:
        return ""
    return str(
        query_params.get("access_key")
        or query_params.get("x_access_key")
        or query_params.get("x-access-key")
        or ""
    ).strip()


def is_request_authorized(
    headers: Mapping[str, str],
    query_params: Mapping[str, str] | None = None,
) -> bool:
    expected = _expected_access_key()
    if not expected:
        return True

    provided = _header_access_key(headers) or _query_access_key(query_params)
    if not provided:
        return False

    return secrets.compare_digest(provided, expected)
