"""Request-scoped plugin event bus for inter-plugin communication."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from loguru import logger

if TYPE_CHECKING:
    from backend.app.core.block_handlers import BlockContext

# Async callback signature: (data, context) -> None
EventCallback = Callable[[dict, "BlockContext"], Coroutine[Any, Any, None]]


@dataclass
class PluginEventBus:
    """Per-request event bus enabling plugins to communicate via events.

    Usage:
        bus = PluginEventBus()
        bus.register("dice-rolled", some_callback)
        bus.emit("dice-rolled", {"result": 11})
        await bus.drain(context)  # processes all queued events
    """

    _listeners: dict[str, list[EventCallback]] = field(default_factory=dict)
    _queue: list[tuple[str, dict]] = field(default_factory=list)

    def register(self, event_type: str, callback: EventCallback) -> None:
        """Register a listener for an event type."""
        self._listeners.setdefault(event_type, []).append(callback)

    def emit(self, event_type: str, data: dict) -> None:
        """Queue an event for processing during drain()."""
        self._queue.append((event_type, data))

    async def drain(self, context: "BlockContext") -> None:
        """Process all queued events, invoking registered listeners.

        Events emitted during drain are also processed (breadth-first).
        """
        max_iterations = 100  # safety limit to prevent infinite loops
        iterations = 0
        while self._queue and iterations < max_iterations:
            event_type, data = self._queue.pop(0)
            iterations += 1
            for cb in self._listeners.get(event_type, []):
                try:
                    await cb(data, context)
                except Exception:
                    logger.exception(
                        "Event listener failed for event '%s'", event_type
                    )
        if iterations >= max_iterations:
            logger.warning(
                "Event bus drain hit iteration limit (%d), possible infinite loop",
                max_iterations,
            )
