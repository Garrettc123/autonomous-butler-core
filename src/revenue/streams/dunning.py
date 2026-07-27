"""Payment recovery (dunning) stream."""

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from src.revenue import RevenueStream, StreamResult
from src.revenue.stripe_client import StripeClient

# Exponential backoff (in seconds) between retry attempts for one invoice:
# 1h, 6h, 24h, 72h. Invoices exhausting the schedule are given up on.
RETRY_BACKOFF_SECONDS = (3600, 21600, 86400, 259200)
MAX_RETRIES = len(RETRY_BACKOFF_SECONDS)

# Only consider invoices that became due within this window.
LOOKBACK_DAYS = 30


class DunningStream(RevenueStream):
    """
    Failed-payment recovery.

    Finds open Stripe invoices whose payment attempts failed and re-attempts
    them on an exponential backoff schedule, tracking recovery rate so the
    platform can report how much revenue it clawed back automatically.
    """

    id = "dunning"
    title = "Payment Recovery"
    description = "Detect failed invoices and retry payment with backoff"

    def __init__(
        self,
        enabled: bool = True,
        client: StripeClient | None = None,
        lookback_days: int = LOOKBACK_DAYS,
        **_: Any,
    ) -> None:
        super().__init__(enabled)
        self.client = client or StripeClient()
        self.lookback_days = lookback_days
        # invoice_id -> {"attempts": int, "next_attempt_at": float}
        self._retry_state: dict[str, dict[str, float]] = {}
        self._recovered_count = 0
        self._recovered_cents = 0
        self._attempted_count = 0

    def is_configured(self) -> bool:
        return self.client.configured

    def missing_config_reason(self) -> str:
        return "STRIPE_SECRET_KEY is not set"

    async def collect(self) -> StreamResult:
        since = int((datetime.now(timezone.utc) - timedelta(days=self.lookback_days)).timestamp())
        data = await self.client.get(
            "invoices", {"status": "open", "created[gte]": since, "limit": 100}
        )
        if data is None:
            return StreamResult.skip(self.id, "Stripe invoices unavailable")

        invoices = [inv for inv in data.get("data", []) if self._has_failed_payment(inv)]
        at_risk_cents = sum(inv.get("amount_due", 0) for inv in invoices)

        actions: list[str] = []
        events: list[tuple[str, dict[str, Any]]] = []
        now = time.time()

        for invoice in invoices:
            invoice_id = invoice.get("id")
            if not invoice_id:
                continue

            state = self._retry_state.setdefault(
                invoice_id, {"attempts": 0, "next_attempt_at": now}
            )
            attempts = int(state["attempts"])
            if attempts >= MAX_RETRIES:
                continue
            if now < state["next_attempt_at"]:
                continue

            state["attempts"] = attempts + 1
            state["next_attempt_at"] = now + RETRY_BACKOFF_SECONDS[attempts]
            self._attempted_count += 1

            response = await self.client.post(f"invoices/{invoice_id}/pay", {})
            if response is None:
                actions.append(f"Retry {attempts + 1} failed for invoice {invoice_id}")
                events.append(
                    (
                        "revenue.payment_retry_failed",
                        {"invoice": invoice_id, "attempt": attempts + 1},
                    )
                )
                continue

            if response.get("status") == "paid" or response.get("paid") is True:
                amount = response.get("amount_paid", invoice.get("amount_due", 0))
                self._recovered_count += 1
                self._recovered_cents += amount
                self._retry_state.pop(invoice_id, None)
                actions.append(
                    f"Recovered ${round(amount / 100, 2)} from invoice {invoice_id}"
                )
                events.append(
                    (
                        "revenue.payment_recovered",
                        {"invoice": invoice_id, "amount_usd": round(amount / 100, 2)},
                    )
                )
            else:
                actions.append(f"Retry {attempts + 1} did not settle invoice {invoice_id}")

        # Drop state for invoices that are no longer open/failing.
        live_ids = {inv.get("id") for inv in invoices}
        for stale_id in [i for i in self._retry_state if i not in live_ids]:
            self._retry_state.pop(stale_id, None)

        metrics = {
            "failed_invoices": len(invoices),
            "at_risk_usd": round(at_risk_cents / 100, 2),
            "retries_attempted": self._attempted_count,
            "recovered_count": self._recovered_count,
            "recovered_usd": round(self._recovered_cents / 100, 2),
            "recovery_rate": self._recovery_rate(),
        }
        return StreamResult(self.id, metrics=metrics, actions=actions, events=events)

    def _recovery_rate(self) -> float:
        if not self._attempted_count:
            return 0.0
        return round(self._recovered_count / self._attempted_count, 3)

    @staticmethod
    def _has_failed_payment(invoice: dict[str, Any]) -> bool:
        """An open invoice with at least one attempt and nothing paid has failed."""
        return bool(invoice.get("attempt_count", 0)) and not invoice.get("paid", False)
