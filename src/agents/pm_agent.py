"""
PM Agent – creates and updates Linear issues, manages sprint planning,
and tracks velocity.
"""

import asyncio
import logging
import os
from typing import Any

import httpx

from src.agents import BaseAgent

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class PMAgent(BaseAgent):
    """Manages Linear issues, sprint planning, and velocity tracking."""

    name = "pm"
    description = "Create/update Linear issues, manage sprint planning, track velocity"

    def __init__(self, event_bus=None, linear_api_key: str = "", linear_team_id: str = "") -> None:
        super().__init__(event_bus)
        self._linear_key = linear_api_key or os.getenv("LINEAR_API_KEY", "")
        self._team_id = linear_team_id or os.getenv("LINEAR_TEAM_ID", "")
        self._velocity: float = 0.0
        self._open_issues: int = 0

    def cycle_interval(self) -> float:
        return 300.0

    async def setup(self) -> None:
        if self.event_bus:
            self.event_bus.subscribe("security.vulnerability_found", self._handle_security_alert)
            self.event_bus.subscribe("devops.build_retried", self._handle_build_retry)

    async def run_cycle(self) -> None:
        if not self._linear_key:
            self.logger.debug("No Linear key – skipping PM cycle")
            return

        await self._sync_issues()
        await self._compute_velocity()

    async def _gql(self, query: str, variables: dict | None = None) -> dict | None:
        headers = {
            "Authorization": self._linear_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(LINEAR_API_URL, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            self.logger.warning("Linear API error: %s", exc)
            return None

    async def _sync_issues(self) -> None:
        """Count open issues in the team's backlog."""
        if not self._team_id:
            return
        query = """
        query($teamId: String!) {
            team(id: $teamId) {
                issues(filter: { state: { type: { nin: ["completed", "cancelled"] } } }) {
                    nodes { id title priority }
                }
            }
        }
        """
        result = await self._gql(query, {"teamId": self._team_id})
        if result is None:
            return
        issues = (
            result.get("data", {})
            .get("team", {})
            .get("issues", {})
            .get("nodes", [])
        )
        self._open_issues = len(issues)
        self.record_action(f"Synced {self._open_issues} open issues", {"count": self._open_issues})

    async def _compute_velocity(self) -> None:
        """Compute completed story points in the last two weeks."""
        if not self._team_id:
            return
        query = """
        query($teamId: String!) {
            team(id: $teamId) {
                issues(filter: {
                    state: { type: { in: ["completed"] } }
                    completedAt: { gte: "-P14D" }
                }) {
                    nodes { estimate }
                }
            }
        }
        """
        result = await self._gql(query, {"teamId": self._team_id})
        if result is None:
            return
        issues = (
            result.get("data", {})
            .get("team", {})
            .get("issues", {})
            .get("nodes", [])
        )
        self._velocity = sum(i.get("estimate") or 0 for i in issues)
        self.record_action("Velocity computed", {"velocity_pts_2wk": self._velocity})
        await self.emit("pm.velocity_update", {"velocity": self._velocity})

    async def create_issue(self, title: str, description: str, priority: int = 2) -> str | None:
        """Create a new Linear issue and return its ID."""
        if not self._linear_key or not self._team_id:
            return None
        mutation = """
        mutation($title: String!, $description: String!, $teamId: String!, $priority: Int!) {
            issueCreate(input: {
                title: $title,
                description: $description,
                teamId: $teamId,
                priority: $priority
            }) {
                success
                issue { id url }
            }
        }
        """
        result = await self._gql(
            mutation,
            {"title": title, "description": description, "teamId": self._team_id, "priority": priority},
        )
        if result is None:
            return None
        issue_data = result.get("data", {}).get("issueCreate", {})
        if issue_data.get("success"):
            issue_id = issue_data.get("issue", {}).get("id")
            self.record_action(f"Created issue: {title}", {"issue_id": issue_id})
            return issue_id
        return None

    async def _handle_security_alert(self, event) -> None:
        count = event.payload.get("count", 0)
        await self.create_issue(
            title=f"🔐 Security: {count} critical vulnerability alert(s)",
            description=f"Automatically created by Security Agent.\n\n{event.payload}",
            priority=1,
        )

    async def _handle_build_retry(self, event) -> None:
        repo = event.payload.get("repo", "unknown")
        self.record_action(f"Noted build retry in {repo}", event.payload)

    def health(self) -> dict[str, Any]:
        h = super().health()
        h["linear_configured"] = bool(self._linear_key)
        h["open_issues"] = self._open_issues
        h["velocity_2wk"] = self._velocity
        return h
