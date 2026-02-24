from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.models.game_graph import GameGraph
from backend.app.models.game_kv import GameKV
from backend.app.models.game_log import GameLog


class GameDB:
    """Game state storage layer: KV, Graph, Log primitives."""

    def __init__(self, db: AsyncSession, session_id: str) -> None:
        self.db = db
        self.session_id = session_id

    # ── KV ──

    async def kv_get(self, collection: str, key: str) -> dict | None:
        stmt = select(GameKV).where(
            GameKV.session_id == self.session_id,
            GameKV.collection == collection,
            GameKV.key == key,
        )
        row = (await self.db.exec(stmt)).first()
        return json.loads(row.value_json) if row else None

    async def kv_set(self, collection: str, key: str, value: Any) -> None:
        stmt = select(GameKV).where(
            GameKV.session_id == self.session_id,
            GameKV.collection == collection,
            GameKV.key == key,
        )
        row = (await self.db.exec(stmt)).first()
        now = datetime.now(timezone.utc)
        if row:
            row.value_json = json.dumps(value, ensure_ascii=False)
            row.updated_at = now
            self.db.add(row)
        else:
            self.db.add(GameKV(
                session_id=self.session_id,
                collection=collection,
                key=key,
                value_json=json.dumps(value, ensure_ascii=False),
                updated_at=now,
            ))
        await self.db.commit()

    async def kv_query(self, collection: str, filter_key: str | None = None) -> list[dict]:
        stmt = select(GameKV).where(
            GameKV.session_id == self.session_id,
            GameKV.collection == collection,
        )
        if filter_key:
            stmt = stmt.where(GameKV.key.contains(filter_key))
        rows = (await self.db.exec(stmt)).all()
        return [{"key": r.key, "value": json.loads(r.value_json)} for r in rows]

    async def kv_delete(self, collection: str, key: str) -> bool:
        stmt = select(GameKV).where(
            GameKV.session_id == self.session_id,
            GameKV.collection == collection,
            GameKV.key == key,
        )
        row = (await self.db.exec(stmt)).first()
        if not row:
            return False
        await self.db.delete(row)
        await self.db.commit()
        return True

    # ── Graph ──

    async def graph_add(
        self, from_id: str, to_id: str, relation: str, data: dict | None = None
    ) -> None:
        stmt = select(GameGraph).where(
            GameGraph.session_id == self.session_id,
            GameGraph.from_id == from_id,
            GameGraph.to_id == to_id,
            GameGraph.relation == relation,
        )
        row = (await self.db.exec(stmt)).first()
        if row:
            row.data_json = json.dumps(data or {}, ensure_ascii=False)
            self.db.add(row)
        else:
            self.db.add(GameGraph(
                session_id=self.session_id,
                from_id=from_id,
                to_id=to_id,
                relation=relation,
                data_json=json.dumps(data or {}, ensure_ascii=False),
            ))
        await self.db.commit()

    async def graph_remove(self, from_id: str, to_id: str, relation: str) -> bool:
        stmt = select(GameGraph).where(
            GameGraph.session_id == self.session_id,
            GameGraph.from_id == from_id,
            GameGraph.to_id == to_id,
            GameGraph.relation == relation,
        )
        row = (await self.db.exec(stmt)).first()
        if not row:
            return False
        await self.db.delete(row)
        await self.db.commit()
        return True

    async def graph_query(
        self,
        node_id: str | None = None,
        relation: str | None = None,
        direction: str = "both",
    ) -> list[dict]:
        stmt = select(GameGraph).where(GameGraph.session_id == self.session_id)
        if relation:
            stmt = stmt.where(GameGraph.relation == relation)
        if node_id:
            if direction == "out":
                stmt = stmt.where(GameGraph.from_id == node_id)
            elif direction == "in":
                stmt = stmt.where(GameGraph.to_id == node_id)
            else:
                stmt = stmt.where(
                    (GameGraph.from_id == node_id) | (GameGraph.to_id == node_id)
                )
        rows = (await self.db.exec(stmt)).all()
        return [
            {
                "from_id": r.from_id,
                "to_id": r.to_id,
                "relation": r.relation,
                "data": json.loads(r.data_json) if r.data_json else {},
            }
            for r in rows
        ]

    # ── Log ──

    async def log_append(self, collection: str, entry: dict) -> None:
        self.db.add(GameLog(
            session_id=self.session_id,
            collection=collection,
            entry_json=json.dumps(entry, ensure_ascii=False),
        ))
        await self.db.commit()

    async def log_query(
        self, collection: str, limit: int = 10, since: str | None = None
    ) -> list[dict]:
        stmt = (
            select(GameLog)
            .where(
                GameLog.session_id == self.session_id,
                GameLog.collection == collection,
            )
            .order_by(GameLog.created_at.desc())  # type: ignore[union-attr]
            .limit(limit)
        )
        if since:
            stmt = stmt.where(GameLog.created_at >= datetime.fromisoformat(since))
        rows = (await self.db.exec(stmt)).all()
        rows.reverse()
        return [json.loads(r.entry_json) for r in rows]

    # ── Snapshot ──

    async def build_state_snapshot(self) -> dict:
        """Build a compact state snapshot for Plugin Agent context."""
        kv_stmt = select(GameKV).where(GameKV.session_id == self.session_id)
        kv_rows = (await self.db.exec(kv_stmt)).all()
        collections: dict[str, dict] = {}
        for r in kv_rows:
            collections.setdefault(r.collection, {})[r.key] = json.loads(r.value_json)

        graph_stmt = select(GameGraph).where(GameGraph.session_id == self.session_id)
        graph_rows = (await self.db.exec(graph_stmt)).all()
        edges = [
            {"from": r.from_id, "to": r.to_id, "rel": r.relation}
            for r in graph_rows
        ]

        return {"kv": collections, "graph": edges}
