"""
Garcar Enterprise — HubSpot Integration
CRM: upsert contacts, create deals, move pipeline stages.
Uses HubSpot Private App token (no OAuth needed for server-to-server).
"""
import os
import aiohttp
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

HUBSPOT_BASE = "https://api.hubapi.com"
HUBSPOT_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN', '')}",
    "Content-Type": "application/json"
}

class GarcarHubSpot:
    async def upsert_contact(self, email: str, properties: dict) -> dict:
        payload = {"properties": {"email": email, **properties}}
        async with aiohttp.ClientSession() as s:
            # Try update first, then create
            async with s.patch(f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{email}?idProperty=email",
                               headers=HUBSPOT_HEADERS, json=payload) as r:
                if r.status == 404:
                    async with s.post(f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
                                      headers=HUBSPOT_HEADERS, json=payload) as r2:
                        return await r2.json()
                return await r.json()

    async def create_deal(self, deal_name: str, amount: float, contact_email: str, stage: str = None) -> dict:
        stage_id = stage or os.environ.get("HUBSPOT_STAGE_QUALIFIED", "")
        payload = {"properties": {
            "dealname": deal_name,
            "amount": str(amount),
            "pipeline": os.environ.get("HUBSPOT_PIPELINE_ID", "default"),
            "dealstage": stage_id
        }}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{HUBSPOT_BASE}/crm/v3/objects/deals",
                              headers=HUBSPOT_HEADERS, json=payload) as r:
                data = await r.json()
                deal_id = data.get("id", "")
                await bus.emit("hubspot.deal_created", {
                    "deal_id": deal_id, "name": deal_name,
                    "amount": amount, "contact": contact_email
                }, agents=["RevenueOpsAgent"])
                return data

    async def move_deal_to_closed_won(self, deal_id: str) -> dict:
        stage_id = os.environ.get("HUBSPOT_STAGE_CLOSED_WON", "closedwon")
        payload = {"properties": {"dealstage": stage_id}}
        async with aiohttp.ClientSession() as s:
            async with s.patch(f"{HUBSPOT_BASE}/crm/v3/objects/deals/{deal_id}",
                               headers=HUBSPOT_HEADERS, json=payload) as r:
                return await r.json()

hubspot = GarcarHubSpot()

async def handle_upsert_contact(event):
    await hubspot.upsert_contact(event["email"], {
        "firstname": event.get("firstname", ""),
        "lastname": event.get("lastname", ""),
        "hs_lead_status": "NEW",
        "lead_source": event.get("source", "garcar-butler")
    })

bus.subscribe("hubspot.upsert_contact", handle_upsert_contact)
