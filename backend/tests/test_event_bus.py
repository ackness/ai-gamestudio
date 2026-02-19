"""Tests for PluginEventBus."""
from __future__ import annotations

import pytest

from backend.app.core.event_bus import PluginEventBus


class TestPluginEventBus:
    @pytest.mark.asyncio
    async def test_emit_and_drain_calls_listener(self):
        bus = PluginEventBus()
        results: list[dict] = []

        async def listener(data, context):
            results.append(data)

        bus.register("test-event", listener)
        bus.emit("test-event", {"value": 42})

        await bus.drain(None)  # type: ignore[arg-type]
        assert len(results) == 1
        assert results[0]["value"] == 42

    @pytest.mark.asyncio
    async def test_no_listeners_doesnt_error(self):
        bus = PluginEventBus()
        bus.emit("unheard-event", {"x": 1})

        await bus.drain(None)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_multiple_listeners_all_called(self):
        bus = PluginEventBus()
        results: list[str] = []

        async def listener_a(data, context):
            results.append("a")

        async def listener_b(data, context):
            results.append("b")

        bus.register("evt", listener_a)
        bus.register("evt", listener_b)
        bus.emit("evt", {})

        await bus.drain(None)  # type: ignore[arg-type]
        assert "a" in results
        assert "b" in results

    @pytest.mark.asyncio
    async def test_events_emitted_during_drain_are_processed(self):
        bus = PluginEventBus()
        results: list[str] = []

        async def chain_listener(data, context):
            results.append("chain")
            if data.get("chain"):
                bus.emit("chained", {"chain": False})

        async def final_listener(data, context):
            results.append("final")

        bus.register("start", chain_listener)
        bus.register("chained", final_listener)
        bus.emit("start", {"chain": True})

        await bus.drain(None)  # type: ignore[arg-type]
        assert "chain" in results
        assert "final" in results
