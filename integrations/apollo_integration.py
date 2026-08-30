"""
Garcar Enterprise — Apollo.io Integration
Autonomous lead sourcing, enrichment, and sequence enrollment.
Connects to lead-enrichment-engine output via event bus.
"""
import os
import aiohttp
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

APOLLO_BASE = "https://api.apollo.io/v1"
APOLLO_HEADERS = {
    "x-api-key": os.environ.get("APOLLO_API_KEY", ""),
    "Content-Type": "application/json"
}

class GarcarApollo:
    async def search_people(self, titles: list, seniority: list, company_size: list, limit: int = 25) -> list:
        """Search Apollo for prospects matching Garcar ICP."""
        payload = {
            "per_page": limit,
            "person_titles": titles,
            "person_seniority": seniority,
            "organization_num_employees_ranges": company_size
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{APOLLO_BASE}/mixed_people/search",
                              headers=APOLLO_HEADERS, json=payload) as r:
                data = await r.json()
                people = data.get("people", [])
                for p in people:
                    await bus.emit("lead.enriched", {
                        "email": p.get("email", ""),
                        "first_name": p.get("first_name", ""),
                        "last_name": p.get("last_name", ""),
                        "title": p.get("title", ""),
                        "company": p.get("organization", {}).get("name", ""),
                        "source": "apollo"
                    }, agents=["RevenueOpsAgent"])
                return people

    async def enroll_in_sequence(self, contact_id: str, sequence_id: str = None) -> dict:
        """Enroll a contact in an Apollo email sequence."""
        seq_id = sequence_id or os.environ.get("APOLLO_SEQUENCE_OUTBOUND_ID", "")
        payload = {"sequence_id": seq_id, "contact_ids": [contact_id]}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{APOLLO_BASE}/emailer_campaigns/{seq_id}/add_contact_ids",
                              headers=APOLLO_HEADERS, json=payload) as r:
                return await r.json()

    async def run_daily_prospecting(self):
        """Daily ICP prospecting — triggered by GitHub Actions cron."""
        await self.search_people(
            titles=["CTO", "VP Engineering", "Head of DevOps", "Platform Engineering Lead"],
            seniority=["director", "vp", "c_suite", "founder"],
            company_size=["11,50", "51,200", "201,500"]
        )

apollo = GarcarApollo()
