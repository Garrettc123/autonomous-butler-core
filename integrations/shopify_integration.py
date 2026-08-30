"""
Garcar Enterprise — Shopify Integration
Webhook listener: new orders trigger revenue ledger + Linear issues + Slack alerts.
"""
import os
import hmac
import hashlib
import base64
import json
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional
from event_bus_sdk import ButlerEventBus

app = FastAPI(title="Garcar Shopify Integration")
bus = ButlerEventBus()

SHOPIFY_SECRET = os.environ["SHOPIFY_WEBHOOK_SECRET"]

def verify_shopify_hmac(data: bytes, hmac_header: str) -> bool:
    digest = base64.b64encode(
        hmac.new(SHOPIFY_SECRET.encode(), data, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(digest, hmac_header)

@app.post("/webhook/shopify/orders")
async def shopify_order_webhook(
    request: Request,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_topic: Optional[str] = Header(None)
):
    payload = await request.body()
    if not verify_shopify_hmac(payload, x_shopify_hmac_sha256 or ""):
        raise HTTPException(status_code=401, detail="Invalid Shopify HMAC")

    data = json.loads(payload)
    topic = x_shopify_topic

    if topic == "orders/paid":
        order_id = data["id"]
        total = float(data["total_price"])
        customer = data.get("customer", {}).get("email", "unknown")

        await bus.emit("revenue.shopify_order", {
            "source": "shopify",
            "amount": total,
            "order_id": order_id,
            "customer": customer,
            "description": f"Shopify Order #{data['order_number']}"
        }, agents=["RevenueOpsAgent"])

        # Auto-create Linear fulfillment issue
        await bus.emit("linear.create_issue", {
            "title": f"Fulfill Order #{data['order_number']} — ${total:.2f}",
            "team": "Revenue",
            "priority": 2,
            "labels": ["shopify", "fulfillment"]
        }, agents=["PMAgent"])

    return {"status": "processed", "topic": topic}
