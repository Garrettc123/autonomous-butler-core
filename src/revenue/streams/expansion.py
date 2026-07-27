"""Churn prevention and expansion/upsell stream."""

from datetime import datetime, timedelta, timezone
from typing import Any

from src.revenue import RevenueStream, StreamResult
from src.revenue.stripe_client import StripeClient

# Number of cancellations within one window before an alert is raised.
CHURN_ALERT_THRESHOLD = 3

# Cancellation look-back window, in seconds.
CHURN_WINDOW_SECONDS = 300


class ExpansionStream(RevenueStream):
    """
    Churn prevention and expansion revenue.

    Watches recently cancelled subscriptions to raise churn alerts, and
    compares seat counts between cycles so growing accounts surface as upsell
    opportunities for the rest of the platform to act on.
    """

    id = "expansion"
    title = "Churn & Upsell"
    description = "Alert on churn and flag expansion/upsell opportunities"

    def __init__(
        self,
        enabled: bool = True,
        client: StripeClient | None = None,
        churn_window_seconds: int = CHURN_WINDOW_SECONDS,
        churn_alert_threshold: int = CHURN_ALERT_THRESHOLD,
        **_: Any,
    ) -> None:
        super().__init__(enabled)
        self.client = client or StripeClient()
        self.churn_window_seconds = churn_window_seconds
        self.churn_alert_threshold = churn_alert_threshold
        # subscription_id -> total seat quantity observed on the previous cycle
        self._seat_counts: dict[str, int] = {}
        self._churned_total = 0
        self._upsell_total = 0

    def is_configured(self) -> bool:
        return self.client.configured

    def missing_config_reason(self) -> str:
        return "STRIPE_SECRET_KEY is not set"

    async def collect(self) -> StreamResult:
        actions: list[str] = []
        events: list[tuple[str, dict[str, Any]]] = []
        metrics: dict[str, Any] = {}

        churn = await self._collect_churn(actions, events)
        metrics.update(churn)

        expansion = await self._collect_expansion(actions, events)
        metrics.update(expansion)

        return StreamResult(self.id, metrics=metrics, actions=actions, events=events)

    # ------------------------------------------------------------------
    # Churn
    # ------------------------------------------------------------------

    async def _collect_churn(
        self, actions: list[str], events: list[tuple[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        since = int(
            (
                datetime.now(timezone.utc) - timedelta(seconds=self.churn_window_seconds)
            ).timestamp()
        )
        data = await self.client.get(
            "subscriptions", {"status": "canceled", "created[gte]": since, "limit": 100}
        )
        if data is None:
            return {"cancellations": 0}

        cancelled = data.get("data", [])
        count = len(cancelled)
        self._churned_total += count

        if count >= self.churn_alert_threshold:
            actions.append(f"Churn alert: {count} cancellations detected")
            events.append(("revenue.churn_alert", {"cancellations": count}))
        elif count:
            actions.append(f"{count} cancellation(s) recorded")

        return {"cancellations": count, "churned_total": self._churned_total}

    # ------------------------------------------------------------------
    # Expansion / upsell
    # ------------------------------------------------------------------

    async def _collect_expansion(
        self, actions: list[str], events: list[tuple[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        data = await self.client.get("subscriptions", {"status": "active", "limit": 100})
        if data is None:
            return {"upsell_opportunities": 0}

        opportunities = 0
        current: dict[str, int] = {}

        for subscription in data.get("data", []):
            sub_id = subscription.get("id")
            if not sub_id:
                continue
            seats = self._seat_count(subscription)
            current[sub_id] = seats

            previous = self._seat_counts.get(sub_id)
            if previous is not None and seats > previous:
                opportunities += 1
                payload = {
                    "subscription": sub_id,
                    "previous_seats": previous,
                    "current_seats": seats,
                }
                actions.append(
                    f"Upsell opportunity: {sub_id} grew {previous} → {seats} seats"
                )
                events.append(("revenue.upsell_opportunity", payload))

        self._seat_counts = current
        self._upsell_total += opportunities

        return {
            "tracked_subscriptions": len(current),
            "upsell_opportunities": opportunities,
            "upsell_total": self._upsell_total,
        }

    @staticmethod
    def _seat_count(subscription: dict[str, Any]) -> int:
        return sum(
            item.get("quantity", 1) or 1
            for item in subscription.get("items", {}).get("data", [])
        )
