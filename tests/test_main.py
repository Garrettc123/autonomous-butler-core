"""Tests for Autonomous Butler Core API"""
import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_root():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Autonomous Butler Core"
    assert data["status"] == "operational"
    assert "version" in data


def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "autonomous-butler-core"


def test_list_agents():
    """Test agents listing endpoint"""
    response = client.get("/api/v1/agents")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert len(data["agents"]) == 6
    
    agent_ids = [agent["id"] for agent in data["agents"]]
    expected_ids = ["devops", "revenue", "security", "infrastructure", "pm", "support"]
    assert agent_ids == expected_ids


def test_system_status():
    """Test system status endpoint"""
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "components" in data
    assert "metrics" in data
    assert data["components"]["orchestrator"] == "healthy"
