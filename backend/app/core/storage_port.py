"""StoragePort — unified storage abstraction for KV / Log / Graph primitives.

All game data access (plugins, core entities, settings) goes through this
interface.  Backend uses SqlStorageAdapter; frontend mirrors the same contract
with ApiStorageAdapter / IdbStorageAdapter.
"""

from __future__ import annotations

import enum
from typing import Any, Protocol, runtime_checkable


class Scope(str, enum.Enum):
    SESSION = "session"
    PROJECT = "project"
    LOCAL = "local"
    GLOBAL = "global"


@runtime_checkable
class StoragePort(Protocol):
    """Unified storage interface implemented by each adapter."""

    # ── KV ────────────────────────────────────────────────────────────────

    async def kv_get(
        self, scope: Scope, ns: str, collection: str, key: str,
    ) -> dict | None: ...

    async def kv_set(
        self, scope: Scope, ns: str, collection: str, key: str, value: Any,
    ) -> None: ...

    async def kv_query(
        self, scope: Scope, ns: str, collection: str,
        *, filter_key: str | None = None,
    ) -> list[dict]: ...

    async def kv_delete(
        self, scope: Scope, ns: str, collection: str, key: str,
    ) -> bool: ...

    # ── Log ───────────────────────────────────────────────────────────────

    async def log_append(
        self, scope: Scope, ns: str, collection: str, entry: Any,
    ) -> None: ...

    async def log_query(
        self, scope: Scope, ns: str, collection: str,
        *, limit: int = 50, offset: int = 0,
    ) -> list[dict]: ...

    # ── Graph ─────────────────────────────────────────────────────────────

    async def graph_add(
        self, scope: Scope, ns: str,
        from_id: str, to_id: str, relation: str,
        data: dict | None = None,
    ) -> None: ...

    async def graph_query(
        self, scope: Scope, ns: str,
        from_id: str | None = None, relation: str | None = None,
    ) -> list[dict]: ...

    async def graph_delete(
        self, scope: Scope, ns: str,
        from_id: str, to_id: str, relation: str,
    ) -> bool: ...

    # ── Bulk ──────────────────────────────────────────────────────────────

    async def build_state_snapshot(
        self, scope: Scope, ns: str | None = None,
    ) -> dict:
        """Build a compact state snapshot (KV collections + graph edges)."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def flush(self) -> None:
        """Commit any deferred writes."""
        ...
