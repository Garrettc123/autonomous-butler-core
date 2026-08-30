"""
Garcar Enterprise — Supabase Integration
Primary event store, real-time broadcasting, and ledger writes.
All Butler agents write here. Dashboards subscribe via Supabase Realtime.
"""
import os
from supabase import create_client, Client
from datetime import datetime, timezone
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

async def log_revenue_to_ledger(event: dict):
    """Write revenue event to gc_ledger table."""
    supabase.table("gc_ledger").insert({
        "source": event["source"],
        "amount": event["amount"],
        "description": event.get("description", ""),
        "metadata": event.get("metadata", {}),
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()

async def log_agent_event(event: dict):
    """Write agent action to agent_events table."""
    supabase.table("agent_events").insert({
        "agent": event["agent"],
        "action": event["action"],
        "payload": event.get("payload", {}),
        "outcome": event.get("outcome", "pending"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()

async def update_integration_health(platform: str, status: str, detail: str):
    """Upsert integration health status — used by all-platforms health check."""
    supabase.table("integrations_health").upsert({
        "platform": platform,
        "status": status,
        "detail": detail,
        "last_checked": datetime.now(timezone.utc).isoformat()
    }).execute()

async def get_revenue_summary(days: int = 30) -> dict:
    """Pull rolling revenue summary for dashboard."""
    result = supabase.table("gc_ledger").select("source, amount").execute()
    rows = result.data or []
    total = sum(r["amount"] for r in rows)
    by_source = {}
    for r in rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + r["amount"]
    return {"total": total, "by_source": by_source, "rows": len(rows)}

# Subscribe to all revenue and agent events
bus.subscribe("revenue.*", log_revenue_to_ledger)
bus.subscribe("agent.*", log_agent_event)
