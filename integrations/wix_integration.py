"""
Garcar Enterprise — Wix Integration
Manages Wix storefront products, orders, and contacts via Wix REST API.
Uses Wix API Keys (server-to-server) — no OAuth required for server flows.
"""
import os
import aiohttp
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

WIX_API_BASE = "https://www.wixapis.com"
WIX_HEADERS = {
    "Authorization": os.environ.get("WIX_API_KEY", ""),
    "wix-site-id": os.environ.get("WIX_SITE_ID", ""),
    "Content-Type": "application/json"
}

class GarcarWix:
    async def get_orders(self, limit: int = 50) -> list:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{WIX_API_BASE}/ecom/v1/orders",
                             headers=WIX_HEADERS, params={"limit": limit}) as r:
                data = await r.json()
                return data.get("orders", [])

    async def create_product(self, name: str, price: float, description: str = "") -> dict:
        payload = {"product": {"name": name, "productType": "digital",
                               "description": description,
                               "price": {"price": str(price)}}}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{WIX_API_BASE}/catalog/v1/products",
                              headers=WIX_HEADERS, json=payload) as r:
                data = await r.json()
                product = data.get("product", {})
                await bus.emit("wix.product_created", {"id": product.get("id"), "name": name, "price": price}, agents=["RevenueOpsAgent"])
                return product

    async def sync_contacts_to_hubspot(self) -> int:
        """Pull Wix contacts and push to HubSpot CRM via event bus."""
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{WIX_API_BASE}/contacts/v4/contacts",
                             headers=WIX_HEADERS) as r:
                data = await r.json()
                contacts = data.get("contacts", [])
                for c in contacts:
                    await bus.emit("hubspot.upsert_contact", {
                        "email": c.get("primaryInfo", {}).get("email", ""),
                        "firstname": c.get("info", {}).get("name", {}).get("first", ""),
                        "lastname": c.get("info", {}).get("name", {}).get("last", ""),
                        "source": "wix"
                    }, agents=["RevenueOpsAgent"])
                return len(contacts)

wix = GarcarWix()
