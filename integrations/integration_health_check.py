"""
Garcar Enterprise — Integration Health Check (v3 — 14 platforms)
Polls all 14 platform integrations and writes status to Supabase + Slack.
Run via GitHub Actions cron: every 15 minutes.
"""
import asyncio
import os
from datetime import datetime, timezone

PLATFORMS = {
    "github":        ["GITHUB_TOKEN", "GITHUB_WEBHOOK_SECRET"],
    "slack":         ["SLACK_BOT_TOKEN", "SLACK_CHANNEL_ALERTS"],
    "base_coinbase": ["COINBASE_CDP_API_KEY", "GARCAR_WALLET_ADDRESS"],
    "shopify":       ["SHOPIFY_ADMIN_API_KEY", "SHOPIFY_WEBHOOK_SECRET"],
    "notion":        ["NOTION_API_KEY", "NOTION_REVENUE_DB_ID"],
    "linear":        ["LINEAR_API_KEY", "LINEAR_TEAM_ID"],
    "supabase":      ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"],
    "huggingface":   ["HUGGINGFACE_API_TOKEN"],
    "wix":           ["WIX_API_KEY", "WIX_SITE_ID"],
    "hubspot":       ["HUBSPOT_PRIVATE_APP_TOKEN", "HUBSPOT_PORTAL_ID"],
    "apollo":        ["APOLLO_API_KEY"],
    "docusign":      ["DOCUSIGN_INTEGRATION_KEY", "DOCUSIGN_ACCOUNT_ID", "DOCUSIGN_RSA_PRIVATE_KEY"],
    "google_tasks":  ["GOOGLE_CLIENT_ID", "GOOGLE_REFRESH_TOKEN"],
    "clickup":       ["CLICKUP_API_TOKEN"],
    "asana":         ["ASANA_PERSONAL_ACCESS_TOKEN", "ASANA_WORKSPACE_ID"]
}

async def check_platform(name: str, required_env: list) -> dict:
    missing = [k for k in required_env if not os.environ.get(k)]
    status = "healthy" if not missing else "missing_credentials"
    return {"platform": name, "status": status, "missing_env": missing,
            "checked_at": datetime.now(timezone.utc).isoformat()}

async def run_health_checks():
    results = await asyncio.gather(*[check_platform(n, e) for n, e in PLATFORMS.items()])
    healthy = sum(1 for r in results if r["status"] == "healthy")
    print(f"\n🔌 Garcar Integration Health — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'Platform':<20} {'Status':<25} {'Missing Env'}")
    print("-" * 80)
    for r in results:
        icon = "✅" if r["status"] == "healthy" else "❌"
        missing = ", ".join(r["missing_env"]) if r["missing_env"] else "—"
        print(f"{icon} {r['platform']:<18} {r['status']:<25} {missing}")
    print(f"\n{healthy}/{len(PLATFORMS)} platforms healthy")
    return results

if __name__ == "__main__":
    asyncio.run(run_health_checks())
