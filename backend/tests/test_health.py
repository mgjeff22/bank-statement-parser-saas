import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_top_level_status(client):
    """Verifies that /api/health responds with HTTP 200 and top-level status 'healthy'."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_health_database_subsystem(client):
    """Verifies SQLite database probe connectivity."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["subsystems"]["database"] == "operational"
    assert data["checks"]["database"]["status"] == "ok"


def test_health_storage_subsystem(client):
    """Verifies file storage writeability probe."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["subsystems"]["storage"] == "operational"
    assert data["checks"]["storage"]["writable"] is True


def test_health_parsing_pipeline_subsystem(client):
    """Verifies statement parsing pipeline readiness probe."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["subsystems"]["parsing_pipeline"] == "operational"
    assert data["checks"]["parsing_pipeline"]["status"] == "ok"


def test_health_billing_adapter_subsystem(client):
    """Verifies billing adapter mode and status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "billing_adapter" in data["subsystems"]
    assert "operational" in data["subsystems"]["billing_adapter"]
    assert data["checks"]["billing"]["status"] == "ok"


def test_health_root_alias(client):
    """Verifies /health root alias returns identical 200 healthy status."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
