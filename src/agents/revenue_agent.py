"""
Revenue Ops Agent – orchestrates every revenue stream.

The agent itself holds no Stripe logic. It builds the configured set of
:class:`~src.revenue.RevenueStream` instances from the shared registry, runs
them on each cycle, records their actions, and republishes their events onto
the bus. Adding a new monetizable channel means registering a new stream, not
editing this file.
"""

import os
from typing import Any

from src.agents import BaseAgent
from src.revenue import RevenueStream, StreamResult, registry
from src.revenue.stripe_client import StripeClient

# Importing the streams package registers all built-in streams.
import src.revenue.streams  # noqa: F401

DEFAULT_CYCLE_SECONDS = 300.0


def _parse_enabled_streams(raw: str) -> set[str] | None:
    """
    Parse the ``REVENUE_STREAMS`` setting into a set of stream ids.

    Empty or ``"all"`` enables every registered stream.
    """
    value = (raw or "").strip()
    if not value or value.lower() == "all":
        return None
    return {part.strip() for part in value.split(",") if part.strip()}


class RevenueAgent(BaseAgent):
    """Runs every enabled revenue stream and reports their combined state."""

    name = "revenue"
    description = "Orchestrate subscription, usage, one-time, dunning and upsell revenue"

    def __init__(
        self,
        event_bus=None,
        stripe_secret_key: str = "",
        enabled_streams: set[str] | None = None,
        streams: list[RevenueStream] | None = None,
    ) -> None:
        super().__init__(event_bus)
        self._stripe_key = stripe_secret_key or os.getenv("STRIPE_SECRET_KEY", "")
        self._client = StripeClient(self._stripe_key)

        if streams is not None:
            self.streams = streams
        else:
            if enabled_streams is None:
                enabled_streams = _parse_enabled_streams(os.getenv("REVENUE_STREAMS", ""))
            self.streams = registry.build(enabled_streams, client=self._client)

    def cycle_interval(self) -> float:
        return DEFAULT_CYCLE_SECONDS

    # ------------------------------------------------------------------
    # Stream access
    # ------------------------------------------------------------------

    def get_stream(self, stream_id: str) -> RevenueStream | None:
        """Return a stream by id, or ``None`` if it is not registered."""
        for stream in self.streams:
            if stream.id == stream_id:
                return stream
        return None

    def stream_statuses(self) -> list[dict[str, Any]]:
        """Status of every stream, for the API and dashboard."""
        return [stream.status() for stream in self.streams]

    # ------------------------------------------------------------------
    # Cycle
    # ------------------------------------------------------------------

    async def run_cycle(self) -> None:
        for stream in self.streams:
            result = await stream.run()
            await self._handle_result(stream, result)

    async def _handle_result(self, stream: RevenueStream, result: StreamResult) -> None:
        if result.skipped:
            self.logger.debug("Stream %s skipped: %s", stream.id, result.reason)
            return

        for action in result.actions:
            self.record_action(action, {"stream": stream.id})

        for topic, payload in result.events:
            await self.emit(topic, {**payload, "stream": stream.id})

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        h = super().health()
        h["stripe_configured"] = bool(self._stripe_key)
        h["streams_enabled"] = sum(1 for s in self.streams if s.enabled)
        h["streams_total"] = len(self.streams)
        h["last_mrr_usd"] = self._last_mrr_usd()
        h["streams"] = self.stream_statuses()
        return h

    def _last_mrr_usd(self) -> float:
        """Most recent MRR reading, kept for dashboard/API backwards compatibility."""
        subscriptions = self.get_stream("subscriptions")
        if subscriptions is None:
            return 0.0
        return float(subscriptions.status()["last_metrics"].get("mrr_usd", 0.0))
