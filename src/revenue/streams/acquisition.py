"""Customer acquisition stream: find leads, enrich them, and bill them."""

import os
from typing import Any

from src.leads import DEFAULT_QUALIFY_SCORE, Lead, LeadPipeline
from src.leads.enrichment import ClearbitEnricher, GitHubProfileEnricher, HunterEnricher
from src.leads.sources import GitHubLeadSource
from src.revenue import RevenueStream, StreamResult
from src.revenue.stripe_client import StripeClient

# How many candidates each source contributes per cycle.
DEFAULT_DISCOVERY_LIMIT = 25

# Hard cap on billable outreach per cycle, so a bad enrichment run cannot
# invoice hundreds of prospects at once.
DEFAULT_MAX_INVOICES_PER_CYCLE = 5

# Prospect invoices are payable on net-14 terms.
INVOICE_DAYS_UNTIL_DUE = 14


def _parse_keywords(raw: str) -> tuple[str, ...]:
    """Parse the comma-separated ICP keyword setting."""
    return tuple(part.strip() for part in (raw or "").split(",") if part.strip())


def _parse_qualify_score(raw: str) -> int:
    """Parse the qualification threshold, falling back on unset/invalid input."""
    try:
        return int((raw or "").strip())
    except ValueError:
        return DEFAULT_QUALIFY_SCORE


def _default_pipeline(icp_keywords: tuple[str, ...], qualify_score: int) -> LeadPipeline:
    """Build the stock source/enricher set from environment configuration."""
    return LeadPipeline(
        sources=[GitHubLeadSource(keywords=icp_keywords)],
        enrichers=[GitHubProfileEnricher(), ClearbitEnricher(), HunterEnricher()],
        icp_keywords=icp_keywords,
        qualify_score=qualify_score,
    )


class AcquisitionStream(RevenueStream):
    """
    Top-of-funnel revenue: turn strangers into paying customers.

    Each cycle the stream discovers new accounts matching the ICP, enriches
    them until a deliverable business email is known, scores them, and then
    creates a Stripe customer and sends a real invoice for the configured
    price. Prospects already present in Stripe are never re-billed.

    Everything degrades independently: with no lead providers the stream is a
    no-op, and with providers but no acquisition price it still builds the
    qualified pipeline and reports it without charging anyone.
    """

    id = "acquisition"
    title = "Customer Acquisition"
    description = "Discover and enrich leads, then invoice qualified prospects"

    def __init__(
        self,
        enabled: bool = True,
        client: StripeClient | None = None,
        pipeline: LeadPipeline | None = None,
        *,
        icp_keywords: tuple[str, ...] | None = None,
        qualify_score: int | None = None,
        discovery_limit: int = DEFAULT_DISCOVERY_LIMIT,
        max_invoices_per_cycle: int = DEFAULT_MAX_INVOICES_PER_CYCLE,
        price_id: str = "",
        **_: Any,
    ) -> None:
        super().__init__(enabled)
        self.client = client or StripeClient()
        keywords = (
            icp_keywords
            if icp_keywords is not None
            else _parse_keywords(os.getenv("ICP_KEYWORDS", ""))
        )
        if qualify_score is None:
            qualify_score = _parse_qualify_score(os.getenv("LEAD_QUALIFY_SCORE", ""))
        self.icp_keywords = keywords
        self.pipeline = pipeline or _default_pipeline(keywords, qualify_score)
        self.discovery_limit = discovery_limit
        self.max_invoices_per_cycle = max_invoices_per_cycle
        self.price_id = price_id or os.getenv("STRIPE_ACQUISITION_PRICE_ID", "")
        self._customers_created = 0
        self._invoices_sent = 0
        self._billed_emails: set[str] = set()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return self.pipeline.configured

    def missing_config_reason(self) -> str:
        return "no lead source is configured (set GITHUB_TOKEN and ICP_KEYWORDS)"

    @property
    def billing_enabled(self) -> bool:
        """Whether qualified leads can actually be invoiced."""
        return self.client.configured and bool(self.price_id)

    # ------------------------------------------------------------------
    # Cycle
    # ------------------------------------------------------------------

    async def collect(self) -> StreamResult:
        leads, qualified = await self.pipeline.run(self.discovery_limit)

        actions: list[str] = []
        events: list[tuple[str, dict[str, Any]]] = []

        for lead, score in qualified:
            events.append(("revenue.lead_qualified", {**lead.to_dict(), "score": score}))

        billed = 0
        if qualified and not self.billing_enabled:
            actions.append(
                f"{len(qualified)} qualified lead(s) awaiting billing config "
                "(STRIPE_SECRET_KEY / STRIPE_ACQUISITION_PRICE_ID)"
            )
        else:
            for lead, score in qualified:
                if billed >= self.max_invoices_per_cycle:
                    break
                outcome = await self._bill_lead(lead, score)
                if outcome is None:
                    continue
                billed += 1
                actions.append(outcome[0])
                events.append(outcome[1])

        metrics = {
            "discovered": len(leads),
            "qualified": len(qualified),
            "invoiced": billed,
            "billing_enabled": self.billing_enabled,
            "customers_created": self._customers_created,
            "invoices_sent": self._invoices_sent,
            "discovered_total": self.pipeline.discovered_count,
            "enriched_total": self.pipeline.enriched_count,
            "qualified_total": self.pipeline.qualified_count,
            "top_score": max((score for _, score in qualified), default=0),
        }

        if leads and not actions:
            actions.append(f"Discovered {len(leads)} lead(s), {len(qualified)} qualified")

        return StreamResult(self.id, metrics=metrics, actions=actions, events=events)

    # ------------------------------------------------------------------
    # Billing
    # ------------------------------------------------------------------

    async def _bill_lead(
        self, lead: Lead, score: int
    ) -> tuple[str, tuple[str, dict[str, Any]]] | None:
        """
        Create a Stripe customer for ``lead`` and send them an invoice.

        Returns ``(action, event)`` on success, or ``None`` when the lead was
        skipped (already a customer, or Stripe rejected a step).
        """
        if lead.email in self._billed_emails:
            return None

        if await self._customer_exists(lead.email):
            # Existing customers belong to the subscription/expansion streams.
            self._billed_emails.add(lead.email)
            return None

        customer = await self.client.post(
            "customers",
            {
                "email": lead.email,
                "name": lead.company or lead.name or lead.email,
                "description": f"Acquired by butler from {lead.source}",
                "metadata[lead_id]": lead.lead_id,
                "metadata[lead_source]": lead.source,
                "metadata[lead_score]": str(score),
            },
        )
        customer_id = (customer or {}).get("id")
        if not customer_id:
            self.logger.warning("Could not create Stripe customer for %s", lead.lead_id)
            return None
        self._customers_created += 1

        item = await self.client.post(
            "invoiceitems", {"customer": customer_id, "price": self.price_id}
        )
        if item is None:
            self.logger.warning("Could not add invoice item for %s", lead.lead_id)
            return None

        invoice = await self.client.post(
            "invoices",
            {
                "customer": customer_id,
                "collection_method": "send_invoice",
                "days_until_due": INVOICE_DAYS_UNTIL_DUE,
                "auto_advance": "true",
                "metadata[lead_id]": lead.lead_id,
            },
        )
        invoice_id = (invoice or {}).get("id")
        if not invoice_id:
            self.logger.warning("Could not create invoice for %s", lead.lead_id)
            return None

        sent = await self.client.post(f"invoices/{invoice_id}/send", {})
        if sent is None:
            self.logger.warning("Could not send invoice %s", invoice_id)
            return None

        self._invoices_sent += 1
        self._billed_emails.add(lead.email)
        amount_usd = round((sent.get("amount_due", 0) or 0) / 100, 2)
        action = (
            f"Invoiced new prospect {lead.email} (score {score}) "
            f"for ${amount_usd} via invoice {invoice_id}"
        )
        event = (
            "revenue.prospect_invoiced",
            {
                "lead_id": lead.lead_id,
                "customer": customer_id,
                "invoice": invoice_id,
                "amount_usd": amount_usd,
                "score": score,
                "hosted_invoice_url": sent.get("hosted_invoice_url", ""),
            },
        )
        return action, event

    async def _customer_exists(self, email: str) -> bool:
        """Whether Stripe already knows this email, to avoid double billing."""
        existing = await self.client.get("customers", {"email": email, "limit": 1})
        if existing is None:
            # Treat an unreachable Stripe as "already exists" so a transient
            # outage can never cause duplicate customers or invoices.
            return True
        return bool(existing.get("data"))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        s = super().status()
        s["billing_enabled"] = self.billing_enabled
        s["pipeline"] = self.pipeline.status()
        return s


__all__ = ["AcquisitionStream"]
