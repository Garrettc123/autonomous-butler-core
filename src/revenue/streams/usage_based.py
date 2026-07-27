"""Usage-based (metered) billing stream."""

import os
from datetime import datetime, timezone
from typing import Any

from src.revenue import RevenueStream, StreamResult
from src.revenue.stripe_client import StripeClient


class UsageBasedStream(RevenueStream):
    """
    Metered billing.

    Buffers usage recorded by the rest of the platform via :meth:`record_usage`
    and flushes it to Stripe usage records on each cycle. Buffered quantities
    are only cleared once Stripe accepts them, so a failed flush is retried on
    the next cycle rather than silently dropping billable usage.
    """

    id = "usage_based"
    title = "Usage-Based Billing"
    description = "Report metered usage to Stripe for consumption billing"

    def __init__(
        self,
        enabled: bool = True,
        client: StripeClient | None = None,
        usage_price_id: str = "",
        **_: Any,
    ) -> None:
        super().__init__(enabled)
        self.client = client or StripeClient()
        self.usage_price_id = usage_price_id or os.getenv("STRIPE_USAGE_PRICE_ID", "")
        # subscription_item_id -> pending quantity
        self._pending: dict[str, int] = {}
        self._reported_total = 0

    def is_configured(self) -> bool:
        return self.client.configured

    def missing_config_reason(self) -> str:
        return "STRIPE_SECRET_KEY is not set"

    def record_usage(self, subscription_item_id: str, quantity: int) -> None:
        """Buffer billable usage to be flushed to Stripe on the next cycle."""
        if not subscription_item_id or quantity <= 0:
            return
        self._pending[subscription_item_id] = self._pending.get(subscription_item_id, 0) + quantity

    async def collect(self) -> StreamResult:
        if not self._pending:
            return StreamResult(
                self.id,
                metrics={
                    "pending_items": 0,
                    "pending_quantity": 0,
                    "reported_total": self._reported_total,
                },
            )

        timestamp = int(datetime.now(timezone.utc).timestamp())
        actions: list[str] = []
        events: list[tuple[str, dict[str, Any]]] = []
        reported = 0
        failed: dict[str, int] = {}

        for item_id, quantity in self._pending.items():
            response = await self.client.post(
                f"subscription_items/{item_id}/usage_records",
                {"quantity": quantity, "timestamp": timestamp, "action": "increment"},
            )
            if response is None:
                # Keep the quantity buffered so the next cycle retries it.
                failed[item_id] = quantity
                continue
            reported += quantity
            actions.append(f"Reported {quantity} usage units for {item_id}")
            events.append(
                ("revenue.usage_reported", {"subscription_item": item_id, "quantity": quantity})
            )

        self._pending = failed
        self._reported_total += reported

        return StreamResult(
            self.id,
            metrics={
                "pending_items": len(self._pending),
                "pending_quantity": sum(self._pending.values()),
                "reported_this_cycle": reported,
                "reported_total": self._reported_total,
            },
            actions=actions,
            events=events,
        )
