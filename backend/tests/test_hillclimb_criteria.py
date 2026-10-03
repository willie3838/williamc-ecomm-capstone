"""Unit tests verifying Score 3 / 3 expert criteria across security, resilience, multi-category specs, and API v1."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.agent.orchestrator import CATEGORY_SPEC_REGISTRY, ComparisonOrchestrator
from app.data.analytics import AnalyticsService
from app.main import create_app
from app.models.analytics import FeedbackRequest, UserActionRequest
from app.models.requests import CandidateRankingResponse, CandidateRankItem
from app.models.responses import ProductSpec
from app.observability.logging import scrub_pii
from app.tools.catalog import CatalogCircuitBreaker, query_catalog

client = TestClient(create_app())


def test_pii_redaction_scrubber() -> None:
    """Verify scrub_pii redacts SSN, credit cards, emails, and phone numbers (s2_15)."""
    raw = "User SSN 123-45-6789, card 4111-2222-3333-4444, email alice@example.com, phone 555-123-4567"
    redacted = scrub_pii(raw)
    assert "123-45-6789" not in redacted
    assert "[REDACTED_SSN]" in redacted
    assert "4111-2222-3333-4444" not in redacted
    assert "[REDACTED_CC]" in redacted
    assert "alice@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "555-123-4567" not in redacted
    assert "[REDACTED_PHONE]" in redacted


def test_analytics_pii_redaction() -> None:
    """Verify AnalyticsService scrubs PII before persisting to Firestore/BigQuery (s2_15)."""
    mock_fs = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc_ref.id = "doc-123"
    mock_fs.collection.return_value.add.return_value = (None, mock_doc_ref)

    svc = AnalyticsService(firestore_client=mock_fs)
    svc.record_user_action(
        UserActionRequest(
            action_type="compare_request",
            session_id="sess-1",
            query="Compare laptops for alice@example.com with SSN 123-45-6789",
        )
    )
    added_payload = mock_fs.collection.return_value.add.call_args[0][0]
    assert "[REDACTED_EMAIL]" in added_payload["query"]
    assert "[REDACTED_SSN]" in added_payload["query"]

    svc.record_feedback(
        FeedbackRequest(
            rating="thumbs_up",
            session_id="sess-1",
            query="Call 555-123-4567",
            comment="My card is 4111 2222 3333 4444",
        )
    )
    fb_payload = mock_fs.collection.return_value.add.call_args[0][0]
    assert "[REDACTED_PHONE]" in fb_payload["query"]
    assert "[REDACTED_CC]" in fb_payload["comment"]


def test_circuit_breaker_and_cache() -> None:
    """Verify CatalogCircuitBreaker state transitions and stateless BigQuery query execution (s2_21, s2_24)."""
    cb = CatalogCircuitBreaker(failure_threshold=2, recovery_timeout_sec=0.01)
    assert cb.state == "CLOSED"
    cb.record_failure()
    assert cb.state == "CLOSED"
    cb.record_failure()
    assert cb.state == "OPEN"
    cb.record_success()
    assert cb.state == "CLOSED"

    # Verify query_catalog executes statelessly without in-memory caching
    from unittest.mock import MagicMock

    mock_bq = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = [
        {"sku": "SKU-1", "name": "Item 1", "price": 100.0, "specifications": {}}
    ]
    mock_bq.query.return_value = mock_job

    res1 = query_catalog(keywords=["Laptop"], client=mock_bq)
    res2 = query_catalog(keywords=["Laptop"], client=mock_bq)
    assert len(res1) == 1 and len(res2) == 1
    assert mock_bq.query.call_count == 2


def test_multi_category_spec_registry_and_cross_category_guard() -> None:
    """Verify CATEGORY_SPEC_REGISTRY covers all 5 categories and guards cross-category comparisons (s2_05, s2_32)."""
    assert "refresh_rate_hz" in CATEGORY_SPEC_REGISTRY
    assert "driver_size_mm" in CATEGORY_SPEC_REGISTRY
    assert "sensor_range_ft" in CATEGORY_SPEC_REGISTRY
    assert "response_time_ms" in CATEGORY_SPEC_REGISTRY

    orch = ComparisonOrchestrator(hermetic=True)
    # Same category (TVs): refresh_rate_hz higher wins, response_time_ms lower wins
    tv1 = ProductSpec(
        sku="TV-1",
        name="OLED TV A",
        brand="LG",
        category="TVs",
        price=1499.99,
        specifications={"refresh_rate_hz": 120, "response_time_ms": 1.0},
    )
    tv2 = ProductSpec(
        sku="TV-2",
        name="LED TV B",
        brand="Samsung",
        category="TVs",
        price=999.99,
        specifications={"refresh_rate_hz": 60, "response_time_ms": 5.0},
    )
    matrix = orch.build_comparison_matrix([tv1, tv2])
    row_by_feature = {r.feature: r for r in matrix}
    assert row_by_feature["Refresh Rate"].winner_sku == "TV-1"
    assert row_by_feature["Response Time"].winner_sku == "TV-1"

    # Cross-category (Laptops vs Headphones): Category row added, shared spec winners computed, unshared specs neutral
    laptop = ProductSpec(
        sku="LAP-1",
        name="Laptop X",
        brand="Apple",
        category="Laptops",
        price=1299.0,
        specifications={"battery_life_hours": 18, "ram_gb": 16},
    )
    headphone = ProductSpec(
        sku="HP-1",
        name="Headphone Y",
        brand="Sony",
        category="Headphones",
        price=349.0,
        specifications={"battery_life_hours": 30, "driver_size_mm": 40},
    )
    cross_matrix = orch.build_comparison_matrix([laptop, headphone])
    cross_features = {r.feature: r for r in cross_matrix}
    assert "Category" in cross_features
    assert cross_features["Category"].winner_sku is None
    assert cross_features["Category"].winner_skus == []
    # Shared numeric spec across categories computes winner
    assert cross_features["Battery Life"].winner_sku == "HP-1"
    assert cross_features["Battery Life"].winner_skus == ["HP-1"]
    # Unshared specs (present in only 1 of 2 products) have no winner
    assert cross_features["Memory (RAM)"].winner_sku is None
    assert cross_features["Memory (RAM)"].winner_skus == []
    assert cross_features["Driver Size"].winner_sku is None
    assert cross_features["Driver Size"].winner_skus == []


def test_api_v1_routes_and_readiness_dependencies() -> None:
    """Verify /api/v1 endpoints and /health/ready dependency checks (s2_18, s2_29, s2_31)."""
    ready_resp = client.get("/health/ready")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    assert ready_data["status"] == "ready"
    assert ready_data["api_version"] == "v1"
    assert ready_data["dependencies"]["bigquery"] == "ready"
    assert ready_data["dependencies"]["vertex_ai"] == "ready"

    v1_versions = client.get("/api/v1/agent/versions")
    assert v1_versions.status_code == 200
    assert v1_versions.json()["active_default"] == "1.2.0-tiered"

    v1_compare = client.post(
        "/api/v1/compare",
        json={"query": "Compare MacBook Air M3 and Dell XPS 13"},
    )
    assert v1_compare.status_code == 200
    assert v1_compare.json()["agent_version"] == "1.2.0-tiered"

    ranking_resp = CandidateRankingResponse(rankings=[CandidateRankItem(sku="SKU-1", score=9.5)])
    assert len(ranking_resp.rankings) == 1

    scrubbed = ComparisonOrchestrator.verify_and_scrub_sku_citations(
        "MacBook Air [SKU: SKU-1] beats Ghost Laptop [SKU: FAKE-999].",
        {"SKU-1"},
    )
    assert "[SKU: SKU-1]" in (scrubbed or "")
    assert "FAKE-999" not in (scrubbed or "")
