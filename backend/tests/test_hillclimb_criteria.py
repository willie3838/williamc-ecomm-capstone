"""Unit tests verifying Score 3 / 3 expert criteria across security, resilience, multi-category specs, and API v1."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.agent.orchestrator as orchestrator_mod
from app.agent.orchestrator import ComparisonOrchestrator
from app.data.analytics import AnalyticsService
from app.main import create_app
from app.models.analytics import FeedbackRequest, UserActionRequest
from app.models.comparison import ComparisonSynthesis
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


def test_multi_category_spec_winners_and_cross_category_guard() -> None:
    """Verify Stage 4 LLM spec_winners replaces CATEGORY_SPEC_REGISTRY across categories and guards cross-category comparisons (s2_05, s2_32)."""
    assert not hasattr(orchestrator_mod, "CATEGORY_SPEC_REGISTRY")

    synth = ComparisonSynthesis(
        recommendation="Sony WH-1000XM5 [SKU: 6505727] wins on Bluetooth and lighter weight.",
        key_differences=["Bluetooth 5.3 vs 5.2 [SKU: 6505727]"],
        tradeoffs=["Higher price [SKU: 6505727]"],
        winner_sku="6505727",
        confidence_score=0.95,
        spec_winners={
            "bluetooth_version": "6505727",
            "weight_oz": "6505727",
            "battery_life_hours": "tie",
            "voice_assistant": "none",
        },
    )
    assert synth.spec_winners["bluetooth_version"] == "6505727"
    assert synth.spec_winners["weight_oz"] == "6505727"

    orch = ComparisonOrchestrator()
    hp1 = ProductSpec(
        sku="6505727",
        name="Sony WH-1000XM5",
        brand="Sony",
        category="Headphones",
        price=399.99,
        specifications={
            "bluetooth_version": "5.3",
            "weight_oz": "8.8 oz",
            "battery_life_hours": 30,
            "voice_assistant": "Alexa, Google Assistant",
        },
    )
    hp2 = ProductSpec(
        sku="6554461",
        name="Apple AirPods Max",
        brand="Apple",
        category="Headphones",
        price=549.99,
        specifications={
            "bluetooth_version": "5.0",
            "weight_oz": "13.6 oz",
            "battery_life_hours": 30,
            "voice_assistant": "Siri",
        },
    )
    matrix = orch.build_comparison_matrix([hp1, hp2], spec_winners=synth.spec_winners)
    row_by_feature = {r.feature: r for r in matrix}
    assert row_by_feature["Bluetooth Version"].winner_sku == "6505727"
    assert row_by_feature["Weight (oz)"].winner_sku == "6505727"
    assert row_by_feature["Battery Life"].winner_sku is None
    assert row_by_feature["Battery Life"].winner_skus == []
    assert row_by_feature["Voice Assistant"].winner_sku is None
    assert row_by_feature["Voice Assistant"].winner_skus == []

    # Fallback numeric/version evaluation when spec_winners is omitted:
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
    tv_matrix = orch.build_comparison_matrix([tv1, tv2])
    tv_rows = {r.feature: r for r in tv_matrix}
    assert tv_rows["Refresh Rate"].winner_sku == "TV-1"
    assert tv_rows["Response Time"].winner_sku == "TV-1"

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
    assert cross_features["Battery Life"].winner_sku == "HP-1"
    assert cross_features["Battery Life"].winner_skus == ["HP-1"]
    assert cross_features["Memory (RAM)"].winner_sku is None
    assert cross_features["Memory (RAM)"].winner_skus == []
    assert cross_features["Driver Size"].winner_sku is None
    assert cross_features["Driver Size"].winner_skus == []


def test_adk_llm_replaces_hermetic_adapter_and_catalog_fails_fast() -> None:
    """Verify app.agent.adk_llm exists, hermetic_adapter is removed, and /api/catalog fails fast with 503."""
    import importlib

    adk_llm = importlib.import_module("app.agent.adk_llm")
    assert hasattr(adk_llm, "CatalogAdkLlm")
    assert hasattr(adk_llm, "verify_and_scrub_synthesis_claims")

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.agent.hermetic_adapter")

    with patch("app.tools.catalog.query_catalog", side_effect=RuntimeError("BQ down")):
        resp = client.get("/api/catalog")
        assert resp.status_code == 503


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

    with patch("app.main.ComparisonOrchestrator") as mock_orch_cls:
        from app.models.responses import ComparisonResponse

        mock_orch_cls.return_value.compare.return_value = ComparisonResponse(
            summary="MacBook Air M3 [SKU: 6534606] is recommended.",
            products=[],
            comparison_matrix=[],
            citations=[],
            recommendations="MacBook Air M3 [SKU: 6534606] is recommended.",
            agent_version="1.2.0-tiered",
        )
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
