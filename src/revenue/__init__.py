"""
Revenue stream abstraction shared by all monetizable channels.

A :class:`RevenueStream` models one distinct way the product makes money
(subscriptions, metered usage, one-time purchases, recovered payments,
expansion upsells, ...). Streams are polled on a cycle by the
``RevenueAgent`` orchestrator and each returns a normalized
:class:`StreamResult`.

Every stream must degrade gracefully to a no-op when its credentials or
configuration are missing, so the platform runs unattended in environments
where only some integrations are wired up.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


class StreamResult:
    """Normalized outcome of a single :meth:`RevenueStream.collect` run."""

    def __init__(
        self,
        stream_id: str,
        *,
        skipped: bool = False,
        reason: str = "",
        metrics: dict[str, Any] | None = None,
        actions: list[str] | None = None,
        events: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> None:
        self.stream_id = stream_id
        self.skipped = skipped
        self.reason = reason
        self.metrics = metrics or {}
        self.actions = actions or []
        # Each event is a ``(topic, payload)`` pair published by the orchestrator.
        self.events = events or []
        self.timestamp = datetime.now(timezone.utc).isoformat()

    @classmethod
    def skip(cls, stream_id: str, reason: str) -> "StreamResult":
        """Build a no-op result, used when credentials/config are absent."""
        return cls(stream_id, skipped=True, reason=reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "skipped": self.skipped,
            "reason": self.reason,
            "metrics": self.metrics,
            "actions": self.actions,
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"StreamResult(stream_id={self.stream_id!r}, skipped={self.skipped!r})"


class RevenueStream(ABC):
    """
    Abstract base for a single monetizable channel.

    Subclasses declare a stable ``id``/``title`` and implement :meth:`collect`.
    Streams that can take corrective action (retrying a payment, sending an
    upsell) additionally override :meth:`activate`.
    """

    id: str = "base"
    title: str = ""
    description: str = ""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.logger = logging.getLogger(f"butler.revenue.{self.id}")
        self._last_result: StreamResult | None = None
        self._collect_count = 0
        self._error_count = 0
        self._action_count = 0
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Whether the stream has everything it needs to do real work."""
        return True

    def missing_config_reason(self) -> str:
        """Human-readable explanation shown when the stream is skipped."""
        return "stream is not configured"

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def collect(self) -> StreamResult:
        """Gather current metrics for this stream."""

    async def activate(self) -> StreamResult:
        """
        Take revenue-generating/recovering action.

        Defaults to a no-op for read-only streams.
        """
        return StreamResult.skip(self.id, "stream has no activate() behaviour")

    # ------------------------------------------------------------------
    # Orchestrator entry point
    # ------------------------------------------------------------------

    async def run(self) -> StreamResult:
        """
        Execute one cycle for this stream, never raising.

        Returns a skip result when disabled or unconfigured, and converts any
        unexpected exception into a recorded error so one broken integration
        cannot stall the others.
        """
        if not self.enabled:
            return StreamResult.skip(self.id, "stream is disabled")
        if not self.is_configured():
            return StreamResult.skip(self.id, self.missing_config_reason())

        try:
            result = await self.collect()
        except Exception as exc:  # noqa: BLE001
            self._error_count += 1
            self._last_error = str(exc)
            self.logger.error("Stream %s failed: %s", self.id, exc)
            return StreamResult.skip(self.id, f"error: {exc}")

        self._collect_count += 1
        self._action_count += len(result.actions)
        self._last_result = result
        return result

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Status summary surfaced through the API and dashboard."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "enabled": self.enabled,
            "configured": self.is_configured(),
            "collect_count": self._collect_count,
            "action_count": self._action_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
            "last_metrics": self._last_result.metrics if self._last_result else {},
            "last_run": self._last_result.timestamp if self._last_result else None,
        }


class StreamRegistry:
    """
    Registry of revenue streams, enabled or disabled per environment.

    Streams are registered as factories so they are only instantiated when the
    registry is built, letting configuration be read at construction time.
    """

    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., RevenueStream]] = {}

    def register(self, stream_id: str, factory: Callable[..., RevenueStream]) -> None:
        """Register a stream factory under a stable id."""
        if stream_id in self._factories:
            logger.debug("Overwriting registered revenue stream %r", stream_id)
        self._factories[stream_id] = factory

    def ids(self) -> list[str]:
        """All registered stream ids, in registration order."""
        return list(self._factories)

    def build(self, enabled_ids: set[str] | None = None, **kwargs: Any) -> list[RevenueStream]:
        """
        Instantiate every registered stream.

        ``enabled_ids`` selects which streams are active; streams outside the
        set are still built (so they show up in the dashboard) but marked
        disabled. ``None`` enables everything.
        """
        streams: list[RevenueStream] = []
        for stream_id, factory in self._factories.items():
            enabled = enabled_ids is None or stream_id in enabled_ids
            try:
                streams.append(factory(enabled=enabled, **kwargs))
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to build revenue stream %r: %s", stream_id, exc)
        return streams


# Module-level singleton populated by ``src.revenue.streams``.
registry = StreamRegistry()
