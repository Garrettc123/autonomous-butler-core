"""One-time / checkout revenue stream."""

from datetime import datetime, timedelta, timezone
from typing import Any

from src.revenue import RevenueStream, StreamResult
from src.revenue.stripe_client import StripeClient

# Look back far enough to give a stable running total between cycles.
LOOKBACK_HOURS = 24


class OneTimeStream(RevenueStream):
    """
    Non-recurring revenue.

    Aggregates succeeded Stripe charges from the recent window, excluding any
    charge tied to a subscription invoice so this stream never double-counts
    revenue already reported by the subscription stream.
    """

    id = "one_time"
    title = "One-Time Purchases"
    description = "Aggregate non-subscription charges and checkout revenue"

    def __init__(
        self,
        enabled: bool = True,
        client: StripeClient | None = None,
        lookback_hours: int = LOOKBACK_HOURS,
        **_: Any,
    ) -> None:
        super().__init__(enabled)
        self.client = client or StripeClient()
        self.lookback_hours = lookback_hours

    def is_configured(self) -> bool:
        return self.client.configured

    def missing_config_reason(self) -> str:
        return "STRIPE_SECRET_KEY is not set"

    async def collect(self) -> StreamResult:
        since = int(
            (datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)).timestamp()
        )
        data = await self.client.get("charges", {"created[gte]": since, "limit": 100})
        if data is None:
            return StreamResult.skip(self.id, "Stripe charges unavailable")

        charges = data.get("data", [])
        gross_cents = 0
        refunded_cents = 0
        count = 0

        for charge in charges:
            if charge.get("invoice"):
                # Invoice-backed charges belong to the subscription stream.
                continue
            if charge.get("status") != "succeeded":
                continue
            count += 1
            gross_cents += charge.get("amount", 0)
            refunded_cents += charge.get("amount_refunded", 0)

        net_cents = gross_cents - refunded_cents
        metrics = {
            "window_hours": self.lookback_hours,
            "charge_count": count,
            "gross_usd": round(gross_cents / 100, 2),
            "refunded_usd": round(refunded_cents / 100, 2),
            "net_usd": round(net_cents / 100, 2),
        }

        actions: list[str] = []
        events: list[tuple[str, dict[str, Any]]] = []
        if count:
            actions.append(f"{count} one-time purchase(s) totalling ${metrics['net_usd']}")
            events.append(("revenue.one_time_snapshot", metrics))

        return StreamResult(self.id, metrics=metrics, actions=actions, events=events)
