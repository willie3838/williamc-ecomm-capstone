"""Unit tests for FastAPI compare API endpoint and OpenAPI documentation."""

from fastapi.testclient import TestClient

from app.main import app
from app.models import ComparisonRequest, ComparisonResponse

client = TestClient(app)


def test_compare_endpoint_valid_request() -> None:
    """Verify compare endpoint accepts valid payload and returns compliant schema."""
    payload = {
        "query": "Compare MacBook Air M3 and Dell XPS 13",
        "category": "Laptops",
        "top_k": 3,
    }
    response = client.post("/api/compare", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Validate against Pydantic model
    validated = ComparisonResponse.model_validate(data)
    assert "MacBook Air M3" in validated.summary
    assert validated.latency_ms is not None
    assert validated.latency_ms >= 0.0
    assert isinstance(validated.products, list)
    assert isinstance(validated.comparison_matrix, list)
    assert isinstance(validated.citations, list)


def test_compare_endpoint_minimal_query() -> None:
    """Verify compare endpoint works with minimal required fields."""
    response = client.post(
        "/api/compare",
        json={"query": "Find best headphones with ANC"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "headphones" in data["summary"].lower()


def test_compare_endpoint_query_too_short() -> None:
    """Verify 422 validation error when query length is less than 3 chars."""
    response = client.post("/api/compare", json={"query": "ab"})
    assert response.status_code == 422


def test_compare_endpoint_whitespace_only() -> None:
    """Verify 400 Bad Request error when query contains only whitespace."""
    response = client.post("/api/compare", json={"query": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "Query string must not be empty."


def test_compare_endpoint_query_too_long() -> None:
    """Verify 422 validation error when query exceeds 500 characters."""
    response = client.post("/api/compare", json={"query": "x" * 501})
    assert response.status_code == 422


def test_compare_endpoint_top_k_bounds() -> None:
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
    resp_valid = client.post(
        "/api/compare",
        json={"query": "Valid query", "top_k": 10},
    )
    assert resp_valid.status_code == 200


def test_compare_endpoint_category_sanitization() -> None:
    """Verify whitespace-only category is stripped to None without failing validation."""
    response = client.post(
        "/api/compare",
        json={"query": "Valid query", "category": "   "},
    )
    assert response.status_code == 200

    # Also test explicit None/null
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

    assert schema["info"]["title"] == "Best Buy Catalog Comparison Agent API"
    paths = schema["paths"]
    assert "/health" in paths
    assert "/health/ready" in paths
    assert "/api/compare" in paths

    schemas = schema["components"]["schemas"]
    assert "ComparisonRequest" in schemas
    assert "ComparisonResponse" in schemas
    assert "HealthResponse" in schemas
    assert "MatrixRow" in schemas
    assert "ProductItem" in schemas
    assert "Citation" in schemas


def test_interactive_docs_endpoints() -> None:
    """Verify Swagger UI and ReDoc documentation endpoints return 200 OK."""
    swagger_resp = client.get("/docs")
    assert swagger_resp.status_code == 200

    redoc_resp = client.get("/redoc")
    assert redoc_resp.status_code == 200
