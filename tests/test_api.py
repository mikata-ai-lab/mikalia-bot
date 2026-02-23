"""
test_api.py — Tests para el servidor FastAPI de Mikalia.

Verifica:
- Endpoints basicos (root, health, stats, goals, jobs)
- Health check retorna status correcto
- Stats incluyen token usage y memory counts
- Webhook de GitHub acepta payloads
"""

from __future__ import annotations

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from mikalia.api import create_app
from mikalia.core.memory import MemoryManager


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    db_path = tmp_path / "test_api.db"
    return MemoryManager(str(db_path), str(SCHEMA_PATH))


@pytest.fixture
def client(memory):
    app = create_app(memory=memory)
    return TestClient(app)


# ================================================================
# Root endpoint
# ================================================================

class TestRoot:
    def test_root_returns_info(self, client):
        """GET / retorna info basica de Mikalia."""
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Mikalia"
        assert data["status"] == "alive"
        assert "uptime_seconds" in data

    def test_root_has_signature(self, client):
        """GET / incluye el mensaje firma."""
        resp = client.get("/")
        data = resp.json()
        assert "Stay curious" in data["message"]


# ================================================================
# Health check
# ================================================================

class TestHealth:
    def test_health_returns_healthy(self, client):
        """GET /health retorna healthy cuando DB funciona."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["checks"]["database"] is True

    def test_health_includes_facts_count(self, client):
        """GET /health incluye conteo de facts."""
        resp = client.get("/health")
        data = resp.json()
        assert "facts_count" in data["checks"]
        # Seed data tiene 17 facts
        assert data["checks"]["facts_count"] >= 15

    def test_health_includes_uptime(self, client):
        """GET /health incluye uptime."""
        resp = client.get("/health")
        data = resp.json()
        assert "uptime_seconds" in data["checks"]
        assert data["checks"]["uptime_seconds"] >= 0


# ================================================================
# Stats
# ================================================================

class TestStats:
    def test_stats_returns_token_usage(self, client):
        """GET /stats incluye token usage 24h y 7d."""
        resp = client.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "token_usage" in data
        assert "last_24h" in data["token_usage"]
        assert "last_7d" in data["token_usage"]

    def test_stats_returns_memory_counts(self, client):
        """GET /stats incluye conteos de memoria."""
        resp = client.get("/stats")
        data = resp.json()
        assert "memory" in data
        assert "facts" in data["memory"]
        assert "lessons" in data["memory"]
        assert "goals_active" in data["memory"]

    def test_stats_has_uptime(self, client):
        """GET /stats incluye uptime."""
        resp = client.get("/stats")
        data = resp.json()
        assert "uptime_seconds" in data


# ================================================================
# Goals
# ================================================================

class TestGoals:
    def test_goals_returns_list(self, client):
        """GET /goals retorna lista de goals activos."""
        resp = client.get("/goals")
        assert resp.status_code == 200
        data = resp.json()
        assert "goals" in data
        assert "total" in data
        assert isinstance(data["goals"], list)

    def test_goals_have_fields(self, client):
        """Cada goal tiene project, title, status, priority, progress."""
        resp = client.get("/goals")
        data = resp.json()
        if data["total"] > 0:
            goal = data["goals"][0]
            assert "project" in goal
            assert "title" in goal
            assert "priority" in goal
            assert "progress" in goal


# ================================================================
# Jobs
# ================================================================

class TestJobs:
    def test_jobs_returns_list(self, client):
        """GET /jobs retorna lista de scheduled jobs."""
        resp = client.get("/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert "jobs" in data
        assert data["total"] == 4  # 4 seed jobs

    def test_jobs_have_cron_fields(self, client):
        """Cada job tiene name, cron, enabled."""
        resp = client.get("/jobs")
        data = resp.json()
        job = data["jobs"][0]
        assert "name" in job
        assert "cron" in job
        assert "enabled" in job
        assert "last_run" in job


# ================================================================
# GitHub Webhook
# ================================================================

class TestGitHubWebhook:
    def test_webhook_accepts_payload(self, client):
        """POST /webhook/github acepta un payload JSON."""
        payload = {
            "action": "opened",
            "pull_request": {"title": "Test PR"},
        }
        resp = client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["received"] is True
        assert data["event"] == "pull_request"

    def test_webhook_handles_push_event(self, client):
        """POST /webhook/github maneja push events."""
        payload = {"ref": "refs/heads/main", "commits": []}
        resp = client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event"] == "push"
