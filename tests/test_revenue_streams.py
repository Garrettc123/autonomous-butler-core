"""Tests for the revenue stream abstraction and the built-in streams."""

import json
import time

import httpx
import pytest

from src.agents.revenue_agent import RevenueAgent, _parse_enabled_streams
from src.revenue import RevenueStream, StreamRegistry, StreamResult, registry
from src.revenue.streams.dunning import DunningStream
from src.revenue.streams.expansion import ExpansionStream
from src.revenue.streams.one_time import OneTimeStream
from src.revenue.streams.subscriptions import SubscriptionStream
from src.revenue.streams.usage_based import UsageBasedStream
from src.revenue.stripe_client import StripeClient, verify_webhook_signature
from src.bus import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def stub_client(routes: dict[str, object], *, key: str = "sk_test_123") -> StripeClient:
    """
    Build a StripeClient backed by a mock httpx transport.

    ``routes`` maps a URL path substring to either a dict (returned as a 200
    JSON body) or an int status code (returned as an error response).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        for fragment, response in routes.items():
            if fragment in request.url.path:
                if isinstance(response, int):
                    return httpx.Response(response, json={"error": "boom"})
                return httpx.Response(200, json=response)
        return httpx.Response(404, json={"error": "no stub for " + request.url.path})

    return StripeClient(key, transport=httpx.MockTransport(handler))


def subscription(sub_id: str, amount: int, interval: str = "month", quantity: int = 1) -> dict:
    return {
        "id": sub_id,
        "items": {
            "data": [
                {"quantity": quantity, "plan": {"amount": amount, "interval": interval}}
            ]
        },
    }


# ---------------------------------------------------------------------------
# RevenueStream base behaviour
# ---------------------------------------------------------------------------


class DummyStream(RevenueStream):
    id = "dummy"
    title = "Dummy"
    description = "test stream"

    def __init__(self, enabled=True, configured=True, raises=False, **_):
        super().__init__(enabled)
        self._configured = configured
        self._raises = raises

    def is_configured(self) -> bool:
        return self._configured

    def missing_config_reason(self) -> str:
        return "dummy not configured"

    async def collect(self) -> StreamResult:
        if self._raises:
            raise RuntimeError("kaboom")
        return StreamResult(self.id, metrics={"x": 1}, actions=["did a thing"])


@pytest.mark.asyncio
async def test_stream_run_happy_path():
    stream = DummyStream()
    result = await stream.run()
    assert result.skipped is False
    assert result.metrics == {"x": 1}
    assert stream.status()["collect_count"] == 1
    assert stream.status()["action_count"] == 1


@pytest.mark.asyncio
async def test_stream_run_disabled_is_noop():
    stream = DummyStream(enabled=False)
    result = await stream.run()
    assert result.skipped is True
    assert "disabled" in result.reason
    assert stream.status()["collect_count"] == 0


@pytest.mark.asyncio
async def test_stream_run_unconfigured_is_noop():
    stream = DummyStream(configured=False)
    result = await stream.run()
    assert result.skipped is True
    assert result.reason == "dummy not configured"


@pytest.mark.asyncio
async def test_stream_run_swallows_exceptions():
    stream = DummyStream(raises=True)
    result = await stream.run()
    assert result.skipped is True
    assert "kaboom" in result.reason
    assert stream.status()["error_count"] == 1


def test_stream_result_to_dict():
    result = StreamResult("s", metrics={"a": 1}, actions=["x"])
    data = result.to_dict()
    assert data["stream_id"] == "s"
    assert data["metrics"] == {"a": 1}
    assert data["skipped"] is False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_builds_all_streams():
    streams = registry.build(None, client=StripeClient(""))
    ids = {s.id for s in streams}
    assert ids == {"subscriptions", "usage_based", "one_time", "dunning", "expansion"}
    assert all(s.enabled for s in streams)


def test_registry_respects_enabled_subset():
    streams = registry.build({"dunning"}, client=StripeClient(""))
    enabled = {s.id for s in streams if s.enabled}
    assert enabled == {"dunning"}
    # Disabled streams are still built so they remain visible in the dashboard.
    assert len(streams) == 5


def test_registry_survives_failing_factory():
    reg = StreamRegistry()

    def broken(**_):
        raise ValueError("nope")

    reg.register("ok", DummyStream)
    reg.register("broken", broken)
    streams = reg.build(None)
    assert [s.id for s in streams] == ["dummy"]


# ---------------------------------------------------------------------------
# Subscription stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscription_stream_computes_mrr_and_arr():
    client = stub_client(
        {"subscriptions": {"data": [subscription("sub_1", 5000), subscription("sub_2", 2500)]}}
    )
    stream = SubscriptionStream(client=client)
    result = await stream.run()
    assert result.metrics["mrr_usd"] == 75.0
    assert result.metrics["arr_usd"] == 900.0
    assert result.metrics["active_subscriptions"] == 2
    assert result.events[0][0] == "revenue.mrr_snapshot"


@pytest.mark.asyncio
async def test_subscription_stream_normalizes_yearly_plans():
    client = stub_client({"subscriptions": {"data": [subscription("sub_1", 12000, "year")]}})
    stream = SubscriptionStream(client=client)
    result = await stream.run()
    assert result.metrics["mrr_usd"] == 10.0


@pytest.mark.asyncio
async def test_subscription_stream_respects_quantity():
    client = stub_client(
        {"subscriptions": {"data": [subscription("sub_1", 1000, quantity=3)]}}
    )
    stream = SubscriptionStream(client=client)
    result = await stream.run()
    assert result.metrics["mrr_usd"] == 30.0


@pytest.mark.asyncio
async def test_subscription_stream_reports_delta():
    client = stub_client({"subscriptions": {"data": [subscription("sub_1", 5000)]}})
    stream = SubscriptionStream(client=client)
    first = await stream.run()
    assert first.metrics["mrr_delta_usd"] == 50.0
    second = await stream.run()
    assert second.metrics["mrr_delta_usd"] == 0.0


@pytest.mark.asyncio
async def test_subscription_stream_without_key_is_noop():
    stream = SubscriptionStream(client=StripeClient(""))
    result = await stream.run()
    assert result.skipped is True
    assert "STRIPE_SECRET_KEY" in result.reason


@pytest.mark.asyncio
async def test_subscription_stream_handles_api_error():
    stream = SubscriptionStream(client=stub_client({"subscriptions": 500}))
    result = await stream.run()
    assert result.skipped is True
    assert "unavailable" in result.reason


# ---------------------------------------------------------------------------
# Usage-based stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_stream_flushes_pending_usage():
    client = stub_client({"usage_records": {"id": "mbur_1", "quantity": 10}})
    stream = UsageBasedStream(client=client)
    stream.record_usage("si_1", 4)
    stream.record_usage("si_1", 6)
    result = await stream.run()
    assert result.metrics["reported_this_cycle"] == 10
    assert result.metrics["pending_quantity"] == 0
    assert result.events[0][0] == "revenue.usage_reported"


@pytest.mark.asyncio
async def test_usage_stream_retains_usage_when_stripe_fails():
    stream = UsageBasedStream(client=stub_client({"usage_records": 500}))
    stream.record_usage("si_1", 7)
    result = await stream.run()
    assert result.metrics["reported_this_cycle"] == 0
    # Usage stays buffered so the next cycle retries instead of losing revenue.
    assert result.metrics["pending_quantity"] == 7


@pytest.mark.asyncio
async def test_usage_stream_ignores_invalid_usage():
    stream = UsageBasedStream(client=stub_client({}))
    stream.record_usage("", 5)
    stream.record_usage("si_1", 0)
    stream.record_usage("si_1", -3)
    result = await stream.run()
    assert result.metrics["pending_items"] == 0


@pytest.mark.asyncio
async def test_usage_stream_without_key_is_noop():
    stream = UsageBasedStream(client=StripeClient(""))
    stream.record_usage("si_1", 5)
    result = await stream.run()
    assert result.skipped is True


# ---------------------------------------------------------------------------
# One-time stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_time_stream_excludes_subscription_charges():
    client = stub_client(
        {
            "charges": {
                "data": [
                    {"amount": 5000, "amount_refunded": 0, "status": "succeeded"},
                    {
                        "amount": 9900,
                        "amount_refunded": 0,
                        "status": "succeeded",
                        "invoice": "in_1",
                    },
                    {"amount": 1000, "amount_refunded": 0, "status": "failed"},
                ]
            }
        }
    )
    stream = OneTimeStream(client=client)
    result = await stream.run()
    assert result.metrics["charge_count"] == 1
    assert result.metrics["net_usd"] == 50.0


@pytest.mark.asyncio
async def test_one_time_stream_subtracts_refunds():
    client = stub_client(
        {"charges": {"data": [{"amount": 5000, "amount_refunded": 1500, "status": "succeeded"}]}}
    )
    stream = OneTimeStream(client=client)
    result = await stream.run()
    assert result.metrics["gross_usd"] == 50.0
    assert result.metrics["refunded_usd"] == 15.0
    assert result.metrics["net_usd"] == 35.0


@pytest.mark.asyncio
async def test_one_time_stream_without_key_is_noop():
    stream = OneTimeStream(client=StripeClient(""))
    result = await stream.run()
    assert result.skipped is True


@pytest.mark.asyncio
async def test_one_time_stream_handles_api_error():
    stream = OneTimeStream(client=stub_client({"charges": 500}))
    result = await stream.run()
    assert result.skipped is True


# ---------------------------------------------------------------------------
# Dunning stream
# ---------------------------------------------------------------------------


def failed_invoice(invoice_id: str, amount: int = 5000) -> dict:
    return {"id": invoice_id, "amount_due": amount, "attempt_count": 2, "paid": False}


@pytest.mark.asyncio
async def test_dunning_stream_recovers_payment():
    client = stub_client(
        {
            "invoices/in_1/pay": {"status": "paid", "amount_paid": 5000},
            "invoices": {"data": [failed_invoice("in_1")]},
        }
    )
    stream = DunningStream(client=client)
    result = await stream.run()
    assert result.metrics["recovered_count"] == 1
    assert result.metrics["recovered_usd"] == 50.0
    assert result.metrics["recovery_rate"] == 1.0
    assert result.events[0][0] == "revenue.payment_recovered"


@pytest.mark.asyncio
async def test_dunning_stream_backs_off_between_retries():
    client = stub_client(
        {
            "invoices/in_1/pay": {"status": "open", "paid": False},
            "invoices": {"data": [failed_invoice("in_1")]},
        }
    )
    stream = DunningStream(client=client)
    await stream.run()
    assert stream._retry_state["in_1"]["attempts"] == 1

    # Immediately re-running must not retry again: backoff has not elapsed.
    await stream.run()
    assert stream._retry_state["in_1"]["attempts"] == 1

    # Once the backoff window passes, the next attempt is made.
    stream._retry_state["in_1"]["next_attempt_at"] = time.time() - 1
    await stream.run()
    assert stream._retry_state["in_1"]["attempts"] == 2


@pytest.mark.asyncio
async def test_dunning_stream_gives_up_after_max_retries():
    from src.revenue.streams.dunning import MAX_RETRIES

    client = stub_client(
        {
            "invoices/in_1/pay": {"status": "open", "paid": False},
            "invoices": {"data": [failed_invoice("in_1")]},
        }
    )
    stream = DunningStream(client=client)
    for _ in range(MAX_RETRIES + 3):
        stream._retry_state.setdefault("in_1", {"attempts": 0, "next_attempt_at": 0})
        stream._retry_state["in_1"]["next_attempt_at"] = time.time() - 1
        await stream.run()
    assert stream._retry_state["in_1"]["attempts"] == MAX_RETRIES


@pytest.mark.asyncio
async def test_dunning_stream_ignores_paid_invoices():
    client = stub_client(
        {"invoices": {"data": [{"id": "in_2", "amount_due": 0, "attempt_count": 1, "paid": True}]}}
    )
    stream = DunningStream(client=client)
    result = await stream.run()
    assert result.metrics["failed_invoices"] == 0
    assert result.metrics["retries_attempted"] == 0


@pytest.mark.asyncio
async def test_dunning_stream_without_key_is_noop():
    stream = DunningStream(client=StripeClient(""))
    result = await stream.run()
    assert result.skipped is True


@pytest.mark.asyncio
async def test_dunning_stream_handles_api_error():
    stream = DunningStream(client=stub_client({"invoices": 500}))
    result = await stream.run()
    assert result.skipped is True


# ---------------------------------------------------------------------------
# Expansion stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expansion_stream_raises_churn_alert():
    cancelled = {"data": [{"id": f"sub_{i}"} for i in range(4)]}

    def handler(request: httpx.Request) -> httpx.Response:
        if "canceled" in str(request.url):
            return httpx.Response(200, json=cancelled)
        return httpx.Response(200, json={"data": []})

    client = StripeClient("sk_test", transport=httpx.MockTransport(handler))
    stream = ExpansionStream(client=client)
    result = await stream.run()
    assert result.metrics["cancellations"] == 4
    assert any(topic == "revenue.churn_alert" for topic, _ in result.events)


@pytest.mark.asyncio
async def test_expansion_stream_below_threshold_has_no_alert():
    def handler(request: httpx.Request) -> httpx.Response:
        if "canceled" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "sub_1"}]})
        return httpx.Response(200, json={"data": []})

    client = StripeClient("sk_test", transport=httpx.MockTransport(handler))
    stream = ExpansionStream(client=client)
    result = await stream.run()
    assert result.metrics["cancellations"] == 1
    assert result.events == []
    assert result.actions == ["1 cancellation(s) recorded"]


@pytest.mark.asyncio
async def test_expansion_stream_detects_seat_growth():
    state = {"seats": 2}

    def handler(request: httpx.Request) -> httpx.Response:
        if "canceled" in str(request.url):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(
            200, json={"data": [subscription("sub_1", 1000, quantity=state["seats"])]}
        )

    client = StripeClient("sk_test", transport=httpx.MockTransport(handler))
    stream = ExpansionStream(client=client)

    first = await stream.run()
    assert first.metrics["upsell_opportunities"] == 0

    state["seats"] = 5
    second = await stream.run()
    assert second.metrics["upsell_opportunities"] == 1
    assert any(topic == "revenue.upsell_opportunity" for topic, _ in second.events)


@pytest.mark.asyncio
async def test_expansion_stream_without_key_is_noop():
    stream = ExpansionStream(client=StripeClient(""))
    result = await stream.run()
    assert result.skipped is True


@pytest.mark.asyncio
async def test_expansion_stream_handles_api_error():
    stream = ExpansionStream(client=stub_client({"subscriptions": 500}))
    result = await stream.run()
    assert result.metrics["cancellations"] == 0
    assert result.metrics["upsell_opportunities"] == 0


# ---------------------------------------------------------------------------
# RevenueAgent orchestration
# ---------------------------------------------------------------------------


def test_parse_enabled_streams():
    assert _parse_enabled_streams("") is None
    assert _parse_enabled_streams("all") is None
    assert _parse_enabled_streams("dunning, one_time") == {"dunning", "one_time"}


def test_revenue_agent_builds_all_streams():
    agent = RevenueAgent(stripe_secret_key="")
    assert len(agent.streams) == 5
    assert agent.get_stream("dunning") is not None
    assert agent.get_stream("nope") is None


def test_revenue_agent_health_exposes_streams():
    agent = RevenueAgent(stripe_secret_key="")
    h = agent.health()
    assert h["stripe_configured"] is False
    assert h["last_mrr_usd"] == 0.0
    assert h["streams_total"] == 5
    assert len(h["streams"]) == 5


def test_revenue_agent_enabled_subset():
    agent = RevenueAgent(stripe_secret_key="", enabled_streams={"subscriptions"})
    assert agent.health()["streams_enabled"] == 1


@pytest.mark.asyncio
async def test_revenue_agent_records_actions_and_emits_events():
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("revenue.mrr_snapshot", handler)

    client = stub_client({"subscriptions": {"data": [subscription("sub_1", 5000)]}})
    agent = RevenueAgent(event_bus=bus, streams=[SubscriptionStream(client=client)])
    await agent.run_cycle()

    assert len(agent.actions_today()) == 1
    assert agent.actions_today()[0]["details"]["stream"] == "subscriptions"
    assert len(received) == 1
    assert received[0].payload["stream"] == "subscriptions"
    assert agent.health()["last_mrr_usd"] == 50.0


@pytest.mark.asyncio
async def test_revenue_agent_cycle_without_key_records_nothing():
    agent = RevenueAgent(stripe_secret_key="")
    await agent.run_cycle()
    assert agent.actions_today() == []


@pytest.mark.asyncio
async def test_revenue_agent_one_broken_stream_does_not_stop_others():
    client = stub_client({"subscriptions": {"data": [subscription("sub_1", 5000)]}})
    agent = RevenueAgent(
        streams=[DummyStream(raises=True), SubscriptionStream(client=client)]
    )
    await agent.run_cycle()
    # The healthy stream still recorded its action.
    assert len(agent.actions_today()) == 1


# ---------------------------------------------------------------------------
# Stripe client + webhook signature verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stripe_client_returns_none_without_key():
    client = StripeClient("")
    assert await client.get("subscriptions") is None
    assert await client.post("invoices/in_1/pay") is None


def sign(payload: bytes, secret: str, timestamp: int) -> str:
    import hashlib
    import hmac

    signature = hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def test_webhook_signature_valid():
    payload = json.dumps({"id": "evt_1", "type": "invoice.paid"}).encode()
    now = int(time.time())
    assert verify_webhook_signature(payload, sign(payload, "whsec_x", now), "whsec_x") is True


def test_webhook_signature_rejects_wrong_secret():
    payload = b'{"id":"evt_1"}'
    now = int(time.time())
    assert verify_webhook_signature(payload, sign(payload, "other", now), "whsec_x") is False


def test_webhook_signature_rejects_tampered_payload():
    payload = b'{"id":"evt_1"}'
    now = int(time.time())
    header = sign(payload, "whsec_x", now)
    assert verify_webhook_signature(b'{"id":"evt_2"}', header, "whsec_x") is False


def test_webhook_signature_rejects_replayed_timestamp():
    payload = b'{"id":"evt_1"}'
    old = int(time.time()) - 10_000
    assert verify_webhook_signature(payload, sign(payload, "whsec_x", old), "whsec_x") is False


def test_webhook_signature_rejects_malformed_headers():
    payload = b'{}'
    assert verify_webhook_signature(payload, "", "whsec_x") is False
    assert verify_webhook_signature(payload, "garbage", "whsec_x") is False
    assert verify_webhook_signature(payload, "t=abc,v1=def", "whsec_x") is False
    assert verify_webhook_signature(payload, "t=123", "whsec_x") is False


def test_webhook_signature_rejects_when_secret_missing():
    assert verify_webhook_signature(b"{}", "t=1,v1=x", "") is False
