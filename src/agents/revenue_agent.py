"""
Revenue Ops Agent – tracks MRR/ARR via Stripe, alerts on churn,
and triggers upsell campaigns.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from src.agents import BaseAgent

logger = logging.getLogger(__name__)

# Stripe uses Unix timestamps; MRR thresholds in USD cents
CHURN_ALERT_THRESHOLD = 3  # number of cancellations per cycle before alerting


class RevenueAgent(BaseAgent):
    """Tracks Stripe MRR/ARR, detects churn, and flags upsell opportunities."""

    name = "revenue"
    description = "Track MRR/ARR, alert on churn, trigger upsell campaigns"

    def __init__(self, event_bus=None, stripe_secret_key: str = "") -> None:
        super().__init__(event_bus)
        self._stripe_key = stripe_secret_key or os.getenv("STRIPE_SECRET_KEY", "")
        self._stripe_url = "https://api.stripe.com/v1"
        self._last_mrr_cents: int = 0

    def cycle_interval(self) -> float:
        return 300.0  # every 5 minutes

    async def run_cycle(self) -> None:
        if not self._stripe_key:
            self.logger.debug("No Stripe key – skipping revenue cycle")
            return

        mrr = await self._calculate_mrr()
        if mrr is not None:
            self.record_action("MRR snapshot", {"mrr_usd": mrr / 100})
            await self.emit("revenue.mrr_snapshot", {"mrr_usd": mrr / 100})
            self._last_mrr_cents = mrr

        await self._check_churn()

    async def _stripe_get(self, path: str, params: dict | None = None) -> dict | None:
        url = f"{self._stripe_url}/{path}"
        headers = {"Authorization": f"Bearer {self._stripe_key}"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers, params=params or {})
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            self.logger.warning("Stripe API error: %s", exc)
            return None

    async def _calculate_mrr(self) -> int | None:
        """Sum active subscription monthly amounts (in cents)."""
        data = await self._stripe_get("subscriptions", {"status": "active", "limit": 100})
        if data is None:
            return None
        mrr = 0
        for sub in data.get("data", []):
            for item in sub.get("items", {}).get("data", []):
                plan = item.get("plan", {})
                amount = plan.get("amount", 0)
                interval = plan.get("interval", "month")
                qty = item.get("quantity", 1)
                if interval == "year":
                    amount = amount // 12
                mrr += amount * qty
        return mrr

    async def _check_churn(self) -> None:
        """Look for subscriptions cancelled in the last cycle window."""
        since = int((datetime.now(timezone.utc) - timedelta(seconds=self.cycle_interval())).timestamp())
        data = await self._stripe_get(
            "subscriptions",
            {"status": "canceled", "created[gte]": since, "limit": 100},
        )
        if data is None:
            return
        cancelled = data.get("data", [])
        if len(cancelled) >= CHURN_ALERT_THRESHOLD:
            self.record_action(
                f"Churn alert: {len(cancelled)} cancellations detected",
                {"count": len(cancelled)},
            )
            await self.emit("revenue.churn_alert", {"cancellations": len(cancelled)})
        elif cancelled:
            self.record_action(
                f"{len(cancelled)} cancellation(s) recorded",
                {"count": len(cancelled)},
            )

    def health(self) -> dict[str, Any]:
        h = super().health()
        h["stripe_configured"] = bool(self._stripe_key)
        h["last_mrr_usd"] = self._last_mrr_cents / 100
        return h
