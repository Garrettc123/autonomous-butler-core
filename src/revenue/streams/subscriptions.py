"""Subscription revenue stream: active-subscription MRR and ARR."""

from typing import Any

from src.revenue import RevenueStream, StreamResult
from src.revenue.stripe_client import StripeClient

# Average month length, used to normalize non-monthly billing intervals.
WEEKS_PER_MONTH = 52 / 12
DAYS_PER_MONTH = 365 / 12


class SubscriptionStream(RevenueStream):
    """
    Recurring subscription revenue.

    Sums the monthly-normalized amount of every active Stripe subscription to
    produce MRR, and derives ARR from it. Yearly plans are divided by 12 so
    mixed billing intervals roll up into a single comparable figure.
    """

    id = "subscriptions"
    title = "Subscriptions"
    description = "Recurring MRR/ARR from active Stripe subscriptions"

    def __init__(self, enabled: bool = True, client: StripeClient | None = None, **_: Any) -> None:
        super().__init__(enabled)
        self.client = client or StripeClient()
        self._last_mrr_cents = 0

    def is_configured(self) -> bool:
        return self.client.configured

    def missing_config_reason(self) -> str:
        return "STRIPE_SECRET_KEY is not set"

    async def collect(self) -> StreamResult:
        data = await self.client.get("subscriptions", {"status": "active", "limit": 100})
        if data is None:
            return StreamResult.skip(self.id, "Stripe subscriptions unavailable")

        subscriptions = data.get("data", [])
        mrr_cents = sum(self._subscription_mrr_cents(sub) for sub in subscriptions)
        previous = self._last_mrr_cents
        self._last_mrr_cents = mrr_cents

        mrr_usd = round(mrr_cents / 100, 2)
        arr_usd = round(mrr_usd * 12, 2)
        delta_usd = round((mrr_cents - previous) / 100, 2)

        metrics = {
            "mrr_usd": mrr_usd,
            "arr_usd": arr_usd,
            "active_subscriptions": len(subscriptions),
            "mrr_delta_usd": delta_usd,
        }
        return StreamResult(
            self.id,
            metrics=metrics,
            actions=[f"MRR snapshot: ${mrr_usd}"],
            events=[("revenue.mrr_snapshot", metrics)],
        )

    @staticmethod
    def _subscription_mrr_cents(subscription: dict[str, Any]) -> int:
        """
        Normalize one subscription's line items to a monthly cent amount.

        Non-monthly intervals are converted using the average length of a month
        (52/12 weeks, 365/12 days) so mixed billing cadences roll up accurately.
        """
        total = 0
        for item in subscription.get("items", {}).get("data", []):
            plan = item.get("plan") or item.get("price") or {}
            amount = plan.get("amount") or plan.get("unit_amount") or 0
            interval = (plan.get("interval") or plan.get("recurring", {}).get("interval") or "month")
            quantity = item.get("quantity", 1) or 1
            if interval == "year":
                amount = amount // 12
            elif interval == "week":
                amount = round(amount * WEEKS_PER_MONTH)
            elif interval == "day":
                amount = round(amount * DAYS_PER_MONTH)
            total += amount * quantity
        return total
