"""
Support Agent – responds to GitHub issues, triages bugs,
and escalates critical issues.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from src.agents import BaseAgent

logger = logging.getLogger(__name__)

# Labels considered "critical" for auto-escalation
CRITICAL_LABELS = {"critical", "blocker", "severity:critical", "P0"}

TRIAGE_COMMENT = (
    "👋 Thanks for opening this issue! "
    "The Autonomous Butler Support Agent has triaged this report and will route it to the right team. "
    "A human engineer will follow up shortly."
)


class SupportAgent(BaseAgent):
    """Monitors GitHub issues, posts triage comments, and escalates critical ones."""

    name = "support"
    description = "Respond to GitHub issues, triage bugs, escalate critical issues"

    def __init__(
        self,
        event_bus=None,
        github_token: str = "",
        github_org: str = "",
    ) -> None:
        super().__init__(event_bus)
        self._github_token = github_token or os.getenv("GITHUB_TOKEN", "")
        self._github_org = github_org or os.getenv("GITHUB_ORG", "")
        self._base_url = "https://api.github.com"
        self._headers = {
            "Authorization": f"Bearer {self._github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._processed_issue_ids: set[int] = set()
        self._escalated: int = 0

    def cycle_interval(self) -> float:
        return 120.0

    async def run_cycle(self) -> None:
        if not self._github_token or not self._github_org:
            self.logger.debug("No GitHub credentials – skipping support cycle")
            return

        await self._process_new_issues()

    async def _process_new_issues(self) -> None:
        """Find recently-opened issues across org repos and triage them."""
        repos = await self._list_repos()
        since = (datetime.now(timezone.utc) - timedelta(seconds=self.cycle_interval() * 2)).isoformat()
        for repo in repos[:10]:  # limit to 10 repos per cycle
            await self._triage_repo_issues(repo, since)

    async def _list_repos(self) -> list[str]:
        url = f"{self._base_url}/orgs/{self._github_org}/repos"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._headers, params={"per_page": 30})
                if resp.status_code in (401, 403, 404):
                    return []
                resp.raise_for_status()
                return [r["full_name"] for r in resp.json()]
        except httpx.HTTPError as exc:
            self.logger.warning("Could not list repos: %s", exc)
            return []

    async def _triage_repo_issues(self, repo_full_name: str, since: str) -> None:
        url = f"{self._base_url}/repos/{repo_full_name}/issues"
        params = {"state": "open", "since": since, "per_page": 20, "sort": "created"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._headers, params=params)
                if resp.status_code in (401, 403, 404):
                    return
                resp.raise_for_status()
                issues = resp.json()
        except httpx.HTTPError as exc:
            self.logger.warning("Could not fetch issues for %s: %s", repo_full_name, exc)
            return

        for issue in issues:
            if "pull_request" in issue:
                continue  # skip PRs
            issue_id = issue["id"]
            if issue_id in self._processed_issue_ids:
                continue
            self._processed_issue_ids.add(issue_id)

            labels = {lbl["name"] for lbl in issue.get("labels", [])}
            is_critical = bool(labels & CRITICAL_LABELS)

            await self._post_triage_comment(repo_full_name, issue["number"])
            self.record_action(
                f"Triaged issue #{issue['number']} in {repo_full_name}",
                {"issue_number": issue["number"], "critical": is_critical},
            )

            if is_critical:
                self._escalated += 1
                self.record_action(
                    f"Escalated critical issue #{issue['number']}",
                    {"repo": repo_full_name, "issue": issue["number"]},
                )
                await self.emit(
                    "support.critical_escalation",
                    {"repo": repo_full_name, "issue_number": issue["number"], "title": issue["title"]},
                )

    async def _post_triage_comment(self, repo_full_name: str, issue_number: int) -> None:
        url = f"{self._base_url}/repos/{repo_full_name}/issues/{issue_number}/comments"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url, headers=self._headers, json={"body": TRIAGE_COMMENT}
                )
                if resp.status_code not in (200, 201):
                    self.logger.warning(
                        "Failed to post comment on %s#%d: %s", repo_full_name, issue_number, resp.status_code
                    )
        except httpx.HTTPError as exc:
            self.logger.warning("Comment post error: %s", exc)

    def health(self) -> dict[str, Any]:
        h = super().health()
        h["github_configured"] = bool(self._github_token)
        h["escalated_today"] = self._escalated
        return h
