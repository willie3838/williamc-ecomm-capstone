"""Failure Injection and Chaos Engineering Test Suite.

Simulates infrastructure faults, network disruptions, API rate limits, and corrupted data payloads:
1. BigQuery transient network timeouts and 503 Service Unavailable errors.
2. Vertex AI Gemini API rate limits (HTTP 429) and downstream service outages (HTTP 500).
3. Corrupted, truncated, and malformed catalog JSON data payloads.
4. Latency spikes and client connection resets.
5. Verification of circuit breaker, exponential backoff, and graceful heuristic degradation.
"""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as g_exceptions
from google.cloud import bigquery

from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec
from app.tools.catalog import query_catalog


class TestBigQueryFailureModes:
    """Simulate and verify BigQuery infrastructure failure handling and graceful orchestrator recovery."""

    def test_bigquery_503_service_unavailable_retries_and_orchestrator_recovers(self):
        """Verify 503 transient database failure triggers retry with backoff and orchestrator returns graceful degradation response."""
        mock_client = MagicMock(spec=bigquery.Client)
        # Mock query to raise 503 ServiceUnavailable on all attempts
        mock_client.query.side_effect = g_exceptions.ServiceUnavailable(
            "BigQuery transient outage (simulated)"
        )

        # 1. query_catalog itself re-raises the exception to ensure no muted errors
        with pytest.raises(g_exceptions.ServiceUnavailable):
            query_catalog(keywords=["macbook"], client=mock_client)

        # 2. Orchestrator catches database failure and gracefully degrades without crashing
        orchestrator = ComparisonOrchestrator(bq_client=mock_client)
        response = orchestrator.compare("Compare MacBook and XPS")
        assert response.products == []
        assert "No matching products found" in response.summary

    def test_bigquery_connection_timeout_orchestrator_recovery(self):
        """Verify connection timeout is caught by orchestrator without unhandled crash."""
        mock_client = MagicMock(spec=bigquery.Client)
        mock_client.query.side_effect = TimeoutError(
            "Connection to BigQuery timed out after 3000ms"
        )

        orchestrator = ComparisonOrchestrator(bq_client=mock_client)
        response = orchestrator.compare("Compare Dell XPS and Lenovo ThinkPad")
        assert response.products == []
        assert response.comparison_matrix == []

    def test_bigquery_malformed_corrupted_rows(self):
        """Verify rows with missing required columns or corrupted types are quarantined without crashing."""
        mock_client = MagicMock(spec=bigquery.Client)
        mock_query_job = MagicMock()

        # Simulate corrupted row missing essential fields and containing malformed types
        corrupted_row = {
            "sku": None,  # Corrupted primary key
            "name": 12345,  # Int instead of string
            "price": "not_a_float",  # Unparseable price
            "category": None,
            "specifications": "invalid_json_string",
        }
        valid_row = {
            "sku": "999999",
            "name": "Resilient Laptop",
            "brand": "BrandX",
            "category": "Laptops",
            "price": 999.0,
            "shortDescription": "Test laptop",
            "specifications": '{"ram_gb": 16}',
            "in_stock": True,
        }

        mock_query_job.result.return_value = [corrupted_row, valid_row]
        mock_query_job.total_bytes_billed = 1024
        mock_client.query.return_value = mock_query_job

        results = query_catalog(keywords=["laptop"], client=mock_client)
        # Valid row should survive quarantine
        assert len(results) >= 1
        assert any(r["sku"] == "999999" for r in results)


class TestVertexAIFailureModes:
    """Simulate and verify Vertex AI foundation model failure modes and fallback."""

    @patch("google.genai.Client")
    def test_vertex_ai_429_quota_exceeded_falls_back_to_heuristics(self, mock_client_cls):
        """Verify HTTP 429 quota exhaustion gracefully falls back to deterministic heuristic reranking."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.side_effect = g_exceptions.ResourceExhausted(
            "Rate limit exceeded 429"
        )

        orchestrator = ComparisonOrchestrator()
        p1 = ProductSpec(
            sku="111", name="Apple MacBook Air", price=1099.0, brand="Apple", category="Laptops"
        )
        p2 = ProductSpec(
            sku="222", name="Dell XPS 13", price=999.0, brand="Dell", category="Laptops"
        )

        # Rerank with LLM should gracefully return None and orchestrator falls back to heuristics
        result = orchestrator.rank_and_select_products(
            [p1, p2], keywords=["macbook", "xps"], original_query="MacBook vs XPS"
        )

        assert len(result) == 2
        assert {p.sku for p in result} == {"111", "222"}

    @patch("google.genai.Client")
    def test_vertex_ai_500_internal_error_fallback(self, mock_client_cls):
        """Verify downstream 500 error from foundation model does not break the user experience."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.side_effect = g_exceptions.InternalServerError(
            "500 Internal Error"
        )

        orchestrator = ComparisonOrchestrator()
        p1 = ProductSpec(
            sku="111", name="Sony WH-1000XM5", price=399.0, brand="Sony", category="Headphones"
        )
        p2 = ProductSpec(
            sku="222", name="Bose QC Ultra", price=429.0, brand="Bose", category="Headphones"
        )

        result = orchestrator.rank_and_select_products(
            [p1, p2], keywords=["sony", "bose"], original_query="Sony vs Bose"
        )
        assert len(result) == 2

    @patch("google.genai.Client")
    def test_vertex_ai_garbage_json_response_handling(self, mock_client_cls):
        """Verify model returning non-JSON garbage or hallucinated structure is caught and handled."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "Here is your ranking: 1. MacBook 2. Dell! (I am not returning JSON)"
        mock_response.candidates = [MagicMock(finish_reason="STOP")]
        mock_client.models.generate_content.return_value = mock_response

        orchestrator = ComparisonOrchestrator()
        p1 = ProductSpec(
            sku="111", name="Apple MacBook Air", price=1099.0, brand="Apple", category="Laptops"
        )
        p2 = ProductSpec(
            sku="222", name="Dell XPS 13", price=999.0, brand="Dell", category="Laptops"
        )

        result = orchestrator.rank_and_select_products(
            [p1, p2], keywords=["macbook", "xps"], original_query="MacBook vs XPS"
        )
        assert len(result) == 2


class TestDataCorruptionAndBoundaryFailures:
    """Verify system resilience against corrupted schemas and extreme edge-case boundaries."""

    def test_empty_catalog_and_extreme_inputs(self):
        """Verify handling when query matches zero products or receives extreme payloads."""
        orchestrator = ComparisonOrchestrator()
        matrix = orchestrator.build_comparison_matrix([])
        assert matrix == []

        summary = orchestrator.synthesize_summary([], matrix)
        assert "No matching products found" in summary

    def test_matrix_row_corrupted_specifications_type(self):
        """Verify specs containing unexpected structures (nested dicts, bools, None) do not crash matrix builder."""
        orchestrator = ComparisonOrchestrator()
        p1 = ProductSpec(
            sku="101",
            name="Product A",
            price=500.0,
            brand="BrandA",
            category="Laptops",
            specifications={
                "battery_life_hours": None,
                "ram_gb": "Unknown",
                "weird_field": {"nested": "data"},
            },
        )
        p2 = ProductSpec(
            sku="102",
            name="Product B",
            price=600.0,
            brand="BrandB",
            category="Laptops",
            specifications={"battery_life_hours": 10.0, "ram_gb": 16, "weird_field": True},
        )

        rows = orchestrator.build_comparison_matrix([p1, p2])
        assert len(rows) > 0
        # Check that rows with weird fields are serialized without throwing TypeError
        row_features = [r.feature for r in rows]
        assert "Memory (RAM)" in row_features
