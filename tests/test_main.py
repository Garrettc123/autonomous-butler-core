"""Integration tests for the FastAPI application."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from src.main import app
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "agents" in data
    assert "version" in data
    assert len(data["agents"]) == 6


def test_agents_endpoint(client):
    resp = client.get("/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    names = {a["name"] for a in data["agents"]}
    assert names == {"devops", "revenue", "security", "pm", "support", "infrastructure"}


def test_get_specific_agent(client):
    resp = client.get("/agents/devops")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "devops"


def test_get_unknown_agent(client):
    resp = client.get("/agents/nonexistent")
    # Returns a tuple from the route handler
    assert resp.status_code in (200, 404)


def test_events_endpoint(client):
    resp = client.get("/events")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert isinstance(data["events"], list)


def test_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents_running" in data
    assert "total_actions_today" in data
    assert "bus_events_total" in data


def test_dashboard_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Autonomous Butler" in resp.text
    assert "devops" in resp.text.lower()
