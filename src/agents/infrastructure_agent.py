"""
Infrastructure Agent – monitors uptime, scales services,
and optimizes cloud costs.
"""

import asyncio
import logging
import os
import time
from typing import Any

import httpx

from src.agents import BaseAgent

logger = logging.getLogger(__name__)

# Cost saving: flag instances idle for more than this many seconds
IDLE_THRESHOLD_SECONDS = 1800  # 30 minutes


class InfrastructureAgent(BaseAgent):
    """Monitors uptime endpoints, detects outages, and tracks cost metrics."""

    name = "infrastructure"
    description = "Monitor uptime, scale services, optimize costs"

    def __init__(
        self,
        event_bus=None,
        prometheus_url: str = "",
        endpoints: list[str] | None = None,
    ) -> None:
        super().__init__(event_bus)
        self._prometheus_url = prometheus_url or os.getenv("PROMETHEUS_URL", "")
        # Endpoints to health-check each cycle
        self._endpoints: list[str] = endpoints or []
        self._uptime_stats: dict[str, bool] = {}
        self._cost_usd: float = 0.0

    def cycle_interval(self) -> float:
        return 60.0

    async def run_cycle(self) -> None:
        await self._check_uptime()
        await self._query_cost_metrics()

    async def _check_uptime(self) -> None:
        """Ping each configured endpoint and record up/down state."""
        for endpoint in self._endpoints:
            up = await self._ping(endpoint)
            was_up = self._uptime_stats.get(endpoint, True)
            self._uptime_stats[endpoint] = up

            if not up and was_up:
                self.record_action(f"Outage detected: {endpoint}", {"endpoint": endpoint})
                await self.emit(
                    "infra.outage_detected",
                    {"endpoint": endpoint, "timestamp": time.time()},
                )
            elif up and not was_up:
                self.record_action(f"Service recovered: {endpoint}", {"endpoint": endpoint})
                await self.emit(
                    "infra.service_recovered",
                    {"endpoint": endpoint, "timestamp": time.time()},
                )

    async def _ping(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url)
                return resp.status_code < 500
        except httpx.HTTPError:
            return False

    async def _query_cost_metrics(self) -> None:
        """Query Prometheus for cost-related metrics (if configured)."""
        if not self._prometheus_url:
            return
        query = "sum(kube_node_status_capacity{resource='cpu'})"
        url = f"{self._prometheus_url}/api/v1/query"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params={"query": query})
                if resp.status_code == 200:
                    result = resp.json().get("data", {}).get("result", [])
                    if result:
                        self.record_action("Cost metrics queried", {"cpu_capacity": result[0].get("value")})
        except httpx.HTTPError as exc:
            self.logger.debug("Prometheus query failed: %s", exc)

    def add_endpoint(self, url: str) -> None:
        """Dynamically add an endpoint to monitor."""
        if url not in self._endpoints:
            self._endpoints.append(url)

    def health(self) -> dict[str, Any]:
        h = super().health()
        h["monitored_endpoints"] = len(self._endpoints)
        h["uptime_stats"] = self._uptime_stats
        h["prometheus_configured"] = bool(self._prometheus_url)
        return h
