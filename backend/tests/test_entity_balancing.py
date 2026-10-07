"""Unit tests verifying comparative entity balancing, SKU deduplication, and session counter increments."""

import json
from unittest.mock import MagicMock

from app.data.analytics import AnalyticsService
from app.tools.catalog import query_catalog


def test_query_catalog_deduplicates_identical_skus():
    """Verify query_catalog deduplicates rows sharing the same SKU."""
    mock_client = MagicMock()
    # Simulate BigQuery returning duplicate rows for Dell XPS and Apple MacBook
    mock_client.query_and_wait.return_value = [
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

    results = query_catalog(keywords=["mac", "dell"], client=mock_client)
    assert len(results) == 2
    skus = [r["sku"] for r in results]
    assert skus == ["6575132", "6534606"]


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
