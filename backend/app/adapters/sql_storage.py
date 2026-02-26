"""SqlStorageAdapter — StoragePort implementation backed by SQLModel tables.

Session scope  → StorageKV / StorageLog / StorageGraph (keyed by session_id)
Project scope  → PluginStorage (keyed by project_id + plugin_name)

The adapter receives context ids (session_id, project_id) at construction time
so callers don't need to pass them on every operation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.json_utils import safe_json_loads
from backend.app.core.storage_port import Scope
from backend.app.models.game_graph import StorageGraph
from backend.app.models.game_kv import StorageKV
from backend.app.models.game_log import StorageLog
from backend.app.models.plugin_storage import PluginStorage


class SqlStorageAdapter:
    """StoragePort implementation using SQL tables."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        session_id: str | None = None,
        project_id: str | None = None,
        autocommit: bool = True,
    ) -> None:
        self.db = db
        self.session_id = session_id
        self.project_id = project_id
        self.autocommit = autocommit

    # ── helpers ────────────────────────────────────────────────────────────

    def _require_session(self, scope: Scope) -> str:
        if scope == Scope.SESSION:
            if not self.session_id:
                raise ValueError("session_id required for SESSION scope")
            return self.session_id
        raise ValueError(f"unexpected scope {scope} in _require_session")

    def _require_project(self, scope: Scope) -> str:
        if scope == Scope.PROJECT:
            if not self.project_id:
                raise ValueError("project_id required for PROJECT scope")
            return self.project_id
        raise ValueError(f"unexpected scope {scope} in _require_project")

    async def _maybe_commit(self) -> None:
        if self.autocommit:
            await self.db.commit()

    async def flush(self) -> None:
        await self.db.commit()

    # ── KV (session scope) ────────────────────────────────────────────────

    async def _session_kv_get(self, sid: str, collection: str, key: str) -> dict | None:
        stmt = select(StorageKV).where(
            StorageKV.session_id == sid,
            StorageKV.collection == collection,
            StorageKV.key == key,
        )
        row = (await self.db.exec(stmt)).first()
        if not row:
            return None
        return safe_json_loads(
            row.value_json, fallback=None,
            context=f"StorageKV get ({sid}/{collection}/{key})",
        )

    async def _session_kv_set(self, sid: str, collection: str, key: str, value: Any) -> None:
        stmt = select(StorageKV).where(
            StorageKV.session_id == sid,
            StorageKV.collection == collection,
            StorageKV.key == key,
        )
        row = (await self.db.exec(stmt)).first()
        now = datetime.now(timezone.utc)
        dumped = json.dumps(value, ensure_ascii=False)
        if row:
            row.value_json = dumped
            row.updated_at = now
            self.db.add(row)
        else:
            self.db.add(StorageKV(
                session_id=sid, collection=collection,
                key=key, value_json=dumped, updated_at=now,
            ))
        await self._maybe_commit()

    async def _session_kv_query(
        self, sid: str, collection: str, filter_key: str | None = None,
    ) -> list[dict]:
        stmt = select(StorageKV).where(
            StorageKV.session_id == sid,
            StorageKV.collection == collection,
        )
        if filter_key:
            stmt = stmt.where(StorageKV.key.contains(filter_key))
        rows = (await self.db.exec(stmt)).all()
        return [
            {
                "key": r.key,
                "value": safe_json_loads(
                    r.value_json, fallback=None,
                    context=f"StorageKV query ({sid}/{collection}/{r.key})",
                ),
            }
            for r in rows
        ]

    async def _session_kv_delete(self, sid: str, collection: str, key: str) -> bool:
        stmt = select(StorageKV).where(
            StorageKV.session_id == sid,
            StorageKV.collection == collection,
            StorageKV.key == key,
        )
        row = (await self.db.exec(stmt)).first()
        if not row:
            return False
        await self.db.delete(row)
        await self._maybe_commit()
        return True

    # ── KV (project scope via PluginStorage) ──────────────────────────────

    async def _project_kv_get(self, pid: str, ns: str, key: str) -> dict | None:
        collection_key = f"{ns}:{key}"
        stmt = select(PluginStorage).where(
            PluginStorage.project_id == pid,
            PluginStorage.plugin_name == ns,
            PluginStorage.key == collection_key,
        )
        row = (await self.db.exec(stmt)).first()
        if not row:
            return None
        return safe_json_loads(
            row.value_json, fallback=None,
            context=f"PluginStorage get ({pid}/{ns}/{key})",
        )

    async def _project_kv_set(self, pid: str, ns: str, key: str, value: Any) -> None:
        collection_key = f"{ns}:{key}"
        stmt = select(PluginStorage).where(
            PluginStorage.project_id == pid,
            PluginStorage.plugin_name == ns,
            PluginStorage.key == collection_key,
        )
        row = (await self.db.exec(stmt)).first()
        dumped = json.dumps(value, ensure_ascii=False)
        if row:
            row.value_json = dumped
            self.db.add(row)
        else:
            self.db.add(PluginStorage(
                project_id=pid, plugin_name=ns,
                key=collection_key, value_json=dumped,
            ))
        await self._maybe_commit()

    async def _project_kv_query(
        self, pid: str, ns: str, filter_key: str | None = None,
    ) -> list[dict]:
        prefix = f"{ns}:"
        stmt = select(PluginStorage).where(
            PluginStorage.project_id == pid,
            PluginStorage.plugin_name == ns,
            PluginStorage.key.startswith(prefix),
        )
        if filter_key:
            stmt = stmt.where(PluginStorage.key.contains(filter_key))
        rows = (await self.db.exec(stmt)).all()
        return [
            {
                "key": r.key.removeprefix(prefix),
                "value": safe_json_loads(
                    r.value_json, fallback=None,
                    context=f"PluginStorage query ({pid}/{ns}/{r.key})",
                ),
            }
            for r in rows
        ]

    async def _project_kv_delete(self, pid: str, ns: str, key: str) -> bool:
        collection_key = f"{ns}:{key}"
        stmt = select(PluginStorage).where(
            PluginStorage.project_id == pid,
            PluginStorage.plugin_name == ns,
            PluginStorage.key == collection_key,
        )
        row = (await self.db.exec(stmt)).first()
        if not row:
            return False
        await self.db.delete(row)
        await self._maybe_commit()
        return True

    # ── Public KV (scope router) ──────────────────────────────────────────

    async def kv_get(
        self, scope: Scope, ns: str, collection: str, key: str,
    ) -> dict | None:
        if scope == Scope.SESSION:
            sid = self._require_session(scope)
            return await self._session_kv_get(sid, collection, key)
        if scope == Scope.PROJECT:
            pid = self._require_project(scope)
            return await self._project_kv_get(pid, ns, key)
        raise ValueError(f"unsupported scope {scope} for SQL adapter")

    async def kv_set(
        self, scope: Scope, ns: str, collection: str, key: str, value: Any,
    ) -> None:
        if scope == Scope.SESSION:
            sid = self._require_session(scope)
            await self._session_kv_set(sid, collection, key, value)
            return
        if scope == Scope.PROJECT:
            pid = self._require_project(scope)
            await self._project_kv_set(pid, ns, key, value)
            return
        raise ValueError(f"unsupported scope {scope} for SQL adapter")

    async def kv_query(
        self, scope: Scope, ns: str, collection: str,
        *, filter_key: str | None = None,
    ) -> list[dict]:
        if scope == Scope.SESSION:
            sid = self._require_session(scope)
            return await self._session_kv_query(sid, collection, filter_key)
        if scope == Scope.PROJECT:
            pid = self._require_project(scope)
            return await self._project_kv_query(pid, ns, filter_key)
        raise ValueError(f"unsupported scope {scope} for SQL adapter")

    async def kv_delete(
        self, scope: Scope, ns: str, collection: str, key: str,
    ) -> bool:
        if scope == Scope.SESSION:
            sid = self._require_session(scope)
            return await self._session_kv_delete(sid, collection, key)
        if scope == Scope.PROJECT:
            pid = self._require_project(scope)
            return await self._project_kv_delete(pid, ns, key)
        raise ValueError(f"unsupported scope {scope} for SQL adapter")

    # ── Log (session scope only) ──────────────────────────────────────────

    async def log_append(
        self, scope: Scope, ns: str, collection: str, entry: Any,
    ) -> None:
        sid = self._require_session(scope)
        self.db.add(StorageLog(
            session_id=sid,
            collection=collection,
            entry_json=json.dumps(entry, ensure_ascii=False),
        ))
        await self._maybe_commit()

    async def log_query(
        self, scope: Scope, ns: str, collection: str,
        *, limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        sid = self._require_session(scope)
        stmt = (
            select(StorageLog)
            .where(
                StorageLog.session_id == sid,
                StorageLog.collection == collection,
            )
            .order_by(StorageLog.created_at.desc())  # type: ignore[union-attr]
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.exec(stmt)).all()
        rows.reverse()
        return [
            safe_json_loads(
                r.entry_json, fallback={},
                context=f"StorageLog entry ({sid}/{collection})",
            )
            for r in rows
        ]

    # ── Graph (session scope only) ────────────────────────────────────────

    async def graph_add(
        self, scope: Scope, ns: str,
        from_id: str, to_id: str, relation: str,
        data: dict | None = None,
    ) -> None:
        sid = self._require_session(scope)
        stmt = select(StorageGraph).where(
            StorageGraph.session_id == sid,
            StorageGraph.from_id == from_id,
            StorageGraph.to_id == to_id,
            StorageGraph.relation == relation,
        )
        row = (await self.db.exec(stmt)).first()
        dumped = json.dumps(data or {}, ensure_ascii=False)
        if row:
            row.data_json = dumped
            self.db.add(row)
        else:
            self.db.add(StorageGraph(
                session_id=sid, from_id=from_id,
                to_id=to_id, relation=relation, data_json=dumped,
            ))
        await self._maybe_commit()

    async def graph_query(
        self, scope: Scope, ns: str,
        from_id: str | None = None, relation: str | None = None,
    ) -> list[dict]:
        sid = self._require_session(scope)
        stmt = select(StorageGraph).where(StorageGraph.session_id == sid)
        if relation:
            stmt = stmt.where(StorageGraph.relation == relation)
        if from_id:
            stmt = stmt.where(
                (StorageGraph.from_id == from_id) | (StorageGraph.to_id == from_id),
            )
        rows = (await self.db.exec(stmt)).all()
        return [
            {
                "from_id": r.from_id,
                "to_id": r.to_id,
                "relation": r.relation,
                "data": safe_json_loads(
                    r.data_json, fallback={},
                    context=f"StorageGraph ({sid}/{r.from_id}->{r.to_id})",
                ) if r.data_json else {},
            }
            for r in rows
        ]

    async def graph_delete(
        self, scope: Scope, ns: str,
        from_id: str, to_id: str, relation: str,
    ) -> bool:
        sid = self._require_session(scope)
        stmt = select(StorageGraph).where(
            StorageGraph.session_id == sid,
            StorageGraph.from_id == from_id,
            StorageGraph.to_id == to_id,
            StorageGraph.relation == relation,
        )
        row = (await self.db.exec(stmt)).first()
        if not row:
            return False
        await self.db.delete(row)
        await self._maybe_commit()
        return True

    # ── Snapshot ──────────────────────────────────────────────────────────

    async def build_state_snapshot(
        self, scope: Scope, ns: str | None = None,
    ) -> dict:
        sid = self._require_session(scope)
        kv_stmt = select(StorageKV).where(StorageKV.session_id == sid)
        kv_rows = (await self.db.exec(kv_stmt)).all()
        collections: dict[str, dict] = {}
        for r in kv_rows:
            collections.setdefault(r.collection, {})[r.key] = safe_json_loads(
                r.value_json, fallback=None,
                context=f"StorageKV snapshot ({sid}/{r.collection}/{r.key})",
            )

        graph_stmt = select(StorageGraph).where(StorageGraph.session_id == sid)
        graph_rows = (await self.db.exec(graph_stmt)).all()
        edges = [
            {"from": r.from_id, "to": r.to_id, "rel": r.relation}
            for r in graph_rows
        ]

        return {"kv": collections, "graph": edges}
