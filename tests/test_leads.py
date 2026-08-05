"""Tests for lead discovery, enrichment and the acquisition revenue stream."""

import httpx
import pytest

from src.leads import (
    Lead,
    LeadEnricher,
    LeadPipeline,
    LeadSource,
    is_business_email,
    is_valid_email,
    normalize_domain,
)
from src.leads.enrichment import ClearbitEnricher, GitHubProfileEnricher, HunterEnricher
from src.leads.sources import GitHubLeadSource
from src.revenue.streams.acquisition import (
    AcquisitionStream,
    _parse_keywords,
    _parse_qualify_score,
)
from src.leads.outreach import EmailChannel, OutreachAgent, OutreachResult
from src.revenue.stripe_client import StripeClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def mock_transport(routes: dict[str, object]) -> httpx.MockTransport:
    """
    Map a route key to a JSON body (dict) or a status code (int).

    A key is either a URL path fragment, or ``"<METHOD> <fragment>"`` when the
    same path must behave differently for GET and POST (as Stripe's
    ``/customers`` does: GET searches, POST creates).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        for key, response in routes.items():
            method, _, fragment = key.rpartition(" ")
            if method and method != request.method:
                continue
            if fragment in request.url.path:
                if isinstance(response, int):
                    return httpx.Response(response, json={"error": "boom"})
                return httpx.Response(200, json=response)
        return httpx.Response(404, json={"error": "no stub for " + request.url.path})

    return httpx.MockTransport(handler)


def stripe_stub(routes: dict[str, object], *, key: str = "sk_test_123") -> StripeClient:
    return StripeClient(key, transport=mock_transport(routes))


class StaticSource(LeadSource):
    id = "static"

    def __init__(self, leads: list[Lead], configured: bool = True) -> None:
        super().__init__()
        self._leads = leads
        self._configured = configured

    @property
    def configured(self) -> bool:
        return self._configured

    async def fetch(self, limit: int) -> list[Lead]:
        return self._leads[:limit]


class ExplodingSource(LeadSource):
    id = "boom"

    async def fetch(self, limit: int) -> list[Lead]:
        raise RuntimeError("provider down")


class StaticEnricher(LeadEnricher):
    id = "static_enricher"

    def __init__(self, data: dict) -> None:
        super().__init__()
        self._data = data

    async def lookup(self, lead: Lead) -> dict:
        return self._data


class ExplodingEnricher(LeadEnricher):
    id = "boom_enricher"

    async def lookup(self, lead: Lead) -> dict:
        raise RuntimeError("provider down")


def qualified_lead(email: str = "cto@acme.io") -> Lead:
    return Lead(
        lead_id="github:acme",
        source="github",
        name="Acme",
        email=email,
        company="Acme Inc",
        title="CTO",
        company_size=50,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.acme.io/pricing", "acme.io"),
        ("cto@acme.io", "acme.io"),
        ("ACME.IO", "acme.io"),
        ("", ""),
        ("http://sub.acme.io?utm=1", "sub.acme.io"),
    ],
)
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def test_email_validation():
    assert is_valid_email("cto@acme.io")
    assert not is_valid_email("not-an-email")
    assert not is_valid_email("")
    assert is_business_email("cto@acme.io")
    assert not is_business_email("someone@gmail.com")
    assert not is_business_email("nope")


def test_parse_keywords():
    assert _parse_keywords("devops, sre ,") == ("devops", "sre")
    assert _parse_keywords("") == ()


@pytest.mark.parametrize("raw,expected", [("70", 70), ("", 55), ("nonsense", 55)])
def test_parse_qualify_score(raw, expected):
    assert _parse_qualify_score(raw) == expected


# ---------------------------------------------------------------------------
# Lead model
# ---------------------------------------------------------------------------


def test_merge_fills_blanks_without_overwriting():
    lead = Lead(lead_id="l1", source="s", company="Acme Inc")
    changed = lead.merge("provider", {"company": "Other", "email": "CTO@Acme.io"})
    assert changed is True
    assert lead.company == "Acme Inc"
    assert lead.email == "cto@acme.io"
    # Domain is derived from the newly discovered email.
    assert lead.domain == "acme.io"
    assert lead.enriched_by == ["provider"]


def test_merge_rejects_invalid_values_and_reports_no_change():
    lead = Lead(lead_id="l1", source="s")
    assert lead.merge("provider", {"email": "bogus", "company_size": -3}) is False
    assert lead.email == ""
    assert lead.company_size == 0


def test_merge_accumulates_unique_signals():
    lead = Lead(lead_id="l1", source="s")
    lead.merge("a", {"signals": ["stars:10"]})
    lead.merge("b", {"signals": ["stars:10", "topic:devops"]})
    assert lead.signals == ["stars:10", "topic:devops"]
    assert lead.enriched_by == ["a", "b"]


def test_score_rewards_contactable_icp_fit():
    weak = Lead(lead_id="l1", source="s", email="someone@gmail.com")
    strong = qualified_lead()
    assert weak.score() < strong.score()
    assert strong.score(("cto",)) > strong.score()
    assert Lead(lead_id="l2", source="s").score() == 0


def test_score_is_clamped_to_100():
    lead = qualified_lead()
    lead.signals = ["topic:devops"]
    assert lead.score(("devops",)) <= 100


def test_is_contactable_requires_email():
    assert qualified_lead().is_contactable()
    assert not Lead(lead_id="l1", source="s", company="Acme").is_contactable()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_deduplicates_across_cycles():
    source = StaticSource([qualified_lead()])
    pipeline = LeadPipeline(sources=[source])

    first = await pipeline.discover(10)
    second = await pipeline.discover(10)

    assert len(first) == 1
    assert second == []
    assert pipeline.discovered_count == 1


@pytest.mark.asyncio
async def test_pipeline_survives_failing_provider():
    pipeline = LeadPipeline(
        sources=[ExplodingSource(), StaticSource([qualified_lead()])],
        enrichers=[ExplodingEnricher(), StaticEnricher({"location": "Berlin"})],
    )
    leads, qualified = await pipeline.run(10)
    assert len(leads) == 1
    assert leads[0].location == "Berlin"
    assert len(qualified) == 1


@pytest.mark.asyncio
async def test_pipeline_skips_unconfigured_source():
    pipeline = LeadPipeline(sources=[StaticSource([qualified_lead()], configured=False)])
    assert pipeline.configured is False
    assert await pipeline.discover(10) == []


@pytest.mark.asyncio
async def test_pipeline_qualifies_only_high_scores_sorted():
    weak = Lead(lead_id="weak", source="s", email="me@gmail.com")
    strong = qualified_lead()
    pipeline = LeadPipeline(sources=[StaticSource([weak, strong])], qualify_score=55)
    _, qualified = await pipeline.run(10)
    assert [lead.lead_id for lead, _ in qualified] == ["github:acme"]


@pytest.mark.asyncio
async def test_pipeline_run_short_circuits_without_leads():
    pipeline = LeadPipeline(sources=[StaticSource([])])
    assert await pipeline.run(10) == ([], [])


def test_pipeline_seen_set_is_bounded():
    pipeline = LeadPipeline(max_seen=2)
    for i in range(5):
        pipeline._remember(f"lead-{i}")
    assert len(pipeline._seen) == 2
    assert pipeline.already_seen("lead-4")
    assert not pipeline.already_seen("lead-0")


def test_pipeline_status_lists_providers():
    pipeline = LeadPipeline(
        sources=[StaticSource([])], enrichers=[StaticEnricher({})]
    )
    status = pipeline.status()
    assert status["sources"][0]["id"] == "static"
    assert status["enrichers"][0]["id"] == "static_enricher"


# ---------------------------------------------------------------------------
# GitHub lead source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_source_without_token_is_noop(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    source = GitHubLeadSource("", keywords=("devops",))
    assert source.configured is False
    assert await source.discover(5) == []


@pytest.mark.asyncio
async def test_github_source_without_keywords_is_noop():
    source = GitHubLeadSource("ghp_test", keywords=())
    assert source.configured is False
    assert await source.discover(5) == []


@pytest.mark.asyncio
async def test_github_source_maps_repos_to_leads():
    payload = {
        "items": [
            {
                "full_name": "acme/platform",
                "homepage": "https://www.acme.io",
                "topics": ["devops"],
                "stargazers_count": 120,
                "description": "Platform tooling",
                "owner": {
                    "login": "acme",
                    "type": "Organization",
                    "html_url": "https://github.com/acme",
                    "url": "https://api.github.com/users/acme",
                },
            },
            {
                "full_name": "acme/other",
                "owner": {"login": "acme", "type": "Organization"},
            },
            {"full_name": "orphan/repo", "owner": {}},
        ]
    }
    source = GitHubLeadSource(
        "ghp_test", keywords=("devops",), transport=mock_transport({"search": payload})
    )
    leads = await source.discover(10)

    assert len(leads) == 1
    lead = leads[0]
    assert lead.lead_id == "github:acme"
    assert lead.domain == "acme.io"
    assert lead.company == "acme"
    assert "topic:devops" in lead.signals


@pytest.mark.asyncio
async def test_github_source_swallows_http_errors():
    source = GitHubLeadSource(
        "ghp_test", keywords=("devops",), transport=mock_transport({"search": 500})
    )
    assert await source.discover(5) == []


# ---------------------------------------------------------------------------
# Enrichers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_profile_enricher_without_token_is_noop(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    enricher = GitHubProfileEnricher("")
    lead = Lead(lead_id="github:acme", source="github", metadata={"github_login": "acme"})
    assert enricher.configured is False
    assert await enricher.enrich(lead) is False


@pytest.mark.asyncio
async def test_github_profile_enricher_adds_profile_data():
    profile = {
        "name": "Acme Inc",
        "email": "cto@acme.io",
        "company": "@acme",
        "blog": "https://acme.io",
        "location": "Berlin",
        "bio": "We build platforms",
        "followers": 900,
    }
    enricher = GitHubProfileEnricher(
        "ghp_test", transport=mock_transport({"users": profile})
    )
    lead = Lead(lead_id="github:acme", source="github", metadata={"github_login": "acme"})

    assert await enricher.enrich(lead) is True
    assert lead.email == "cto@acme.io"
    assert lead.company == "acme"
    assert lead.domain == "acme.io"
    assert "followers:900" in lead.signals


@pytest.mark.asyncio
async def test_github_profile_enricher_skips_non_github_leads():
    enricher = GitHubProfileEnricher("ghp_test")
    assert enricher.can_enrich(Lead(lead_id="x", source="other")) is False


@pytest.mark.asyncio
async def test_clearbit_enricher_without_key_is_noop(monkeypatch):
    monkeypatch.delenv("CLEARBIT_API_KEY", raising=False)
    enricher = ClearbitEnricher("")
    assert enricher.configured is False
    assert await enricher.enrich(qualified_lead()) is False


@pytest.mark.asyncio
async def test_clearbit_enricher_adds_firmographics():
    company = {
        "legalName": "Acme Incorporated",
        "domain": "acme.io",
        "location": "Berlin, DE",
        "metrics": {"employees": 240, "raised": 5000000},
        "category": {"industry": "Software", "sector": "Technology"},
    }
    enricher = ClearbitEnricher(
        "sk_test", transport=mock_transport({"companies": company})
    )
    lead = Lead(lead_id="l1", source="s", domain="acme.io")

    assert await enricher.enrich(lead) is True
    assert lead.company == "Acme Incorporated"
    assert lead.company_size == 240
    assert "industry:Software" in lead.signals


@pytest.mark.asyncio
async def test_clearbit_enricher_needs_a_domain():
    enricher = ClearbitEnricher("sk_test")
    assert enricher.can_enrich(Lead(lead_id="l1", source="s")) is False


@pytest.mark.asyncio
async def test_hunter_enricher_picks_best_confidence_contact():
    payload = {
        "data": {
            "organization": "Acme Inc",
            "emails": [
                {"value": "info@acme.io", "confidence": 72},
                {
                    "value": "cto@acme.io",
                    "confidence": 95,
                    "first_name": "Ada",
                    "last_name": "Byron",
                    "position": "CTO",
                },
                {"value": "low@acme.io", "confidence": 10},
                {"value": "broken", "confidence": 99},
            ],
        }
    }
    enricher = HunterEnricher(
        "hk_test", transport=mock_transport({"domain-search": payload})
    )
    lead = Lead(lead_id="l1", source="s", domain="acme.io")

    assert await enricher.enrich(lead) is True
    assert lead.email == "cto@acme.io"
    assert lead.name == "Ada Byron"
    assert lead.title == "CTO"


@pytest.mark.asyncio
async def test_hunter_enricher_rejects_low_confidence_only():
    payload = {"data": {"emails": [{"value": "info@acme.io", "confidence": 10}]}}
    enricher = HunterEnricher(
        "hk_test", transport=mock_transport({"domain-search": payload})
    )
    lead = Lead(lead_id="l1", source="s", domain="acme.io")
    assert await enricher.enrich(lead) is False
    assert lead.email == ""


@pytest.mark.asyncio
async def test_hunter_enricher_skips_leads_that_already_have_email():
    enricher = HunterEnricher("hk_test")
    assert enricher.can_enrich(qualified_lead()) is False


@pytest.mark.asyncio
async def test_enricher_swallows_http_errors():
    enricher = ClearbitEnricher("sk_test", transport=mock_transport({"companies": 502}))
    lead = Lead(lead_id="l1", source="s", domain="acme.io")
    assert await enricher.enrich(lead) is False


# ---------------------------------------------------------------------------
# Acquisition stream
# ---------------------------------------------------------------------------


def billing_routes(**overrides) -> dict[str, object]:
    routes: dict[str, object] = {
        "GET customers": {"data": []},
        "POST customers": {"id": "cus_1"},
        "invoiceitems": {"id": "ii_1"},
        "invoices/in_1/send": {
            "id": "in_1",
            "amount_due": 9900,
            "hosted_invoice_url": "https://pay.stripe.com/in_1",
        },
        "invoices": {"id": "in_1"},
    }
    routes.update(overrides)
    return routes


def build_stream(leads: list[Lead], routes: dict[str, object] | None = None, **kwargs):
    pipeline = LeadPipeline(sources=[StaticSource(leads)], qualify_score=55)
    return AcquisitionStream(
        client=stripe_stub(routes if routes is not None else billing_routes()),
        pipeline=pipeline,
        price_id=kwargs.pop("price_id", "price_acq"),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_acquisition_without_lead_source_is_noop():
    stream = AcquisitionStream(
        client=stripe_stub({}),
        pipeline=LeadPipeline(sources=[StaticSource([], configured=False)]),
        price_id="price_acq",
    )
    result = await stream.run()
    assert result.skipped is True
    assert "no lead source" in result.reason


@pytest.mark.asyncio
async def test_acquisition_invoices_qualified_lead():
    stream = build_stream([qualified_lead()])
    result = await stream.run()

    assert result.metrics["qualified"] == 1
    assert result.metrics["invoiced"] == 1
    assert result.metrics["customers_created"] == 1
    assert result.metrics["invoices_sent"] == 1
    topics = [topic for topic, _ in result.events]
    assert "revenue.lead_qualified" in topics
    assert "revenue.prospect_invoiced" in topics
    invoiced = [p for t, p in result.events if t == "revenue.prospect_invoiced"][0]
    assert invoiced["amount_usd"] == 99.0
    assert invoiced["hosted_invoice_url"] == "https://pay.stripe.com/in_1"


@pytest.mark.asyncio
async def test_acquisition_skips_unqualified_lead():
    weak = Lead(lead_id="weak", source="s", email="me@gmail.com")
    stream = build_stream([weak])
    result = await stream.run()

    assert result.metrics["qualified"] == 0
    assert result.metrics["invoiced"] == 0


@pytest.mark.asyncio
async def test_acquisition_without_price_reports_pipeline_only():
    stream = build_stream([qualified_lead()], price_id="")
    result = await stream.run()

    assert stream.billing_enabled is False
    assert result.metrics["qualified"] == 1
    assert result.metrics["invoiced"] == 0
    assert any("awaiting billing config" in a for a in result.actions)


@pytest.mark.asyncio
async def test_acquisition_never_bills_existing_customer():
    routes = billing_routes(**{"GET customers": {"data": [{"id": "cus_existing"}]}})
    stream = build_stream([qualified_lead()], routes)
    result = await stream.run()

    assert result.metrics["invoiced"] == 0
    assert result.metrics["customers_created"] == 0


@pytest.mark.asyncio
async def test_acquisition_treats_stripe_outage_as_existing_customer():
    routes = billing_routes(**{"GET customers": 500})
    stream = build_stream([qualified_lead()], routes)
    result = await stream.run()

    assert result.metrics["invoiced"] == 0


@pytest.mark.asyncio
async def test_acquisition_stops_at_max_invoices_per_cycle():
    leads = [
        qualified_lead(email=f"cto{i}@acme{i}.io") for i in range(4)
    ]
    for index, lead in enumerate(leads):
        lead.lead_id = f"github:acme{index}"
    stream = build_stream(leads, max_invoices_per_cycle=2)
    result = await stream.run()

    assert result.metrics["qualified"] == 4
    assert result.metrics["invoiced"] == 2


@pytest.mark.asyncio
async def test_acquisition_handles_failed_invoice_send():
    routes = billing_routes(**{"invoices/in_1/send": 500})
    stream = build_stream([qualified_lead()], routes)
    result = await stream.run()

    assert result.metrics["invoiced"] == 0
    assert result.metrics["customers_created"] == 1
    assert result.metrics["invoices_sent"] == 0


@pytest.mark.asyncio
async def test_acquisition_handles_customer_creation_failure():
    routes = billing_routes(**{"POST customers": 500})

    stream = AcquisitionStream(
        client=stripe_stub(routes),
        pipeline=LeadPipeline(sources=[StaticSource([qualified_lead()])]),
        price_id="price_acq",
    )
    result = await stream.run()
    assert result.metrics["invoiced"] == 0
    assert result.metrics["customers_created"] == 0


@pytest.mark.asyncio
async def test_acquisition_status_exposes_pipeline():
    stream = build_stream([qualified_lead()])
    await stream.run()
    status = stream.status()

    assert status["billing_enabled"] is True
    assert status["pipeline"]["qualified_total"] == 1
    assert status["pipeline"]["sources"][0]["id"] == "static"


# ---------------------------------------------------------------------------
# Outreach integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquisition_calls_outreach_for_qualified_leads(monkeypatch):
    """contact_all should be called with the qualified list from the pipeline."""
    contacted: list = []

    def fake_contact_all(qualified):
        contacted.extend(qualified)
        return [OutreachResult(lead.lead_id, "email", True, lead.email) for lead, _ in qualified]

    stream = build_stream([qualified_lead()])
    monkeypatch.setattr(stream.outreach_agent, "contact_all", fake_contact_all)

    result = await stream.run()

    assert len(contacted) == 1
    assert contacted[0][0].lead_id == "github:acme"
    assert any("Outreach sent" in a for a in result.actions)
    event_topics = [t for t, _ in result.events]
    assert "revenue.outreach_attempted" in event_topics
    outreach_event = next(p for t, p in result.events if t == "revenue.outreach_attempted")
    assert outreach_event["success"] is True
    assert outreach_event["channel"] == "email"


@pytest.mark.asyncio
async def test_acquisition_outreach_deduplication_across_cycles(monkeypatch):
    """Persistent outreach agent should not resend to the same lead twice."""
    sent_ids: list[str] = []

    def fake_contact(lead):
        if stream.outreach_agent.already_contacted(lead.lead_id):
            return None
        stream.outreach_agent._delivered[lead.lead_id] = None
        sent_ids.append(lead.lead_id)
        return OutreachResult(lead.lead_id, "email", True, lead.email)

    lead = qualified_lead()
    pipeline = LeadPipeline(sources=[StaticSource([lead])], qualify_score=55)
    pipeline._seen.clear()

    stream = AcquisitionStream(
        client=stripe_stub(billing_routes()),
        pipeline=pipeline,
        price_id="price_acq",
    )
    monkeypatch.setattr(stream.outreach_agent, "contact", fake_contact)

    result1 = await stream.run()
    assert sent_ids == ["github:acme"]
    assert any("Outreach sent" in a for a in result1.actions)

    pipeline._seen.clear()

    result2 = await stream.run()

    assert sent_ids == ["github:acme"]
    assert not any("Outreach sent" in a for a in result2.actions)

# Outreach — EmailChannel (Resend)
# ---------------------------------------------------------------------------


def _resend_transport(status: int, body: dict | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.resend.com":
            return httpx.Response(status, json=body or {})
        return httpx.Response(404, json={"error": "unexpected"})

    return httpx.MockTransport(handler)


def _email_channel(monkeypatch, transport: httpx.MockTransport) -> EmailChannel:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("OUTREACH_FROM_EMAIL", "outreach@garcar.io")
    channel = EmailChannel()

    def patched_post(url, **kwargs):
        return httpx.Client(transport=transport).post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", patched_post)
    return channel


def test_email_channel_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("OUTREACH_FROM_EMAIL", raising=False)
    channel = EmailChannel()
    assert channel.configured is False
    result = channel.send(qualified_lead())
    assert result.success is False
    assert "not configured" in result.detail


def test_email_channel_not_configured_missing_api_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("OUTREACH_FROM_EMAIL", "outreach@garcar.io")
    channel = EmailChannel()
    assert channel.configured is False


def test_email_channel_not_configured_missing_from_email(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("OUTREACH_FROM_EMAIL", raising=False)
    channel = EmailChannel()
    assert channel.configured is False


def test_email_channel_rejects_non_business_email(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("OUTREACH_FROM_EMAIL", "outreach@garcar.io")
    channel = EmailChannel()
    lead = Lead(lead_id="l1", source="s", email="person@gmail.com")
    result = channel.send(lead)
    assert result.success is False
    assert "business email" in result.detail


def test_email_channel_send_success(monkeypatch):
    transport = _resend_transport(200, {"id": "msg_abc123"})
    channel = _email_channel(monkeypatch, transport)
    result = channel.send(qualified_lead())
    assert result.success is True
    assert result.detail == "msg_abc123"
    assert result.channel == "email"


def test_email_channel_send_failure_non_2xx(monkeypatch):
    transport = _resend_transport(422, {"message": "invalid address"})
    channel = _email_channel(monkeypatch, transport)
    result = channel.send(qualified_lead())
    assert result.success is False
    assert result.detail != ""


def test_email_channel_send_failure_exception(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("OUTREACH_FROM_EMAIL", "outreach@garcar.io")
    channel = EmailChannel()

    def raise_exc(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", raise_exc)
    result = channel.send(qualified_lead())
    assert result.success is False
    assert "connection refused" in result.detail


def test_outreach_agent_default_channel_is_email():
    agent = OutreachAgent()
    assert any(c.id == "email" for c in agent.channels)


def test_outreach_agent_skips_already_contacted(monkeypatch):
    transport = _resend_transport(200, {"id": "msg_1"})
    channel = _email_channel(monkeypatch, transport)
    agent = OutreachAgent(channels=[channel])
    lead = qualified_lead()

    first = agent.contact(lead)
    assert first is not None and first.success is True
    second = agent.contact(lead)
    assert second is None  # skipped
    assert second is None  # skipped
