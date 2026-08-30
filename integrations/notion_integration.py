"""
Garcar Enterprise — Notion Integration
Autonomous documentation: agents write decisions, revenue events,
and system state directly to Notion databases.
"""
import os
from notion_client import AsyncClient
from datetime import datetime, timezone
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

class GarcarNotion:
    def __init__(self):
        self.client = AsyncClient(auth=os.environ["NOTION_API_KEY"])
        self.db_ids = {
            "revenue_log": os.environ["NOTION_REVENUE_DB_ID"],
            "ops_runbooks": os.environ["NOTION_OPS_DB_ID"],
            "system_registry": os.environ["NOTION_PROJECTS_DB_ID"]
        }

    async def log_revenue_event(self, source: str, amount: float, description: str, metadata: dict = {}):
        await self.client.pages.create(
            parent={"database_id": self.db_ids["revenue_log"]},
            properties={
                "Name": {"title": [{"text": {"content": description}}]},
                "Source": {"select": {"name": source}},
                "Amount": {"number": amount},
                "Date": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                "Status": {"select": {"name": "Confirmed"}}
            }
        )

    async def log_agent_decision(self, agent: str, action: str, outcome: str, context: dict = {}):
        await self.client.pages.create(
            parent={"database_id": self.db_ids["ops_runbooks"]},
            properties={
                "Name": {"title": [{"text": {"content": f"[{agent}] {action}"}}]},
                "Agent": {"select": {"name": agent}},
                "Outcome": {"select": {"name": outcome}},
                "Timestamp": {"date": {"start": datetime.now(timezone.utc).isoformat()}}
            }
        )

notion = GarcarNotion()

async def handle_revenue_log(event):
    await notion.log_revenue_event(event["source"], event["amount"], event["description"])

async def handle_agent_decision(event):
    await notion.log_agent_decision(event["agent"], event["action"], event["outcome"])

bus.subscribe("revenue.*", handle_revenue_log)
bus.subscribe("agent.decision", handle_agent_decision)
