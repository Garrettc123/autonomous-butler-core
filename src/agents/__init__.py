"""Base agent class shared by all Autonomous Butler agents."""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


class AgentStatus:
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    INITIALIZING = "initializing"


class BaseAgent(ABC):
    """
    Abstract base for all Butler agents.

    Each agent runs an independent async loop, tracks actions taken today,
    and exposes a standard health/status interface used by the dashboard.
    """

    name: str = "base"
    description: str = ""

    def __init__(self, event_bus=None) -> None:
        self.event_bus = event_bus
        self.status: str = AgentStatus.STOPPED
        self.logger = logging.getLogger(f"butler.{self.name}")
        self._actions: list[dict[str, Any]] = []
        self._errors: list[str] = []
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._started_at: datetime | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the agent's background loop."""
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self.status = AgentStatus.INITIALIZING
        self._started_at = datetime.now(timezone.utc)
        self.logger.info("Starting agent %s", self.name)
        try:
            await self.setup()
            self.status = AgentStatus.RUNNING
        except Exception as exc:  # noqa: BLE001
            self.status = AgentStatus.ERROR
            self._errors.append(str(exc))
            self.logger.error("Setup failed for %s: %s", self.name, exc)
            return
        self._task = asyncio.create_task(self._run_loop(), name=f"agent-{self.name}")

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self.status = AgentStatus.STOPPED
        self.logger.info("Agent %s stopped", self.name)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Override to perform one-time initialization."""

    @abstractmethod
    async def run_cycle(self) -> None:
        """
        Core agent logic executed on every loop iteration.
        Agents should call ``self.record_action()`` for every meaningful action.
        """

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Error in %s cycle: %s", self.name, exc)
                self._errors.append(str(exc))
                self.status = AgentStatus.ERROR
                # Back off before retrying
                await asyncio.sleep(10)
                self.status = AgentStatus.RUNNING
            await asyncio.sleep(self.cycle_interval())

    def cycle_interval(self) -> float:
        """Seconds to wait between cycles. Override in subclasses."""
        return 60.0

    # ------------------------------------------------------------------
    # Action tracking
    # ------------------------------------------------------------------

    def record_action(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Record an action taken by this agent."""
        entry = {
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        }
        self._actions.append(entry)
        self.logger.info("[%s] %s", self.name, action)

    def actions_today(self) -> list[dict[str, Any]]:
        """Return actions recorded today (UTC)."""
        today = datetime.now(timezone.utc).date().isoformat()
        return [a for a in self._actions if a["timestamp"].startswith(today)]

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return a health summary for the dashboard."""
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "actions_today": len(self.actions_today()),
            "last_error": self._errors[-1] if self._errors else None,
            "started_at": self._started_at.isoformat() if self._started_at else None,
        }

    # ------------------------------------------------------------------
    # Event bus helpers
    # ------------------------------------------------------------------

    async def emit(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event to the shared bus (no-op if bus not set)."""
        if self.event_bus is None:
            return
        from src.bus import Event  # local import avoids circular dependency

        await self.event_bus.publish(Event(topic=topic, source=self.name, payload=payload))
