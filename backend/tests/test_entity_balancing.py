"""Unit tests verifying comparative entity balancing, SKU deduplication, and session counter increments."""

import json
from unittest.mock import MagicMock, patch

from app.agent.orchestrator import ComparisonOrchestrator
from app.data.analytics import AnalyticsService
from app.models.responses import ProductSpec
from app.tools.catalog import query_catalog


def test_query_catalog_deduplicates_identical_skus():
    """Verify query_catalog deduplicates rows sharing the same SKU."""
    mock_job = MagicMock()
    # Simulate BigQuery returning duplicate rows for Dell XPS and Apple MacBook
    mock_job.result.return_value = [
        {
            "sku": "6575132",
            "name": 'Dell - XPS 13" Laptop',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
            "rating": 4.5,
            "review_count": 200,
            "specifications": json.dumps({"ram_gb": 16}),
            "url": "https://example.com/dell",
            "in_stock": True,
        },
        {
            "sku": "6575132",
            "name": 'Dell - XPS 13" Laptop (Duplicate)',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
            "rating": 4.5,
            "review_count": 200,
            "specifications": json.dumps({"ram_gb": 16}),
            "url": "https://example.com/dell",
            "in_stock": True,
        },
        {
            "sku": "6534606",
            "name": 'Apple - MacBook Air 13.6"',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "rating": 4.8,
            "review_count": 500,
            "specifications": json.dumps({"ram_gb": 16}),
            "url": "https://example.com/mac",
            "in_stock": True,
        },
    ]

    mock_client = MagicMock()
    mock_client.query.return_value = mock_job

    results = query_catalog(keywords=["mac", "dell"], client=mock_client)
    assert len(results) == 2
    skus = [r["sku"] for r in results]
    assert skus == ["6575132", "6534606"]


def test_rank_and_select_products_balances_mac_vs_dell():
    """Verify rank_and_select_products selects 1 Apple product and 1 Dell product, never 2 Dells."""
    candidates = [
        ProductSpec(
            sku="6575132",
            name='Dell - XPS 13" Laptop',
            brand="Dell",
            category="Laptops",
            price=1199.0,
            specifications={"ram_gb": 16},
        ),
        ProductSpec(
            sku="6575133",
            name='Dell - Inspiron 15" Laptop',
            brand="Dell",
            category="Laptops",
            price=799.0,
            specifications={"ram_gb": 16},
        ),
        ProductSpec(
            sku="6534606",
            name='Apple - MacBook Air 13.6" Laptop - M3',
            brand="Apple",
            category="Laptops",
            price=1099.0,
            specifications={"ram_gb": 16},
        ),
    ]

    orchestrator = ComparisonOrchestrator()
    # Force heuristic path
    with patch.object(orchestrator, "_rerank_with_llm", return_value=None):
        selected = orchestrator.rank_and_select_products(
            candidates, keywords=["mac", "dell"], original_query="mac vs dell"
        )

    assert len(selected) >= 2
    top_two = selected[:2]
    brands = {p.brand.lower() for p in top_two}
    assert "apple" in brands, (
        f"Expected Apple in comparison results, got: {[p.name for p in top_two]}"
    )
    assert "dell" in brands, (
        f"Expected Dell in comparison results, got: {[p.name for p in top_two]}"
    )


def test_rank_and_select_products_preserves_intra_brand_macbook_air_vs_pro():
    """Verify intra-brand queries (MacBook Air vs MacBook Pro) do not promote unrelated brands (Dell) into top 2."""
    candidates = [
        ProductSpec(
            sku="6534606",
            name='Apple - MacBook Air 13.6" Laptop - M3',
            brand="Apple",
            category="Laptops",
            price=1099.0,
            specifications={"ram_gb": 16},
        ),
        ProductSpec(
            sku="6534640",
            name='Apple - MacBook Pro 14" Laptop - M3 Pro',
            brand="Apple",
            category="Laptops",
            price=1999.0,
            specifications={"ram_gb": 18},
        ),
        ProductSpec(
            sku="6575132",
            name='Dell - XPS 13" Laptop',
            brand="Dell",
            category="Laptops",
            price=1199.0,
            specifications={"ram_gb": 16},
        ),
    ]

    orchestrator = ComparisonOrchestrator()
    with patch.object(orchestrator, "_rerank_with_llm", return_value=None):
        selected = orchestrator.rank_and_select_products(
            candidates,
            keywords=["MacBook Air 13 M3", "MacBook Pro 14 M3 Pro"],
            original_query="What are the key differences between MacBook Air 13 M3 and MacBook Pro 14 M3 Pro?",
        )

    assert len(selected) >= 2
    top_two_skus = [p.sku for p in selected[:2]]
    assert top_two_skus == ["6534606", "6534640"]


def test_analytics_service_in_memory_session_counter():
    """Verify analytics service increments session counter in-memory when Firestore is unavailable."""
    service = AnalyticsService(disable_cloud_clients=True)
    session_id = "test-offline-session-123"

    count1 = service.increment_session_comparisons(session_id)
    assert count1 == 1

    count2 = service.increment_session_comparisons(session_id)
    assert count2 == 2

    count3 = service.increment_session_comparisons(session_id)
    assert count3 == 3

    # Distinct session starts at 1
    other_count = service.increment_session_comparisons("different-session-456")
    assert other_count == 1
