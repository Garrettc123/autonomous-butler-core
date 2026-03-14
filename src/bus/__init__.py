"""Inter-agent event bus for asynchronous communication."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class Event:
    """Represents a message on the event bus."""

    def __init__(self, topic: str, source: str, payload: dict[str, Any]):
        self.topic = topic
        self.source = source
        self.payload = payload
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.id = f"{source}-{topic}-{self.timestamp}"

    def __repr__(self) -> str:
        return f"Event(topic={self.topic!r}, source={self.source!r})"


class EventBus:
    """
    In-memory async pub/sub event bus for inter-agent communication.

    Agents publish events to topics and subscribe to topics they care about.
    All delivery is non-blocking; slow subscribers do not block publishers.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history = 1000

    def subscribe(self, topic: str, handler: Callable[[Event], Coroutine]) -> None:
        """Register an async handler for a topic."""
        self._subscribers[topic].append(handler)
        logger.debug("Subscribed %s to topic %r", handler, topic)

    def unsubscribe(self, topic: str, handler: Callable) -> None:
        """Remove a handler from a topic."""
        handlers = self._subscribers.get(topic, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers of its topic.

        Each handler is invoked concurrently; errors are logged and swallowed
        so one bad subscriber cannot block others.
        """
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        handlers = list(self._subscribers.get(event.topic, []))
        if not handlers:
            logger.debug("No subscribers for topic %r", event.topic)
            return

        tasks = [asyncio.create_task(self._call(h, event)) for h in handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _call(self, handler: Callable, event: Event) -> None:
        try:
            await handler(event)
        except Exception as exc:  # noqa: BLE001
            logger.error("Handler %s raised %s for event %s", handler, exc, event)

    def recent_events(self, limit: int = 50) -> list[Event]:
        """Return the most recent events (newest last)."""
        return self._history[-limit:]

    def topics(self) -> list[str]:
        """Return all topics that have at least one subscriber."""
        return [t for t, handlers in self._subscribers.items() if handlers]


# Module-level singleton so agents can share one bus instance.
bus = EventBus()
