"""
FastAPI billing router.

Mounts at /billing and exposes:
  POST /billing/subscribe  – create a Stripe Checkout session
  POST /billing/webhook    – handle Stripe webhook events
  GET  /billing/status     – return the caller's subscription status
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from billing.stripe_billing import (
    create_checkout_session,
    create_customer,
    handle_webhook_event,
    verify_webhook_signature,
)
from tenants.provisioner import TenantProvisioner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SubscribeRequest(BaseModel):
    email: str
    name: str = ""
    tier: str  # starter | growth | enterprise
    success_url: str
    cancel_url: str


class SubscribeResponse(BaseModel):
    checkout_url: str
    session_id: str
    customer_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(body: SubscribeRequest) -> SubscribeResponse:
    """
    Create a Stripe customer (if needed) and return a Checkout session URL.
    The client should redirect the user to ``checkout_url`` to complete payment.
    """
    try:
        customer = create_customer(email=body.email, name=body.name)
        session = create_checkout_session(
            tier=body.tier,
            customer_id=customer["id"],
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return SubscribeResponse(
        checkout_url=session["url"],
        session_id=session["id"],
        customer_id=customer["id"],
    )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
) -> dict[str, Any]:
    """
    Receive and process Stripe webhook events.

    Verifies the HMAC-SHA256 signature before dispatching to the appropriate
    handler (subscription created, invoice paid, subscription deleted).
    """
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return JSONResponse({"error": "webhook secret not configured"}, status_code=503)

    raw_body = await request.body()
    if not verify_webhook_signature(raw_body, stripe_signature, secret):
        return JSONResponse({"error": "invalid signature"}, status_code=400)

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON payload"}, status_code=400)

    result = handle_webhook_event(event)
    return {"received": True, **result}


@router.get("/status")
async def billing_status(stripe_customer_id: str) -> dict[str, Any]:
    """
    Return the subscription status for a given Stripe customer ID.

    Query parameter: ``stripe_customer_id``
    """
    provisioner = TenantProvisioner()
    tenant = provisioner.get_by_customer(stripe_customer_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="No tenant found for this customer")
    return {
        "tenant_id": tenant["tenant_id"],
        "tier": tenant["tier"],
        "status": tenant["status"],
        "stripe_customer_id": tenant["stripe_customer_id"],
        "created_at": tenant["created_at"],
    }
