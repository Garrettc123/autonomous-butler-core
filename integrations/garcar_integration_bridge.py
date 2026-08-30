"""
Garcar Multiplex — Full Platform Integration Bridge
Wires: GitHub · Slack · Base/Coinbase · Shopify · Notion · Linear · Supabase · Hugging Face
All credentials read from environment variables (GitHub Actions Secrets).
NEVER hardcode credentials — use os.environ exclusively.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("garcar.bridge")


# ══════════════════════════════════════════════════════════════════════════════
# CREDENTIAL LOADER — reads from env, never from files
# ══════════════════════════════════════════════════════════════════════════════

class Secrets:
    """Loads all platform credentials from environment variables."""

    # GitHub
    GITHUB_TOKEN: str = os.environ.get("GARCAR_GITHUB_TOKEN", "")
    GITHUB_ORG: str = os.environ.get("GITHUB_ORG", "Garrettc123")

    # Slack
    SLACK_BOT_TOKEN: str = os.environ.get("SLACK_BOT_TOKEN", "")
    SLACK_WEBHOOK_URL: str = os.environ.get("SLACK_WEBHOOK_URL", "")
    SLACK_CHANNEL_REVENUE: str = os.environ.get("SLACK_CHANNEL_REVENUE", "")
    SLACK_CHANNEL_OPS: str = os.environ.get("SLACK_CHANNEL_OPS", "")
    SLACK_CHANNEL_ALERTS: str = os.environ.get("SLACK_CHANNEL_ALERTS", "")

    # Base by Coinbase
    CDP_API_KEY_NAME: str = os.environ.get("COINBASE_CDP_API_KEY_NAME", "")
    CDP_PRIVATE_KEY: str = os.environ.get("COINBASE_CDP_PRIVATE_KEY", "")
    BASE_RPC_URL: str = os.environ.get("BASE_NETWORK_RPC_URL", "https://mainnet.base.org")
    BASE_WALLET: str = os.environ.get("BASE_WALLET_ADDRESS", "")
    COINBASE_COMMERCE_KEY: str = os.environ.get("COINBASE_COMMERCE_API_KEY", "")

    # Shopify
    SHOPIFY_DOMAIN: str = os.environ.get("SHOPIFY_STORE_DOMAIN", "")
    SHOPIFY_ADMIN_TOKEN: str = os.environ.get("SHOPIFY_ADMIN_API_TOKEN", "")
    SHOPIFY_STOREFRONT_TOKEN: str = os.environ.get("SHOPIFY_STOREFRONT_TOKEN", "")

    # Notion
    NOTION_KEY: str = os.environ.get("NOTION_API_KEY", "")
    NOTION_REVENUE_DB: str = os.environ.get("NOTION_REVENUE_DB_ID", "")
    NOTION_OPS_DB: str = os.environ.get("NOTION_OPS_DB_ID", "")
    NOTION_LEADS_DB: str = os.environ.get("NOTION_LEADS_DB_ID", "")

    # Linear
    LINEAR_KEY: str = os.environ.get("LINEAR_API_KEY", "")
    LINEAR_TEAM: str = os.environ.get("LINEAR_TEAM_ID", "")
    LINEAR_PROJECT: str = os.environ.get("LINEAR_PROJECT_ID", "")

    # Supabase
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON: str = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    # Hugging Face
    HF_TOKEN: str = os.environ.get("HUGGINGFACE_TOKEN", "")
    HF_SPACE: str = os.environ.get("HUGGINGFACE_SPACE_ID", "")
    HF_MODEL_REPO: str = os.environ.get("HUGGINGFACE_MODEL_REPO", "")

    # Stripe
    STRIPE_KEY: str = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK: str = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    # AI
    OPENAI_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    ANTHROPIC_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

    @classmethod
    def validate(cls) -> dict:
        """Returns dict of which platforms have credentials configured."""
        return {
            "github": bool(cls.GITHUB_TOKEN),
            "slack": bool(cls.SLACK_BOT_TOKEN),
            "base_coinbase": bool(cls.CDP_API_KEY_NAME and cls.CDP_PRIVATE_KEY),
            "shopify": bool(cls.SHOPIFY_DOMAIN and cls.SHOPIFY_ADMIN_TOKEN),
            "notion": bool(cls.NOTION_KEY),
            "linear": bool(cls.LINEAR_KEY),
            "supabase": bool(cls.SUPABASE_URL and cls.SUPABASE_SERVICE),
            "huggingface": bool(cls.HF_TOKEN),
            "stripe": bool(cls.STRIPE_KEY),
            "openai": bool(cls.OPENAI_KEY),
        }


# ══════════════════════════════════════════════════════════════════════════════
# PLATFORM CLIENTS
# ══════════════════════════════════════════════════════════════════════════════

class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {Secrets.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def list_repos(self) -> list:
        with httpx.Client() as c:
            r = c.get(f"{self.BASE}/user/repos?per_page=100&type=all", headers=self.headers)
            r.raise_for_status()
            return r.json()

    def create_issue(self, repo: str, title: str, body: str, labels: list = None) -> dict:
        payload = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        with httpx.Client() as c:
            r = c.post(
                f"{self.BASE}/repos/{Secrets.GITHUB_ORG}/{repo}/issues",
                headers=self.headers,
                json=payload,
            )
            r.raise_for_status()
            return r.json()


class SlackClient:
    def __init__(self):
        self.token = Secrets.SLACK_BOT_TOKEN
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def post(self, channel: str, text: str, blocks: list = None) -> dict:
        payload = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks
        with httpx.Client() as c:
            r = c.post("https://slack.com/api/chat.postMessage", headers=self.headers, json=payload)
            return r.json()

    def alert(self, message: str):
        self.post(Secrets.SLACK_CHANNEL_ALERTS, message)

    def revenue_update(self, message: str):
        self.post(Secrets.SLACK_CHANNEL_REVENUE, message)


class SupabaseClient:
    def __init__(self):
        self.url = Secrets.SUPABASE_URL
        self.headers = {
            "apikey": Secrets.SUPABASE_SERVICE,
            "Authorization": f"Bearer {Secrets.SUPABASE_SERVICE}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def insert(self, table: str, data: dict) -> dict:
        with httpx.Client() as c:
            r = c.post(f"{self.url}/rest/v1/{table}", headers=self.headers, json=data)
            r.raise_for_status()
            return r.json()

    def select(self, table: str, filters: str = "") -> list:
        with httpx.Client() as c:
            r = c.get(f"{self.url}/rest/v1/{table}?{filters}", headers=self.headers)
            r.raise_for_status()
            return r.json()


class NotionClient:
    BASE = "https://api.notion.com/v1"

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {Secrets.NOTION_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def create_page(self, database_id: str, properties: dict) -> dict:
        with httpx.Client() as c:
            r = c.post(
                f"{self.BASE}/pages",
                headers=self.headers,
                json={"parent": {"database_id": database_id}, "properties": properties},
            )
            r.raise_for_status()
            return r.json()

    def log_revenue_event(self, amount: float, source: str, description: str):
        if not Secrets.NOTION_REVENUE_DB:
            log.warning("NOTION_REVENUE_DB_ID not set — skipping revenue log")
            return
        self.create_page(
            Secrets.NOTION_REVENUE_DB,
            {
                "Name": {"title": [{"text": {"content": description}}]},
                "Amount": {"number": amount},
                "Source": {"select": {"name": source}},
                "Date": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
            },
        )


class LinearClient:
    BASE = "https://api.linear.app/graphql"

    def __init__(self):
        self.headers = {"Authorization": Secrets.LINEAR_KEY, "Content-Type": "application/json"}

    def create_issue(self, title: str, description: str, priority: int = 2) -> dict:
        query = """
        mutation CreateIssue($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id title url }
          }
        }
        """
        variables = {
            "input": {
                "title": title,
                "description": description,
                "teamId": Secrets.LINEAR_TEAM,
                "priority": priority,
            }
        }
        if Secrets.LINEAR_PROJECT:
            variables["input"]["projectId"] = Secrets.LINEAR_PROJECT
        with httpx.Client() as c:
            r = c.post(self.BASE, headers=self.headers, json={"query": query, "variables": variables})
            r.raise_for_status()
            return r.json()


class ShopifyClient:
    def __init__(self):
        self.domain = Secrets.SHOPIFY_DOMAIN
        self.headers = {
            "X-Shopify-Access-Token": Secrets.SHOPIFY_ADMIN_TOKEN,
            "Content-Type": "application/json",
        }

    def get_recent_orders(self, limit: int = 50) -> list:
        url = f"https://{self.domain}/admin/api/2024-01/orders.json?limit={limit}&status=any"
        with httpx.Client() as c:
            r = c.get(url, headers=self.headers)
            r.raise_for_status()
            return r.json().get("orders", [])

    def get_revenue_summary(self) -> dict:
        orders = self.get_recent_orders()
        total = sum(float(o.get("total_price", 0)) for o in orders)
        return {"order_count": len(orders), "total_revenue_usd": round(total, 2)}


class HuggingFaceClient:
    BASE = "https://huggingface.co/api"

    def __init__(self):
        self.headers = {"Authorization": f"Bearer {Secrets.HF_TOKEN}"}

    def get_model_info(self, repo_id: str) -> dict:
        with httpx.Client() as c:
            r = c.get(f"{self.BASE}/models/{repo_id}", headers=self.headers)
            r.raise_for_status()
            return r.json()

    def list_spaces(self) -> list:
        with httpx.Client() as c:
            r = c.get(f"{self.BASE}/spaces?author=Garrettc123", headers=self.headers)
            return r.json() if r.status_code == 200 else []


class BaseClient:
    """Base L2 / Coinbase Commerce integration."""

    def __init__(self):
        self.commerce_key = Secrets.COINBASE_COMMERCE_KEY
        self.commerce_headers = {
            "X-CC-Api-Key": self.commerce_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_charges(self) -> list:
        """Fetch Coinbase Commerce charges (crypto payment receipts)."""
        with httpx.Client() as c:
            r = c.get("https://api.commerce.coinbase.com/charges", headers=self.commerce_headers)
            if r.status_code == 200:
                return r.json().get("data", [])
            return []

    def create_charge(self, name: str, description: str, amount_usd: float) -> dict:
        payload = {
            "name": name,
            "description": description,
            "pricing_type": "fixed_price",
            "local_price": {"amount": str(amount_usd), "currency": "USD"},
        }
        with httpx.Client() as c:
            r = c.post("https://api.commerce.coinbase.com/charges", headers=self.commerce_headers, json=payload)
            r.raise_for_status()
            return r.json()


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION — FULL INTEGRATION BRIDGE
# ══════════════════════════════════════════════════════════════════════════════

class GarcarIntegrationBridge:
    """Master orchestrator — coordinates all 8 platforms."""

    def __init__(self):
        self.status = Secrets.validate()
        self.github = GitHubClient() if self.status["github"] else None
        self.slack = SlackClient() if self.status["slack"] else None
        self.supabase = SupabaseClient() if self.status["supabase"] else None
        self.notion = NotionClient() if self.status["notion"] else None
        self.linear = LinearClient() if self.status["linear"] else None
        self.shopify = ShopifyClient() if self.status["shopify"] else None
        self.hf = HuggingFaceClient() if self.status["huggingface"] else None
        self.base = BaseClient() if self.status["base_coinbase"] else None

    def run(self):
        log.info("=" * 60)
        log.info("GARCAR MULTIPLEX — INTEGRATION BRIDGE STARTING")
        log.info(f"Platform status: {json.dumps(self.status, indent=2)}")
        log.info("=" * 60)

        results = {}

        # 1. Shopify revenue sync → Supabase + Notion
        results["shopify"] = self._sync_shopify_revenue()

        # 2. Base/Coinbase charge sync → Supabase ledger
        results["base"] = self._sync_base_charges()

        # 3. GitHub repo health → Linear issues
        results["github_linear"] = self._sync_github_to_linear()

        # 4. Hugging Face model registry → Supabase
        results["huggingface"] = self._sync_hf_models()

        # 5. Post full report to Slack
        self._report_to_slack(results)

        log.info("Integration bridge completed.")
        return results

    def _sync_shopify_revenue(self) -> dict:
        if not self.shopify or not self.supabase:
            log.warning("Shopify or Supabase not configured — skipping")
            return {"skipped": True}
        try:
            summary = self.shopify.get_revenue_summary()
            log.info(f"Shopify revenue: ${summary['total_revenue_usd']} across {summary['order_count']} orders")

            # Write to Supabase gc_ledger
            self.supabase.insert("gc_revenue_events", {
                "source": "shopify",
                "amount_usd": summary["total_revenue_usd"],
                "order_count": summary["order_count"],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })

            # Log to Notion
            if self.notion:
                self.notion.log_revenue_event(
                    summary["total_revenue_usd"], "Shopify",
                    f"Shopify sync — {summary['order_count']} orders"
                )

            return summary
        except Exception as e:
            log.error(f"Shopify sync failed: {e}")
            return {"error": str(e)}

    def _sync_base_charges(self) -> dict:
        if not self.base or not self.supabase:
            log.warning("Base/Coinbase or Supabase not configured — skipping")
            return {"skipped": True}
        try:
            charges = self.base.get_charges()
            confirmed = [c for c in charges if c.get("timeline", [{}])[-1].get("status") == "COMPLETED"]
            total = sum(
                float(c.get("pricing", {}).get("local", {}).get("amount", 0))
                for c in confirmed
            )
            log.info(f"Base/Coinbase: {len(confirmed)} confirmed charges totaling ${total:.2f}")

            self.supabase.insert("gc_revenue_events", {
                "source": "base_coinbase",
                "amount_usd": round(total, 2),
                "order_count": len(confirmed),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })

            return {"confirmed_charges": len(confirmed), "total_usd": round(total, 2)}
        except Exception as e:
            log.error(f"Base sync failed: {e}")
            return {"error": str(e)}

    def _sync_github_to_linear(self) -> dict:
        if not self.github or not self.linear:
            log.warning("GitHub or Linear not configured — skipping")
            return {"skipped": True}
        try:
            repos = self.github.list_repos()
            stale = [
                r for r in repos
                if r.get("open_issues_count", 0) > 10
            ]
            for r in stale[:3]:  # Cap at 3 Linear issues per run
                self.linear.create_issue(
                    title=f"[AUTO] Review: {r['name']} has {r['open_issues_count']} open issues",
                    description=f"Repository [{r['name']}]({r['html_url']}) has accumulated {r['open_issues_count']} open issues. Auto-flagged by Garcar Multiplex integration bridge.",
                    priority=3,
                )
            log.info(f"GitHub→Linear: flagged {len(stale[:3])} repos")
            return {"repos_flagged": len(stale)}
        except Exception as e:
            log.error(f"GitHub→Linear sync failed: {e}")
            return {"error": str(e)}

    def _sync_hf_models(self) -> dict:
        if not self.hf or not self.supabase:
            log.warning("HuggingFace or Supabase not configured — skipping")
            return {"skipped": True}
        try:
            spaces = self.hf.list_spaces()
            log.info(f"HuggingFace: found {len(spaces)} spaces")
            for space in spaces[:10]:
                self.supabase.insert("hf_model_registry", {
                    "space_id": space.get("id", ""),
                    "name": space.get("id", "").split("/")[-1],
                    "sdk": space.get("sdk", "unknown"),
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                })
            return {"spaces_synced": len(spaces)}
        except Exception as e:
            log.error(f"HuggingFace sync failed: {e}")
            return {"error": str(e)}

    def _report_to_slack(self, results: dict):
        if not self.slack:
            log.warning("Slack not configured — skipping report")
            return
        platforms_ok = sum(1 for v in self.status.values() if v)
        report = (
            f"*🧠 Garcar Multiplex Integration Report*\n"
            f"*{platforms_ok}/10 platforms configured*\n\n"
            f"• Shopify: `{results.get('shopify', {})}`\n"
            f"• Base/Coinbase: `{results.get('base', {})}`\n"
            f"• GitHub→Linear: `{results.get('github_linear', {})}`\n"
            f"• HuggingFace: `{results.get('huggingface', {})}`\n"
            f"• Timestamp: `{datetime.now(timezone.utc).isoformat()}`"
        )
        self.slack.post(Secrets.SLACK_CHANNEL_OPS, report)


if __name__ == "__main__":
    bridge = GarcarIntegrationBridge()
    bridge.run()
