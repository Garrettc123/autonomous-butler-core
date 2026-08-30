"""
Stripe Billing integration for Autonomous Butler Core.

Handles customer creation, Stripe Checkout session creation for three
subscription tiers, and webhook event processing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

import stripe

from tenants.provisioner import TenantProvisioner

logger = logging.getLogger(__name__)

TIER_AMOUNTS: dict[str, int] = {
    "starter": 250000,   # $2,500/mo in cents
    "growth": 500000,    # $5,000/mo in cents
    "enterprise": 1000000,  # $10,000/mo in cents
}


def _tier_price_id(tier: str) -> str:
    """Return the Stripe Price ID for a given tier, read from env at call time."""
    return os.getenv(f"STRIPE_PRICE_{tier.upper()}", "")


def _stripe_client() -> stripe.StripeClient:
    api_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not api_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    return stripe.StripeClient(api_key)


def create_customer(email: str, name: str = "", metadata: dict[str, str] | None = None) -> dict[str, Any]:
    """Create a Stripe customer and return the customer object."""
    client = _stripe_client()
    params: dict[str, Any] = {"email": email}
    if name:
        params["name"] = name
    if metadata:
        params["metadata"] = metadata
    customer = client.customers.create(params)
    logger.info("Created Stripe customer %s for %s", customer.id, email)
    return {"id": customer.id, "email": email, "name": name}


def create_checkout_session(
    tier: str,
    customer_id: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    """Create a Stripe Checkout session for the given subscription tier."""
    tier = tier.lower()
    valid_tiers = ("starter", "growth", "enterprise")
    if tier not in valid_tiers:
        raise ValueError(f"Unknown tier '{tier}'. Must be one of: {list(valid_tiers)}")

    price_id = _tier_price_id(tier)
    if not price_id:
        raise RuntimeError(f"STRIPE_PRICE_{tier.upper()} is not configured")

    client = _stripe_client()
    session = client.checkout.sessions.create({
        "mode": "subscription",
        "customer": customer_id,
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"tier": tier},
    })
    logger.info("Created checkout session %s for customer %s tier=%s", session.id, customer_id, tier)
    return {"id": session.id, "url": session.url}


def verify_webhook_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify a Stripe webhook signature (HMAC-SHA256)."""
    try:
        parts = {k: v for k, v in (p.split("=", 1) for p in sig_header.split(","))}
        timestamp = parts.get("t", "")
        v1_sig = parts.get("v1", "")
        if not timestamp or not v1_sig:
            return False
        signed_payload = timestamp.encode() + b"." + payload
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1_sig):
            return False
        # Reject events older than 5 minutes
        if abs(int(time.time()) - int(timestamp)) > 300:
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


def handle_webhook_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Dispatch a verified Stripe webhook event to the appropriate handler.

    Returns a dict with ``handled`` bool and an optional ``action`` string.
    """
    event_type: str = event.get("type", "")
    data_object: dict[str, Any] = event.get("data", {}).get("object", {})

    handlers = {
        "customer.subscription.created": _handle_subscription_created,
        "invoice.paid": _handle_invoice_paid,
        "customer.subscription.deleted": _handle_subscription_deleted,
    }

    handler = handlers.get(event_type)
    if handler is None:
        logger.debug("No handler for Stripe event type '%s'", event_type)
        return {"handled": False, "event_type": event_type}

    try:
        result = handler(data_object)
        return {"handled": True, "event_type": event_type, **result}
    except Exception as exc:  # noqa: BLE001
        logger.error("Error handling Stripe event '%s': %s", event_type, exc)
        return {"handled": False, "event_type": event_type, "error": str(exc)}


# ---------------------------------------------------------------------------
# Private event handlers
# ---------------------------------------------------------------------------

def _handle_subscription_created(subscription: dict[str, Any]) -> dict[str, Any]:
    """Provision tenant on new subscription."""
    customer_id: str = subscription.get("customer", "")
    subscription_id: str = subscription.get("id", "")
    tier = _tier_from_subscription(subscription)

    provisioner = TenantProvisioner()
    tenant = provisioner.provision(
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        tier=tier,
    )
    logger.info("Provisioned tenant %s for customer %s (tier=%s)", tenant["tenant_id"], customer_id, tier)
    return {"action": "tenant_provisioned", "tenant_id": tenant["tenant_id"]}


def _handle_invoice_paid(invoice: dict[str, Any]) -> dict[str, Any]:
    """Record successful payment for a tenant."""
    customer_id: str = invoice.get("customer", "")
    amount_paid: int = invoice.get("amount_paid", 0)
    provisioner = TenantProvisioner()
    provisioner.record_event(
        stripe_customer_id=customer_id,
        event_type="invoice.paid",
        payload={"amount_paid": amount_paid, "invoice_id": invoice.get("id", "")},
    )
    logger.info("Invoice paid for customer %s, amount=%d cents", customer_id, amount_paid)
    return {"action": "invoice_recorded", "amount_paid": amount_paid}


def _handle_subscription_deleted(subscription: dict[str, Any]) -> dict[str, Any]:
    """Deprovision tenant on subscription cancellation."""
    customer_id: str = subscription.get("customer", "")
    subscription_id: str = subscription.get("id", "")
    provisioner = TenantProvisioner()
    provisioner.deprovision(
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
    )
    logger.info("Deprovisioned tenant for customer %s", customer_id)
    return {"action": "tenant_deprovisioned"}


def _tier_from_subscription(subscription: dict[str, Any]) -> str:
    """Derive the tier name from a Stripe subscription object."""
    # Check metadata first
    metadata = subscription.get("metadata", {})
    if metadata.get("tier"):
        return metadata["tier"].lower()

    # Fall back to matching price ID
    items = subscription.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else ""
    for t in ("starter", "growth", "enterprise"):
        if _tier_price_id(t) and price_id == _tier_price_id(t):
            return t
    raise ValueError(
        f"Cannot determine tier for subscription {subscription.get('id', '?')}: "
        f"no matching price ID and no metadata.tier set."
    )
