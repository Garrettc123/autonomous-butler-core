"""
Tests for billing flows: Stripe Billing and multi-tenant provisioner.

All external calls (Stripe API, Supabase REST) are mocked so the tests
run without network access or real API keys.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stripe_sig(secret: str, body: bytes) -> str:
    timestamp = int(time.time())
    signed = str(timestamp).encode() + b"." + body
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


# ---------------------------------------------------------------------------
# billing.stripe_billing unit tests
# ---------------------------------------------------------------------------


class TestVerifyWebhookSignature:
    def _sign(self, secret: str, body: bytes) -> str:
        return _make_stripe_sig(secret, body)

    def test_valid_signature(self):
        from billing.stripe_billing import verify_webhook_signature

        secret = "whsec_test"
        body = b'{"id":"evt_1","type":"invoice.paid"}'
        sig = self._sign(secret, body)
        assert verify_webhook_signature(body, sig, secret) is True

    def test_wrong_secret(self):
        from billing.stripe_billing import verify_webhook_signature

        body = b'{"id":"evt_1"}'
        sig = self._sign("correct_secret", body)
        assert verify_webhook_signature(body, sig, "wrong_secret") is False

    def test_malformed_header(self):
        from billing.stripe_billing import verify_webhook_signature

        assert verify_webhook_signature(b"{}", "not-a-valid-header", "secret") is False

    def test_expired_timestamp(self):
        from billing.stripe_billing import verify_webhook_signature

        secret = "whsec_test"
        body = b"{}"
        old_ts = int(time.time()) - 400  # > 5 minutes ago
        signed = str(old_ts).encode() + b"." + body
        sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        header = f"t={old_ts},v1={sig}"
        assert verify_webhook_signature(body, header, secret) is False


class TestCreateCustomer:
    def test_creates_customer(self):
        from billing.stripe_billing import create_customer

        mock_customer = MagicMock()
        mock_customer.id = "cus_abc123"

        mock_client = MagicMock()
        mock_client.customers.create.return_value = mock_customer

        with patch("billing.stripe_billing._stripe_client", return_value=mock_client):
            result = create_customer("a@b.com", name="Alice")

        mock_client.customers.create.assert_called_once()
        call_params = mock_client.customers.create.call_args[0][0]
        assert call_params["email"] == "a@b.com"
        assert call_params["name"] == "Alice"
        assert result["id"] == "cus_abc123"


class TestCreateCheckoutSession:
    def test_valid_tier(self):
        from billing.stripe_billing import create_checkout_session

        mock_session = MagicMock()
        mock_session.id = "cs_test"
        mock_session.url = "https://checkout.stripe.com/test"
        mock_session.__iter__ = lambda self: iter({"id": "cs_test", "url": mock_session.url}.items())

        mock_client = MagicMock()
        mock_client.checkout.sessions.create.return_value = mock_session

        with (
            patch("billing.stripe_billing._stripe_client", return_value=mock_client),
            patch("billing.stripe_billing._tier_price_id", return_value="price_starter"),
        ):
            result = create_checkout_session(
                tier="starter",
                customer_id="cus_abc",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
            )

        mock_client.checkout.sessions.create.assert_called_once()

    def test_invalid_tier_raises(self):
        from billing.stripe_billing import create_checkout_session

        with pytest.raises(ValueError, match="Unknown tier"):
            create_checkout_session("diamond", "cus_x", "https://ok", "https://cancel")

    def test_missing_price_id_raises(self):
        from billing.stripe_billing import create_checkout_session

        mock_client = MagicMock()
        with (
            patch("billing.stripe_billing._stripe_client", return_value=mock_client),
            patch("billing.stripe_billing._tier_price_id", return_value=""),
        ):
            with pytest.raises(RuntimeError, match="not configured"):
                create_checkout_session("growth", "cus_x", "https://ok", "https://cancel")


class TestHandleWebhookEvent:
    def test_subscription_created(self):
        from billing.stripe_billing import handle_webhook_event

        mock_provisioner = MagicMock()
        mock_provisioner.provision.return_value = {"tenant_id": "t-001"}

        event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_abc",
                    "customer": "cus_abc",
                    "metadata": {"tier": "growth"},
                    "items": {"data": []},
                }
            },
        }

        with patch("billing.stripe_billing.TenantProvisioner", return_value=mock_provisioner):
            result = handle_webhook_event(event)

        assert result["handled"] is True
        assert result["action"] == "tenant_provisioned"
        mock_provisioner.provision.assert_called_once_with(
            stripe_customer_id="cus_abc",
            stripe_subscription_id="sub_abc",
            tier="growth",
        )

    def test_invoice_paid(self):
        from billing.stripe_billing import handle_webhook_event

        mock_provisioner = MagicMock()
        event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_001",
                    "customer": "cus_abc",
                    "amount_paid": 500000,
                }
            },
        }

        with patch("billing.stripe_billing.TenantProvisioner", return_value=mock_provisioner):
            result = handle_webhook_event(event)

        assert result["handled"] is True
        assert result["action"] == "invoice_recorded"
        assert result["amount_paid"] == 500000

    def test_subscription_deleted(self):
        from billing.stripe_billing import handle_webhook_event

        mock_provisioner = MagicMock()
        event = {
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_abc", "customer": "cus_abc"}},
        }

        with patch("billing.stripe_billing.TenantProvisioner", return_value=mock_provisioner):
            result = handle_webhook_event(event)

        assert result["handled"] is True
        assert result["action"] == "tenant_deprovisioned"
        mock_provisioner.deprovision.assert_called_once_with(
            stripe_customer_id="cus_abc",
            stripe_subscription_id="sub_abc",
        )

    def test_unknown_event_not_handled(self):
        from billing.stripe_billing import handle_webhook_event

        result = handle_webhook_event({"type": "charge.refunded", "data": {"object": {}}})
        assert result["handled"] is False


# ---------------------------------------------------------------------------
# tenants.provisioner unit tests
# ---------------------------------------------------------------------------


class TestTenantProvisioner:
    def _provisioner(self):
        from tenants.provisioner import TenantProvisioner

        return TenantProvisioner(supabase_url="https://fake.supabase.co", supabase_key="fake_key")

    def test_provision_inserts_row(self):
        p = self._provisioner()
        inserted: list[dict] = []

        def fake_insert(table, row):
            inserted.append((table, row))
            return [row]

        p._insert = fake_insert  # type: ignore[method-assign]

        tenant = p.provision(
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
            tier="starter",
        )
        assert tenant["tier"] == "starter"
        assert tenant["status"] == "active"
        assert tenant["stripe_customer_id"] == "cus_1"
        # Should have inserted into tenants AND tenant_events
        tables = [t for t, _ in inserted]
        assert "tenants" in tables
        assert "tenant_events" in tables

    def test_deprovision_patches_status(self):
        p = self._provisioner()
        patched: list[dict] = []

        def fake_patch(table, filters, data):
            patched.append((table, filters, data))
            return []

        p._patch = fake_patch  # type: ignore[method-assign]
        p._insert = lambda *a, **kw: []  # type: ignore[method-assign]

        p.deprovision(stripe_customer_id="cus_1", stripe_subscription_id="sub_1")
        assert any(d == {"status": "cancelled"} for _, _, d in patched)

    def test_no_supabase_config_skips_gracefully(self):
        from tenants.provisioner import TenantProvisioner

        p = TenantProvisioner(supabase_url="", supabase_key="")
        # Should not raise even without credentials
        p.provision("cus_noop", "sub_noop", "enterprise")

    def test_get_by_customer_returns_none_when_not_found(self):
        p = self._provisioner()
        p._select = lambda *a, **kw: []  # type: ignore[method-assign]
        assert p.get_by_customer("cus_missing") is None

    def test_get_by_customer_returns_row(self):
        p = self._provisioner()
        row = {"tenant_id": "t-1", "tier": "growth", "status": "active", "stripe_customer_id": "cus_1", "created_at": "now"}
        p._select = lambda *a, **kw: [row]  # type: ignore[method-assign]
        assert p.get_by_customer("cus_1") == row


# ---------------------------------------------------------------------------
# FastAPI billing endpoint integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from src.main import app

    with TestClient(app) as c:
        yield c


class TestBillingEndpoints:
    def test_subscribe_missing_stripe_key(self, client):
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": ""}):
            resp = client.post(
                "/billing/subscribe",
                json={
                    "email": "test@example.com",
                    "tier": "starter",
                    "success_url": "https://example.com/ok",
                    "cancel_url": "https://example.com/cancel",
                },
            )
        assert resp.status_code == 503

    def test_subscribe_invalid_tier(self, client):
        mock_customer = MagicMock()
        mock_customer.id = "cus_test"
        mock_client = MagicMock()
        mock_client.customers.create.return_value = mock_customer

        with (
            patch("billing.stripe_billing._stripe_client", return_value=mock_client),
        ):
            resp = client.post(
                "/billing/subscribe",
                json={
                    "email": "test@example.com",
                    "tier": "ultra",
                    "success_url": "https://example.com/ok",
                    "cancel_url": "https://example.com/cancel",
                },
            )
        assert resp.status_code == 400
        assert "Unknown tier" in resp.json()["detail"]

    def test_subscribe_success(self, client):
        mock_customer = MagicMock()
        mock_customer.id = "cus_abc"

        mock_session = MagicMock()
        mock_session.id = "cs_test"
        mock_session.url = "https://checkout.stripe.com/test"

        mock_client = MagicMock()
        mock_client.customers.create.return_value = mock_customer
        mock_client.checkout.sessions.create.return_value = mock_session

        with (
            patch("billing.stripe_billing._stripe_client", return_value=mock_client),
            patch("billing.stripe_billing._tier_price_id", return_value="price_starter"),
        ):
            resp = client.post(
                "/billing/subscribe",
                json={
                    "email": "user@example.com",
                    "tier": "starter",
                    "success_url": "https://example.com/ok",
                    "cancel_url": "https://example.com/cancel",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["checkout_url"] == "https://checkout.stripe.com/test"
        assert data["session_id"] == "cs_test"
        assert data["customer_id"] == "cus_abc"

    def test_webhook_no_secret(self, client, monkeypatch):
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        resp = client.post("/billing/webhook", content=b"{}")
        assert resp.status_code == 503

    def test_webhook_invalid_signature(self, client, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
        resp = client.post(
            "/billing/webhook",
            content=b'{"id":"evt_1"}',
            headers={"Stripe-Signature": "t=1,v1=bad"},
        )
        assert resp.status_code == 400

    def test_webhook_valid_subscription_created(self, client, monkeypatch):
        secret = "whsec_test"
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)

        event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": "sub_1",
                    "customer": "cus_1",
                    "metadata": {"tier": "starter"},
                    "items": {"data": []},
                }
            },
        }
        body = json.dumps(event).encode()
        sig = _make_stripe_sig(secret, body)

        mock_provisioner = MagicMock()
        mock_provisioner.provision.return_value = {"tenant_id": "t-001"}

        with patch("billing.stripe_billing.TenantProvisioner", return_value=mock_provisioner):
            resp = client.post(
                "/billing/webhook",
                content=body,
                headers={"Stripe-Signature": sig},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["received"] is True
        assert data["handled"] is True

    def test_billing_status_not_found(self, client):
        from tenants.provisioner import TenantProvisioner

        with patch.object(TenantProvisioner, "get_by_customer", return_value=None):
            resp = client.get("/billing/status?stripe_customer_id=cus_missing")
        assert resp.status_code == 404

    def test_billing_status_found(self, client):
        from tenants.provisioner import TenantProvisioner

        row = {
            "tenant_id": "t-001",
            "tier": "growth",
            "status": "active",
            "stripe_customer_id": "cus_1",
            "created_at": "2024-01-01T00:00:00Z",
        }
        with patch.object(TenantProvisioner, "get_by_customer", return_value=row):
            resp = client.get("/billing/status?stripe_customer_id=cus_1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "growth"
        assert data["status"] == "active"
