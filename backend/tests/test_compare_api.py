"""Unit tests for FastAPI compare API endpoint, models, and OpenAPI documentation."""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import ComparisonRequest, ComparisonResponse

client = TestClient(app)


def test_compare_endpoint_valid_request(mock_bq_client: MagicMock) -> None:
    """Verify compare endpoint accepts valid payload and returns compliant schema."""
    sample_rows = [
        {
            "sku": "6534606",
            "name": 'Apple - MacBook Air 13.6" - M3',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "rating": 4.8,
            "review_count": 520,
            "specifications": json.dumps(
                {
                    "processor": "Apple M3 8-core",
                    "ram_gb": 16,
                    "storage_gb": 512,
                    "battery_life_hours": 18.0,
                }
            ),
            "url": "https://www.techbuy.com/site/sku/6534606.p",
            "image_url": "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6534/6534606_sd.jpg",
            "in_stock": True,
        },
        {
            "sku": "6575132",
            "name": 'Dell - XPS 13" - Intel Core Ultra 7',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
            "rating": 4.5,
            "review_count": 210,
            "specifications": json.dumps(
                {
                    "processor": "Intel Core Ultra 7",
                    "ram_gb": 16,
                    "storage_gb": 512,
                    "battery_life_hours": 14.0,
                }
            ),
            "url": "https://www.techbuy.com/site/sku/6575132.p",
            "image_url": "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6575/6575132_sd.jpg",
            "in_stock": True,
        },
    ]

    mock_job = MagicMock()
    mock_job.result.return_value = sample_rows
    mock_bq_client.query.return_value = mock_job

    payload = {
        "query": "Compare MacBook Air M3 and Dell XPS 13",
        "category": "Laptops",
        "top_k": 3,
    }
    with patch("app.agent.orchestrator.bigquery.Client", return_value=mock_bq_client):
        response = client.post("/api/compare", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Validate against Pydantic model
    validated = ComparisonResponse.model_validate(data)
    assert len(validated.products) == 2
    assert validated.latency_ms is not None
    assert validated.latency_ms >= 0.0
    assert isinstance(validated.products, list)
    assert isinstance(validated.comparison_matrix, list)
    assert isinstance(validated.citations, list)


def test_compare_endpoint_minimal_query(mock_bq_client: MagicMock) -> None:
    """Verify compare endpoint works with minimal required fields."""
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_bq_client.query.return_value = mock_job

    with patch("app.agent.orchestrator.bigquery.Client", return_value=mock_bq_client):
        response = client.post(
            "/api/compare",
            json={"query": "Find best headphones with ANC"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "headphones" in data["summary"].lower() or "not found" in data["summary"].lower()


def test_compare_endpoint_query_too_short() -> None:
    """Verify 422 Unprocessable Entity error on query shorter than 3 characters."""
    response = client.post("/api/compare", json={"query": "a"})
    assert response.status_code == 422


def test_compare_endpoint_whitespace_only() -> None:
    """Verify 400 Bad Request error on query containing only whitespace."""
    response = client.post("/api/compare", json={"query": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "Query string must not be empty."


def test_compare_endpoint_query_too_long() -> None:
    """Verify 422 error on queries exceeding 500 characters."""
    response = client.post("/api/compare", json={"query": "x" * 501})
    assert response.status_code == 422


def test_compare_endpoint_top_k_bounds(mock_bq_client: MagicMock) -> None:
    """Verify validation boundaries for top_k parameter (1 to 10)."""
    # Below minimum
    resp_low = client.post(
        "/api/compare",
        json={"query": "Valid query", "top_k": 0},
    )
    assert resp_low.status_code == 422

    # Above maximum
    resp_high = client.post(
        "/api/compare",
        json={"query": "Valid query", "top_k": 11},
    )
    assert resp_high.status_code == 422

    # Within boundary
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_bq_client.query.return_value = mock_job
    with patch("app.agent.orchestrator.bigquery.Client", return_value=mock_bq_client):
        resp_valid = client.post(
            "/api/compare",
            json={"query": "Valid query", "top_k": 10},
        )
    assert resp_valid.status_code == 200


def test_compare_endpoint_category_sanitization(mock_bq_client: MagicMock) -> None:
    """Verify whitespace-only category is stripped to None without failing validation."""
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_bq_client.query.return_value = mock_job

    with patch("app.agent.orchestrator.bigquery.Client", return_value=mock_bq_client):
        response = client.post(
            "/api/compare",
            json={"query": "Valid query", "category": "   "},
        )
    assert response.status_code == 200

    with patch("app.agent.orchestrator.bigquery.Client", return_value=mock_bq_client):
        resp_null = client.post(
            "/api/compare",
            json={"query": "Valid query", "category": None},
        )
    assert resp_null.status_code == 200


def test_comparison_request_direct_instantiation() -> None:
    """Test model validation with explicit null category."""
    req = ComparisonRequest(query="Valid query", category=None)
    assert req.category is None


def test_cors_preflight_headers() -> None:
    """Verify CORS preflight OPTIONS request returns appropriate headers."""
    response = client.options(
        "/api/compare",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_openapi_schema_endpoint() -> None:
    """Verify OpenAPI 3.1 JSON schema contains all defined routes and models."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    assert "Catalog Comparison Agent API" in schema["info"]["title"]
    paths = schema["paths"]
    assert "/health" in paths
    assert "/health/ready" in paths
    assert "/api/compare" in paths

    schemas = schema["components"]["schemas"]
    assert "ComparisonRequest" in schemas
    assert "ComparisonResponse" in schemas
    assert "HealthResponse" in schemas
    assert "MatrixRow" in schemas
    assert "Citation" in schemas


def test_interactive_docs_endpoints() -> None:
    """Verify Swagger UI and ReDoc documentation endpoints return 200 OK."""
    swagger_resp = client.get("/docs")
    assert swagger_resp.status_code == 200

    redoc_resp = client.get("/redoc")
    assert redoc_resp.status_code == 200


def test_compare_endpoint_opinion_query_suppresses_matrix() -> None:
    """Verify POST /api/compare with subjective opinion query suppresses comparison matrix."""
    response = client.post(
        "/api/compare",
        json={"query": "this is a stupid laptop"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["comparison_matrix"] == []
    assert data["products"] == []
    assert "opinion or general comment" in data["summary"].lower()
