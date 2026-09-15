"""Unit tests for FastAPI health and observability endpoints."""

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import PROJECT_ID, app, create_app

client = TestClient(app)


def test_health_endpoint() -> None:
    """Verify health endpoint returns status 200 and project ID."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "catalog-backend"
    assert data["project"] == PROJECT_ID
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"


def test_readiness_endpoint() -> None:
    """Verify readiness probe returns 200 and ready status."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["service"] == "catalog-backend"
    assert data["project"] == PROJECT_ID


def test_health_custom_settings() -> None:
    """Verify health endpoint reflects custom settings when injected."""
    custom_settings = Settings(
        project_id="custom-fde-project",
        service_name="custom-backend",
        environment="staging",
        api_version="2.0.0",
    )
    custom_app = create_app(settings=custom_settings)
    custom_app.dependency_overrides[get_settings] = lambda: custom_settings
    test_client = TestClient(custom_app)

    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "custom-fde-project"
    assert data["service"] == "custom-backend"
    assert data["environment"] == "staging"
    assert data["version"] == "2.0.0"

    readiness_resp = test_client.get("/health/ready")
    assert readiness_resp.status_code == 200
    rdata = readiness_resp.json()
    assert rdata["project"] == "custom-fde-project"
    assert rdata["service"] == "custom-backend"
