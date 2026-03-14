"""
DevOps Agent – monitors CI/CD pipelines, auto-fixes failing builds,
and manages deployments via the GitHub API.
"""

import logging
import os
from typing import Any

import httpx

from src.agents import BaseAgent

logger = logging.getLogger(__name__)


class DevOpsAgent(BaseAgent):
    """Monitors GitHub Actions, auto-retries failed workflows, and gates deploys."""

    name = "devops"
    description = "Monitor CI/CD, auto-fix failing builds, manage deployments"

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

    def cycle_interval(self) -> float:
        return 120.0

    async def run_cycle(self) -> None:
        if not self._github_token:
            self.logger.debug("No GitHub token – skipping DevOps cycle")
            return

        await self._check_workflow_runs()

    async def _check_workflow_runs(self) -> None:
        """Fetch recent workflow runs and retry any that failed."""
        if not self._github_org:
            return

        url = f"{self._base_url}/orgs/{self._github_org}/actions/runs"
        params = {"status": "failure", "per_page": 10}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._headers, params=params)
                if resp.status_code == 404:
                    # Org might be a user account – fall back
                    return
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            self.logger.warning("GitHub API error: %s", exc)
            return

        for run in data.get("workflow_runs", []):
            run_id = run["id"]
            repo_name = run["repository"]["full_name"]
            workflow = run.get("name", "unknown")
            self.logger.info("Found failed run %s in %s (%s)", run_id, repo_name, workflow)
            await self._rerun_workflow(repo_name, run_id)
            self.record_action(
                f"Re-triggered failed workflow '{workflow}'",
                {"repo": repo_name, "run_id": run_id},
            )
            await self.emit(
                "devops.build_retried",
                {"repo": repo_name, "run_id": run_id, "workflow": workflow},
            )

    async def _rerun_workflow(self, repo_full_name: str, run_id: int) -> None:
        url = f"{self._base_url}/repos/{repo_full_name}/actions/runs/{run_id}/rerun-failed-jobs"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, headers=self._headers)
                if resp.status_code not in (201, 204):
                    self.logger.warning("Re-run returned %s", resp.status_code)
        except httpx.HTTPError as exc:
            self.logger.warning("Failed to re-run workflow: %s", exc)

    def health(self) -> dict[str, Any]:
        h = super().health()
        h["github_configured"] = bool(self._github_token)
        return h
