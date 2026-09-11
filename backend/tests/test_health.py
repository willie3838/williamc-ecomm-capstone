"""Unit tests for FastAPI health and API endpoints."""

from fastapi.testclient import TestClient

from app.main import PROJECT_ID, app

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


def test_compare_endpoint_scaffold() -> None:
    """Verify compare endpoint accepts valid payload and returns structured response."""
    response = client.post(
        "/api/compare",
        json={"query": "Compare MacBook Air M3 and Dell XPS 13", "category": "Laptops"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "products" in data
    assert "comparison_matrix" in data
    assert "citations" in data


def test_compare_endpoint_invalid_empty() -> None:
    """Verify validation error on query that is too short."""
    response = client.post("/api/compare", json={"query": "a"})
    assert response.status_code == 422  # Pydantic min_length validation error


def test_compare_endpoint_whitespace_only() -> None:
    """Verify 400 Bad Request error on query containing only whitespace."""
    response = client.post("/api/compare", json={"query": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "Query string must not be empty."
