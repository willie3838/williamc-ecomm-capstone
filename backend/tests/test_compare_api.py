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
    """Verify 422 error on queries exceeding 4000 characters."""
    response = client.post("/api/compare", json={"query": "x" * 4001})
    assert response.status_code == 422


def test_compare_endpoint_query_max_length_4000(mock_bq_client: MagicMock) -> None:
    """Verify 4000-character query is accepted and passes validation."""
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_bq_client.query.return_value = mock_job

    with patch("app.agent.orchestrator.bigquery.Client", return_value=mock_bq_client):
        response = client.post("/api/compare", json={"query": "Compare " + ("x" * 3992)})
    assert response.status_code == 200


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


def test_comparison_request_query_length_boundary() -> None:
    """Test Pydantic model accepts query up to 4000 characters and rejects 4001."""
    import pytest
    from pydantic import ValidationError

    # Exactly 4000 chars - valid
    req_4000 = ComparisonRequest(query="x" * 4000)
    assert len(req_4000.query) == 4000

    # 4001 chars - raises ValidationError
    with pytest.raises(ValidationError):
        ComparisonRequest(query="x" * 4001)


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


def test_catalog_endpoint_all_products() -> None:
    """Verify GET /api/catalog returns full catalog list with 200 OK and valid schema."""
    response = client.get("/api/catalog")
    assert response.status_code == 200
    data = response.json()
    assert "products" in data
    assert "total_count" in data
    assert data["total_count"] > 0
    assert len(data["products"]) == data["total_count"]
    # Check first item structure
    first = data["products"][0]
    assert "sku" in first
    assert "name" in first
    assert "price" in first
    assert "specifications" in first


def test_catalog_endpoint_v1_alias() -> None:
    """Verify GET /api/v1/catalog alias returns identical catalog data."""
    response = client.get("/api/v1/catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] > 0


def test_catalog_endpoint_category_filtering() -> None:
    """Verify GET /api/catalog?category=Headphones filters products correctly."""
    response = client.get("/api/catalog?category=Headphones")
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "Headphones"
    assert data["total_count"] > 0
    for product in data["products"]:
        assert product["category"].lower() == "headphones"


def test_catalog_endpoint_price_filters() -> None:
    """Verify GET /api/catalog with price range filtering."""
    response = client.get("/api/catalog?min_price=1000&max_price=1500")
    assert response.status_code == 200
    data = response.json()
    for product in data["products"]:
        assert 1000.0 <= product["price"] <= 1500.0


def test_compare_routes_no_test_detection_branches_and_session_counter(monkeypatch) -> None:
    """Verify routes/compare.py has zero test-detection branches, keys coordinator cache by class, and increments session_comparison_count without PYTEST_CURRENT_TEST."""
    from pathlib import Path

    import app.routes.compare as compare_mod

    src = Path(compare_mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "PYTEST_CURRENT_TEST",
        "assert_called",
        "_is_test_or_eval_env",
        '"pytest" in sys.modules',
        "'pytest' in sys.modules",
    ):
        assert forbidden not in src, f"Forbidden token {forbidden!r} found in routes/compare.py"

    # Verify _get_coordinator re-instantiates across multiple patch blocks
    with patch("app.routes.compare.MultiAgentCoordinator") as mock_coord_1:
        inst_1 = MagicMock()
        mock_coord_1.return_value = inst_1
        assert compare_mod._get_coordinator("gemini-2.5-flash", None) is inst_1
        assert compare_mod._get_coordinator("gemini-2.5-flash", None) is inst_1
        assert mock_coord_1.call_count == 1

    with patch("app.routes.compare.MultiAgentCoordinator") as mock_coord_2:
        inst_2 = MagicMock()
        mock_coord_2.return_value = inst_2
        assert compare_mod._get_coordinator("gemini-2.5-flash", None) is inst_2
        assert inst_2 is not inst_1
        assert mock_coord_2.call_count == 1

    # Verify session_comparison_count increments accurately when PYTEST_CURRENT_TEST is unset
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with patch("app.main.ComparisonOrchestrator") as mock_orch_cls:
        mock_orch_cls.return_value.compare.side_effect = lambda **kw: ComparisonResponse(
            summary="MacBook Air [SKU: 6534606] vs Dell XPS [SKU: 6575132]",
            products=[],
            comparison_matrix=[],
            citations=[],
            session_id=kw.get("session_id"),
        )
        r1 = client.post(
            "/api/compare",
            json={"query": "MacBook Air vs Dell XPS", "session_id": "sess-prod-counter-1"},
        )
        r2 = client.post(
            "/api/compare",
            json={"query": "MacBook Air vs Dell XPS", "session_id": "sess-prod-counter-1"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["session_comparison_count"] == 1
        assert r2.json()["session_comparison_count"] == 2
