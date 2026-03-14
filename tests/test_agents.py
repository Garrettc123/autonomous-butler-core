"""Tests for the six Butler agents."""

import asyncio
import pytest

from src.agents import AgentStatus, BaseAgent
from src.agents.devops_agent import DevOpsAgent
from src.agents.infrastructure_agent import InfrastructureAgent
from src.agents.pm_agent import PMAgent
from src.agents.revenue_agent import RevenueAgent
from src.agents.security_agent import SecurityAgent
from src.agents.support_agent import SupportAgent
from src.bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------

class ConcreteAgent(BaseAgent):
    name = "test_agent"
    description = "A test agent"

    async def run_cycle(self):
        self.record_action("test_action", {"key": "val"})
        await asyncio.sleep(60)  # idle; will be cancelled on stop()


def test_agent_initial_state():
    agent = ConcreteAgent()
    assert agent.status == AgentStatus.STOPPED
    assert agent.actions_today() == []


def test_agent_record_action():
    agent = ConcreteAgent()
    agent.record_action("did something", {"detail": 42})
    actions = agent.actions_today()
    assert len(actions) == 1
    assert actions[0]["action"] == "did something"
    assert actions[0]["details"]["detail"] == 42


def test_agent_health_keys():
    agent = ConcreteAgent()
    h = agent.health()
    assert "name" in h
    assert "status" in h
    assert "actions_today" in h
    assert "description" in h


@pytest.mark.asyncio
async def test_agent_start_stop():
    agent = ConcreteAgent()
    await agent.start()
    assert agent.status == AgentStatus.RUNNING
    await agent.stop()
    assert agent.status == AgentStatus.STOPPED


@pytest.mark.asyncio
async def test_agent_emit_no_bus():
    """Emitting without a bus should not raise."""
    agent = ConcreteAgent()
    await agent.emit("some.topic", {"x": 1})  # must not raise


@pytest.mark.asyncio
async def test_agent_emit_with_bus(bus):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("test.event", handler)
    agent = ConcreteAgent(event_bus=bus)
    await agent.emit("test.event", {"data": "value"})

    assert len(received) == 1
    assert received[0].source == "test_agent"


# ---------------------------------------------------------------------------
# DevOps Agent
# ---------------------------------------------------------------------------

def test_devops_no_token_health(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_ORG", raising=False)
    agent = DevOpsAgent(github_token="", github_org="")
    h = agent.health()
    assert h["github_configured"] is False


@pytest.mark.asyncio
async def test_devops_cycle_without_token():
    """Cycle should complete without token (graceful degradation)."""
    agent = DevOpsAgent(github_token="", github_org="")
    agent.status = AgentStatus.RUNNING
    # Run one cycle; it should sleep and return without error
    await asyncio.wait_for(agent.run_cycle(), timeout=5)


# ---------------------------------------------------------------------------
# Revenue Agent
# ---------------------------------------------------------------------------

def test_revenue_no_key_health():
    agent = RevenueAgent(stripe_secret_key="")
    h = agent.health()
    assert h["stripe_configured"] is False
    assert h["last_mrr_usd"] == 0.0


@pytest.mark.asyncio
async def test_revenue_cycle_without_key():
    agent = RevenueAgent(stripe_secret_key="")
    agent.status = AgentStatus.RUNNING
    await asyncio.wait_for(agent.run_cycle(), timeout=5)


# ---------------------------------------------------------------------------
# Security Agent
# ---------------------------------------------------------------------------

def test_security_generate_credential():
    cred = SecurityAgent.generate_secure_credential(32)
    assert len(cred) == 32
    assert isinstance(cred, str)


def test_security_unique_credentials():
    c1 = SecurityAgent.generate_secure_credential()
    c2 = SecurityAgent.generate_secure_credential()
    assert c1 != c2


def test_security_health_keys():
    agent = SecurityAgent(github_token="", github_org="")
    h = agent.health()
    assert "open_vulnerability_alerts" in h
    assert "last_scan" in h


# ---------------------------------------------------------------------------
# PM Agent
# ---------------------------------------------------------------------------

def test_pm_no_key_health():
    agent = PMAgent(linear_api_key="", linear_team_id="")
    h = agent.health()
    assert h["linear_configured"] is False
    assert h["open_issues"] == 0


@pytest.mark.asyncio
async def test_pm_cycle_without_key():
    agent = PMAgent(linear_api_key="", linear_team_id="")
    agent.status = AgentStatus.RUNNING
    await asyncio.wait_for(agent.run_cycle(), timeout=5)


@pytest.mark.asyncio
async def test_pm_create_issue_without_key():
    agent = PMAgent(linear_api_key="", linear_team_id="")
    result = await agent.create_issue("Test Issue", "Description")
    assert result is None


# ---------------------------------------------------------------------------
# Support Agent
# ---------------------------------------------------------------------------

def test_support_no_credentials_health(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_ORG", raising=False)
    agent = SupportAgent(github_token="", github_org="")
    h = agent.health()
    assert h["github_configured"] is False
    assert h["escalated_today"] == 0


@pytest.mark.asyncio
async def test_support_cycle_without_credentials():
    agent = SupportAgent(github_token="", github_org="")
    agent.status = AgentStatus.RUNNING
    await asyncio.wait_for(agent.run_cycle(), timeout=5)


# ---------------------------------------------------------------------------
# Infrastructure Agent
# ---------------------------------------------------------------------------

def test_infrastructure_add_endpoint():
    agent = InfrastructureAgent()
    agent.add_endpoint("http://example.com/health")
    assert "http://example.com/health" in agent._endpoints


def test_infrastructure_no_duplicate_endpoints():
    agent = InfrastructureAgent()
    agent.add_endpoint("http://example.com")
    agent.add_endpoint("http://example.com")
    assert agent._endpoints.count("http://example.com") == 1


def test_infrastructure_health_keys():
    agent = InfrastructureAgent()
    h = agent.health()
    assert "monitored_endpoints" in h
    assert "uptime_stats" in h
    assert "prometheus_configured" in h


@pytest.mark.asyncio
async def test_infrastructure_ping_unreachable():
    """Pinging an unreachable endpoint should return False (not raise)."""
    agent = InfrastructureAgent()
    result = await agent._ping("http://127.0.0.1:19999/nowhere")
    assert result is False


# ---------------------------------------------------------------------------
# Inter-agent integration: security alert → PM creates issue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_to_pm_integration(bus):
    """SecurityAgent publishes a vuln event; PMAgent handles it without a real key."""
    pm = PMAgent(event_bus=bus, linear_api_key="", linear_team_id="")
    await pm.setup()  # registers bus subscriptions

    # Publish a security event as the security agent would
    from src.bus import Event

    evt = Event(
        topic="security.vulnerability_found",
        source="security",
        payload={"severity": "critical", "count": 3, "source": "dependabot"},
    )
    # The handler will call create_issue, which returns None (no key)
    await bus.publish(evt)
    # Just ensure no exception was raised
    assert True
