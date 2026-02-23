from __future__ import annotations

import ipaddress
from typing import Union
from urllib.parse import urlsplit

from backend.app.core.config import settings


class ApiBaseValidationError(ValueError):
    """Raised when an API base URL violates outbound network policy."""


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _is_private_or_local_ip(ip: IPAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _matches_allowed_hosts(host: str) -> bool:
    allowed = tuple(settings.API_BASE_ALLOWED_HOSTS or [])
    if not allowed:
        return False

    host_l = host.lower()
    for pattern in allowed:
        candidate = str(pattern or "").strip().lower()
        if not candidate:
            continue
        if candidate.startswith("*."):
            suffix = candidate[1:]  # keep leading dot
            if host_l.endswith(suffix) and host_l != candidate[2:]:
                return True
            continue
        if host_l == candidate or host_l.endswith(f".{candidate}"):
            return True
    return False


def ensure_safe_api_base(raw_base: str | None, *, purpose: str) -> str | None:
    """Validate and return a safe API base URL.

    Policy (default):
    - only https scheme
    - no credential in URL
    - deny private/local destinations (IP literal + internal hostnames)
    - optional explicit allow-list via API_BASE_ALLOWED_HOSTS
    """
    if raw_base is None:
        return None
    base = str(raw_base).strip()
    if not base:
        return None

    parsed = urlsplit(base)
    if not parsed.scheme or not parsed.netloc:
        raise ApiBaseValidationError(f"Invalid {purpose} api_base URL")

    scheme = parsed.scheme.lower()
    if scheme not in ("https", "http"):
        raise ApiBaseValidationError(f"Unsupported {purpose} api_base scheme: {scheme}")
    if scheme == "http" and not settings.API_BASE_ALLOW_HTTP:
        raise ApiBaseValidationError(
            f"Insecure {purpose} api_base blocked: only https is allowed"
        )

    if parsed.username or parsed.password:
        raise ApiBaseValidationError(f"Credential in {purpose} api_base URL is not allowed")

    host = parsed.hostname
    if not host:
        raise ApiBaseValidationError(f"Invalid {purpose} api_base host")

    host_l = host.lower()
    if host_l in {"localhost", "localhost.localdomain"} and not settings.API_BASE_ALLOW_PRIVATE_NET:
        raise ApiBaseValidationError(f"Localhost {purpose} api_base is not allowed")

    # Explicit allow-list short-circuit.
    if _matches_allowed_hosts(host_l):
        return base

    if settings.API_BASE_ALLOW_PRIVATE_NET:
        return base

    if _is_ip_literal(host_l):
        ip = ipaddress.ip_address(host_l)
        if _is_private_or_local_ip(ip):
            raise ApiBaseValidationError(
                f"Private/local {purpose} api_base destination is not allowed"
            )
        return base

    # Conservative hostname checks without DNS lookup to avoid false positives
    # in locked-down environments.
    private_suffixes = (".local", ".internal", ".lan", ".home", ".corp")
    if host_l.endswith(private_suffixes):
        raise ApiBaseValidationError(
            f"Private/local {purpose} api_base destination is not allowed"
        )

    return base
