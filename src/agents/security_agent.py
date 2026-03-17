"""
Security Agent – scans for vulnerabilities, rotates stale credentials,
and monitors for breach indicators.
"""

import asyncio
import logging
import os
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from src.agents import BaseAgent

logger = logging.getLogger(__name__)

# Credentials older than this are considered stale
ROTATION_THRESHOLD_DAYS = 90
VULN_SEVERITY_LEVELS = {"critical", "high", "medium", "low"}


class SecurityAgent(BaseAgent):
    """Scans for vulnerabilities, rotates credentials, and monitors for breaches."""

    name = "security"
    description = "Scan for vulnerabilities, rotate credentials, monitor for breaches"

    def __init__(self, event_bus=None, github_token: str = "", github_org: str = "") -> None:
        super().__init__(event_bus)
        self._github_token = github_token or os.getenv("GITHUB_TOKEN", "")
        self._github_org = github_org or os.getenv("GITHUB_ORG", "")
        self._base_url = "https://api.github.com"
        self._headers = {
            "Authorization": f"Bearer {self._github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._last_scan: datetime | None = None
        self._open_alerts: int = 0

    def cycle_interval(self) -> float:
        return 600.0  # every 10 minutes

    async def run_cycle(self) -> None:
        await self._scan_dependabot_alerts()
        await self._scan_secret_alerts()
        self._last_scan = datetime.now(timezone.utc)

    async def _github_get(self, path: str, params: dict | None = None) -> dict | None:
        if not self._github_token:
            return None
        url = f"{self._base_url}/{path}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._headers, params=params or {})
                if resp.status_code == 403:
                    self.logger.debug("GitHub 403 – insufficient permissions for %s", path)
                    return None
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            self.logger.warning("GitHub API error: %s", exc)
            return None

    async def _scan_dependabot_alerts(self) -> None:
        """Check Dependabot vulnerability alerts across org repos."""
        if not self._github_org:
            return
        path = f"orgs/{self._github_org}/dependabot/alerts"
        data = await self._github_get(path, {"state": "open", "severity": "critical", "per_page": 50})
        if data is None:
            return

        alerts = data if isinstance(data, list) else data.get("alerts", [])
        if alerts:
            self._open_alerts = len(alerts)
            self.record_action(
                f"Found {len(alerts)} critical Dependabot alert(s)",
                {"count": len(alerts)},
            )
            await self.emit(
                "security.vulnerability_found",
                {"severity": "critical", "count": len(alerts), "source": "dependabot"},
            )

    async def _scan_secret_alerts(self) -> None:
        """Check GitHub secret scanning alerts across org repos."""
        if not self._github_org:
            return
        path = f"orgs/{self._github_org}/secret-scanning/alerts"
        data = await self._github_get(path, {"state": "open", "per_page": 50})
        if data is None:
            return

        alerts = data if isinstance(data, list) else []
        if alerts:
            self.record_action(
                f"Found {len(alerts)} secret scanning alert(s)",
                {"count": len(alerts)},
            )
            await self.emit(
                "security.secret_exposed",
                {"count": len(alerts)},
            )

    @staticmethod
    def generate_secure_credential(length: int = 32) -> str:
        """Generate a cryptographically secure random credential."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def health(self) -> dict[str, Any]:
        h = super().health()
        h["github_configured"] = bool(self._github_token)
        h["open_vulnerability_alerts"] = self._open_alerts
        h["last_scan"] = self._last_scan.isoformat() if self._last_scan else None
        return h
