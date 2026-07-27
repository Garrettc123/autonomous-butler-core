"""Integration tests for the FastAPI application."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from src.main import app
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "agents" in data
    assert "version" in data
    assert len(data["agents"]) == 6


def test_agents_endpoint(client):
    resp = client.get("/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    names = {a["name"] for a in data["agents"]}
    assert names == {"devops", "revenue", "security", "pm", "support", "infrastructure"}


def test_get_specific_agent(client):
    resp = client.get("/agents/devops")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "devops"


def test_get_unknown_agent(client):
    resp = client.get("/agents/nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json().get("error", "").lower()


def test_events_endpoint(client):
    resp = client.get("/events")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert isinstance(data["events"], list)


def test_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents_running" in data
    assert "total_actions_today" in data
    assert "bus_events_total" in data


def test_dashboard_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Autonomous Butler" in resp.text
    assert "devops" in resp.text.lower()


def test_dashboard_shows_revenue_streams(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Revenue Streams" in resp.text
    assert "Payment Recovery" in resp.text


def test_revenue_streams_endpoint(client):
    resp = client.get("/revenue/streams")
    assert resp.status_code == 200
    data = resp.json()
    ids = {s["id"] for s in data["streams"]}
    assert ids == {
        "acquisition",
        "subscriptions",
        "usage_based",
        "one_time",
        "dunning",
        "expansion",
    }
    assert data["total"] == 6
    assert data["enabled"] == 6


def test_single_revenue_stream_endpoint(client):
    resp = client.get("/revenue/streams/dunning")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "dunning"
    assert data["enabled"] is True
    # No Stripe key in tests, so the stream reports itself as unconfigured.
    assert data["configured"] is False


def test_unknown_revenue_stream_endpoint(client):
    resp = client.get("/revenue/streams/nonexistent")
    assert resp.status_code == 404
    assert "not found" in resp.json().get("error", "").lower()


def test_metrics_includes_revenue_streams(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["revenue_streams_total"] == 6
    assert data["revenue_streams_enabled"] == 6
    assert "dunning" in data["revenue_streams"]
    assert data["revenue_streams"]["dunning"]["collect_count"] == 0


def test_revenue_agent_health_reports_streams(client):
    resp = client.get("/agents/revenue")
    assert resp.status_code == 200
    data = resp.json()
    assert data["streams_total"] == 6
    assert len(data["streams"]) == 6


def test_stripe_webhook_without_secret_configured(client, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    resp = client.post("/webhooks/stripe", content=b"{}")
    assert resp.status_code == 503


def test_stripe_webhook_rejects_invalid_signature(client, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    resp = client.post(
        "/webhooks/stripe", content=b'{"id":"evt_1"}', headers={"Stripe-Signature": "t=1,v1=bad"}
    )
    assert resp.status_code == 400


def test_stripe_webhook_accepts_valid_signature(client, monkeypatch):
    secret = "whsec_test"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    body = json.dumps({"id": "evt_1", "type": "invoice.payment_failed"}).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()

    resp = client.post(
        "/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": f"t={timestamp},v1={signature}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"received": True, "type": "invoice.payment_failed"}

    # The verified event must reach the bus for other agents to react to.
    events = client.get("/events?limit=100").json()["events"]
    assert any(e["topic"] == "stripe.invoice.payment_failed" for e in events)


def test_stripe_webhook_rejects_invalid_json(client, monkeypatch):
    secret = "whsec_test"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    body = b"not json"
    timestamp = int(time.time())
    signature = hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()

    resp = client.post(
        "/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": f"t={timestamp},v1={signature}"},
    )
    assert resp.status_code == 400
