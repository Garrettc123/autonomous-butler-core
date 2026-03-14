"""
Autonomous Butler Core – main FastAPI application.

Starts all 6 agents, wires them to the shared event bus,
and serves the master dashboard + REST health API.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src.agents import BaseAgent
from src.agents.devops_agent import DevOpsAgent
from src.agents.infrastructure_agent import InfrastructureAgent
from src.agents.pm_agent import PMAgent
from src.agents.revenue_agent import RevenueAgent
from src.agents.security_agent import SecurityAgent
from src.agents.support_agent import SupportAgent
from src.bus import bus

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

VERSION = "1.0.0"

TEMPLATES_DIR = Path(__file__).parent / "dashboard" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---------------------------------------------------------------------------
# Agent registry (populated during startup)
# ---------------------------------------------------------------------------
AGENTS: list[BaseAgent] = []


def _build_agents() -> list[BaseAgent]:
    """Instantiate all 6 agents, sharing the module-level event bus."""
    return [
        DevOpsAgent(event_bus=bus),
        RevenueAgent(event_bus=bus),
        SecurityAgent(event_bus=bus),
        PMAgent(event_bus=bus),
        SupportAgent(event_bus=bus),
        InfrastructureAgent(event_bus=bus),
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global AGENTS
    AGENTS = _build_agents()
    for agent in AGENTS:
        try:
            await agent.start()
            logger.info("Agent '%s' started", agent.name)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to start agent '%s': %s", agent.name, exc)
    yield
    for agent in AGENTS:
        await agent.stop()
    logger.info("All agents stopped")


app = FastAPI(
    title="Autonomous Butler Core",
    description="Enterprise autonomous AI orchestration platform",
    version=VERSION,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    agents_data: list[dict[str, Any]] = [a.health() for a in AGENTS]
    agents_running = sum(1 for a in agents_data if a["status"] == "running")
    total_actions = sum(a["actions_today"] for a in agents_data)
    system_healthy = all(a["status"] in ("running", "initializing", "stopped") for a in agents_data)
    recent = [
        {
            "topic": e.topic,
            "source": e.source,
            "payload": e.payload,
            "timestamp": e.timestamp[:19],
        }
        for e in reversed(bus.recent_events(20))
    ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "agents": agents_data,
            "agents_running": agents_running,
            "total_actions_today": total_actions,
            "system_healthy": system_healthy,
            "event_count": len(bus.recent_events(1000)),
            "recent_events": recent,
            "version": VERSION,
        },
    )


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check() -> dict[str, Any]:
    agents_health = [a.health() for a in AGENTS]
    all_ok = all(a["status"] in ("running", "initializing") for a in agents_health)
    return {
        "status": "healthy" if all_ok else "degraded",
        "version": VERSION,
        "agents": agents_health,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/agents")
async def list_agents() -> dict[str, Any]:
    return {"agents": [a.health() for a in AGENTS]}


@app.get("/agents/{agent_name}")
async def get_agent(agent_name: str) -> dict[str, Any]:
    for agent in AGENTS:
        if agent.name == agent_name:
            return agent.health()
    return JSONResponse({"error": f"Agent '{agent_name}' not found"}, status_code=404)


@app.get("/events")
async def recent_events(limit: int = 50) -> dict[str, Any]:
    events = [
        {
            "id": e.id,
            "topic": e.topic,
            "source": e.source,
            "payload": e.payload,
            "timestamp": e.timestamp,
        }
        for e in bus.recent_events(limit)
    ]
    return {"events": events, "total": len(events)}


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Lightweight Prometheus-style metrics summary."""
    agents_data = [a.health() for a in AGENTS]
    return {
        "agents_running": sum(1 for a in agents_data if a["status"] == "running"),
        "agents_stopped": sum(1 for a in agents_data if a["status"] == "stopped"),
        "agents_error": sum(1 for a in agents_data if a["status"] == "error"),
        "total_actions_today": sum(a["actions_today"] for a in agents_data),
        "bus_events_total": len(bus.recent_events(1000)),
    }
