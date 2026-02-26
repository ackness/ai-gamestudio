"""Tests for SqlStorageAdapter — KV / Log / Graph operations."""
from __future__ import annotations

import pytest
import pytest_asyncio

from backend.app.adapters.sql_storage import SqlStorageAdapter
from backend.app.core.storage_port import Scope


@pytest_asyncio.fixture
async def storage(db_session, sample_session, sample_project):
    return SqlStorageAdapter(
        db_session,
        session_id=sample_session.id,
        project_id=sample_project.id,
    )


# ── KV (session scope) ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kv_set_and_get(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.SESSION, "test-plugin", "items", "sword", {"name": "Sword", "damage": 10})
    result = await storage.kv_get(Scope.SESSION, "test-plugin", "items", "sword")
    assert result == {"name": "Sword", "damage": 10}


@pytest.mark.asyncio
async def test_kv_get_missing(storage: SqlStorageAdapter):
    result = await storage.kv_get(Scope.SESSION, "test-plugin", "items", "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_kv_set_overwrite(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.SESSION, "ns", "col", "k1", {"v": 1})
    await storage.kv_set(Scope.SESSION, "ns", "col", "k1", {"v": 2})
    result = await storage.kv_get(Scope.SESSION, "ns", "col", "k1")
    assert result == {"v": 2}


@pytest.mark.asyncio
async def test_kv_query(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.SESSION, "ns", "chars", "alice", {"name": "Alice"})
    await storage.kv_set(Scope.SESSION, "ns", "chars", "bob", {"name": "Bob"})
    await storage.kv_set(Scope.SESSION, "ns", "other", "x", {"name": "X"})
    rows = await storage.kv_query(Scope.SESSION, "ns", "chars")
    keys = {r["key"] for r in rows}
    assert keys == {"alice", "bob"}


@pytest.mark.asyncio
async def test_kv_query_filter(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.SESSION, "ns", "items", "iron-sword", {"t": "weapon"})
    await storage.kv_set(Scope.SESSION, "ns", "items", "iron-shield", {"t": "armor"})
    await storage.kv_set(Scope.SESSION, "ns", "items", "potion", {"t": "consumable"})
    rows = await storage.kv_query(Scope.SESSION, "ns", "items", filter_key="iron")
    keys = {r["key"] for r in rows}
    assert keys == {"iron-sword", "iron-shield"}


@pytest.mark.asyncio
async def test_kv_delete(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.SESSION, "ns", "col", "k1", {"v": 1})
    deleted = await storage.kv_delete(Scope.SESSION, "ns", "col", "k1")
    assert deleted is True
    assert await storage.kv_get(Scope.SESSION, "ns", "col", "k1") is None


@pytest.mark.asyncio
async def test_kv_delete_missing(storage: SqlStorageAdapter):
    deleted = await storage.kv_delete(Scope.SESSION, "ns", "col", "nope")
    assert deleted is False


# ── KV (project scope) ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_project_kv_set_and_get(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.PROJECT, "my-plugin", "config", "theme", {"color": "dark"})
    result = await storage.kv_get(Scope.PROJECT, "my-plugin", "config", "theme")
    assert result == {"color": "dark"}


@pytest.mark.asyncio
async def test_project_kv_query(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.PROJECT, "plug", "templates", "t1", {"n": "A"})
    await storage.kv_set(Scope.PROJECT, "plug", "templates", "t2", {"n": "B"})
    rows = await storage.kv_query(Scope.PROJECT, "plug", "templates")
    keys = {r["key"] for r in rows}
    assert keys == {"t1", "t2"}


@pytest.mark.asyncio
async def test_project_kv_delete(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.PROJECT, "plug", "cfg", "k", {"v": 1})
    deleted = await storage.kv_delete(Scope.PROJECT, "plug", "cfg", "k")
    assert deleted is True
    assert await storage.kv_get(Scope.PROJECT, "plug", "cfg", "k") is None


# ── Log ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_append_and_query(storage: SqlStorageAdapter):
    await storage.log_append(Scope.SESSION, "combat", "combat-log", {"action": "attack", "dmg": 5})
    await storage.log_append(Scope.SESSION, "combat", "combat-log", {"action": "defend", "dmg": 0})
    rows = await storage.log_query(Scope.SESSION, "combat", "combat-log", limit=10)
    assert len(rows) == 2
    assert rows[0]["action"] == "attack"
    assert rows[1]["action"] == "defend"


@pytest.mark.asyncio
async def test_log_query_limit(storage: SqlStorageAdapter):
    for i in range(5):
        await storage.log_append(Scope.SESSION, "ns", "log", {"i": i})
    rows = await storage.log_query(Scope.SESSION, "ns", "log", limit=3)
    assert len(rows) == 3


# ── Graph ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_add_and_query(storage: SqlStorageAdapter):
    await storage.graph_add(Scope.SESSION, "ns", "alice", "bob", "knows", {"since": "2024"})
    edges = await storage.graph_query(Scope.SESSION, "ns", from_id="alice")
    assert len(edges) == 1
    assert edges[0]["to_id"] == "bob"
    assert edges[0]["relation"] == "knows"
    assert edges[0]["data"]["since"] == "2024"


@pytest.mark.asyncio
async def test_graph_query_by_relation(storage: SqlStorageAdapter):
    await storage.graph_add(Scope.SESSION, "ns", "a", "b", "friend")
    await storage.graph_add(Scope.SESSION, "ns", "a", "c", "enemy")
    edges = await storage.graph_query(Scope.SESSION, "ns", relation="enemy")
    assert len(edges) == 1
    assert edges[0]["to_id"] == "c"


@pytest.mark.asyncio
async def test_graph_delete(storage: SqlStorageAdapter):
    await storage.graph_add(Scope.SESSION, "ns", "x", "y", "rel")
    deleted = await storage.graph_delete(Scope.SESSION, "ns", "x", "y", "rel")
    assert deleted is True
    edges = await storage.graph_query(Scope.SESSION, "ns", from_id="x")
    assert len(edges) == 0


@pytest.mark.asyncio
async def test_graph_delete_missing(storage: SqlStorageAdapter):
    deleted = await storage.graph_delete(Scope.SESSION, "ns", "no", "no", "no")
    assert deleted is False


# ── Snapshot ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_state_snapshot(storage: SqlStorageAdapter):
    await storage.kv_set(Scope.SESSION, "ns", "chars", "hero", {"name": "Hero"})
    await storage.graph_add(Scope.SESSION, "ns", "hero", "villain", "enemy")
    snap = await storage.build_state_snapshot(Scope.SESSION)
    assert "chars" in snap["kv"]
    assert snap["kv"]["chars"]["hero"]["name"] == "Hero"
    assert len(snap["graph"]) == 1


# ── Error cases ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_scope_requires_session_id(db_session, sample_project):
    storage = SqlStorageAdapter(db_session, project_id=sample_project.id)
    with pytest.raises(ValueError, match="session_id required"):
        await storage.kv_get(Scope.SESSION, "ns", "col", "k")


@pytest.mark.asyncio
async def test_project_scope_requires_project_id(db_session, sample_session):
    storage = SqlStorageAdapter(db_session, session_id=sample_session.id)
    with pytest.raises(ValueError, match="project_id required"):
        await storage.kv_get(Scope.PROJECT, "ns", "col", "k")
