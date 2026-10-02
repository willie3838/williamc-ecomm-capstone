"""Unit tests for query_catalog BigQuery tool."""

import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.models.requests import CatalogQueryInput
from app.tools.catalog import query_catalog


def test_catalog_query_input_validation():
    """Verify Pydantic validation on CatalogQueryInput schema."""
    valid_input = CatalogQueryInput(
        keywords=["MacBook", "Dell XPS"],
        category="Laptops",
        min_price=500.0,
        max_price=2000.0,
        limit=5,
    )
    assert valid_input.keywords == ["MacBook", "Dell XPS"]
    assert valid_input.category == "Laptops"
    assert valid_input.limit == 5

    with pytest.raises(ValidationError):
        # limit must be >= 1 and <= 50
        CatalogQueryInput(keywords=["iPad"], limit=0)


def test_query_catalog_empty_keywords(mock_bq_client):
    """Verify that empty keywords list returns an empty list without querying BigQuery."""
    result = query_catalog(keywords=[], client=mock_bq_client)
    assert result == []
    mock_bq_client.query.assert_not_called()


def test_query_catalog_success(mock_bq_client):
    """Verify parameterized query execution and response formatting."""
    mock_query_job = MagicMock()
    mock_rows = [
        {
            "sku": "6534606",
            "name": 'Apple - MacBook Air 13.6" Laptop - M3 - 16GB Memory - 512GB SSD - Midnight',
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
            "name": 'Dell - XPS 13" Laptop - Intel Core Ultra 7 - 16GB Memory - 512GB SSD - Platinum',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
            "rating": 4.5,
            "review_count": 210,
            "specifications": {
                "processor": "Intel Core Ultra 7 155H",
                "ram_gb": 16,
                "storage_gb": 512,
                "battery_life_hours": 14.0,
            },
            "url": None,
            "image_url": None,
            "in_stock": True,
        },
    ]

    mock_query_job.result.return_value = mock_rows
    mock_bq_client.query.return_value = mock_query_job

    results = query_catalog(
        keywords=["MacBook Air", "Dell XPS"],
        category="Laptops",
        min_price=900.0,
        max_price=1500.0,
        limit=2,
        client=mock_bq_client,
    )

    assert len(results) == 2
    mock_bq_client.query.assert_called_once()
    sql_arg = mock_bq_client.query.call_args[0][0]
    job_config = mock_bq_client.query.call_args[1]["job_config"]

    # Assert SQL is parameterized and contains table reference
    assert "catalog.products" in sql_arg
    assert "@product_patterns" in sql_arg
    assert "@category" in sql_arg
    assert "@min_price" in sql_arg
    assert "@max_price" in sql_arg
    assert "@limit" in sql_arg

    # Assert parameters passed safely
    param_names = {p.name for p in job_config.query_parameters}
    assert param_names == {"product_patterns", "category", "min_price", "max_price", "limit"}

    # Assert results data mapping & URL fallback
    first = results[0]
    assert first["sku"] == "6534606"
    assert first["brand"] == "Apple"
    assert first["price"] == 1099.0
    assert isinstance(first["specifications"], dict)
    assert first["specifications"]["ram_gb"] == 16
    assert first["url"] == "https://www.techbuy.com/site/sku/6534606.p"

    second = results[1]
    assert second["sku"] == "6575132"
    assert second["brand"] == "Dell"
    assert second["url"] == "https://www.techbuy.com/site/sku/6575132.p"  # Fallback generated


def test_query_catalog_handles_exceptions(mock_bq_client):
    """Verify that query_catalog handles BigQuery errors gracefully."""
    mock_bq_client.query.side_effect = RuntimeError("BigQuery connection failed")

    with pytest.raises(RuntimeError) as exc_info:
        query_catalog(keywords=["MacBook"], client=mock_bq_client)

    assert "BigQuery" in str(exc_info.value)


def test_query_catalog_whitespace_keywords(mock_bq_client):
    """Verify whitespace-only keywords return empty list."""
    results = query_catalog(keywords=["  ", ""], client=mock_bq_client)
    assert results == []
    mock_bq_client.query.assert_not_called()


def test_query_catalog_invalid_specifications_json(mock_bq_client):
    """Verify fallback to empty dict when specifications contains invalid JSON."""
    mock_query_job = MagicMock()
    mock_rows = [
        {
            "sku": "9999999",
            "name": "Invalid Specs Item",
            "brand": "Generic",
            "category": "Tablets",
            "price": 99.0,
            "specifications": "{broken-json:",
            "url": "https://example.com",
            "in_stock": True,
        },
        {
            "sku": "8888888",
            "name": "None Specs Item",
            "brand": "Generic",
            "category": "Tablets",
            "price": 120.0,
            "specifications": None,
            "url": "https://example.com",
            "in_stock": True,
        },
    ]
    mock_query_job.result.return_value = mock_rows
    mock_bq_client.query.return_value = mock_query_job

    results = query_catalog(keywords=["Generic"], client=mock_bq_client)
    assert len(results) == 2
    assert results[0]["specifications"] == {}
    assert results[1]["specifications"] == {}


def test_catalog_cache_and_snapshot_helpers(monkeypatch):
    """Verify CatalogResponseCache, CatalogCircuitBreaker, warm_full_catalog_cache, and _match_from_snapshot behavior."""
    import app.tools.catalog as catalog_mod
    from app.tools.catalog import (
        CatalogCircuitBreaker,
        CatalogResponseCache,
        _match_from_snapshot,
        warm_full_catalog_cache,
    )

    cache = CatalogResponseCache(max_size=2, ttl_seconds=60)
    assert cache.get("missing") is None
    lock1 = cache.get_inflight_lock("k1")
    assert lock1 is cache.get_inflight_lock("k1")
    for idx in range(5):
        cache.get_inflight_lock(f"overflow-{idx}")
    cache.set("k1", [{"sku": "1"}])
    cache.set("k2", [{"sku": "2"}])
    cache.set("k3", [{"sku": "3"}])
    assert cache.get("k1") is None
    assert cache.get("k2") == [{"sku": "2"}]
    cache.clear()
    assert cache.get("k2") is None

    cb = CatalogCircuitBreaker(failure_threshold=2, recovery_timeout_sec=10.0)
    assert cb.allow_request() is True
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.allow_request() is False
    cb.reset()
    assert cb.state == "CLOSED"

    snapshot = [
        {
            "sku": "101",
            "name": "Apple MacBook Pro",
            "brand": "Apple",
            "category": "Laptops",
            "price": 1999.0,
        },
        {
            "sku": "102",
            "name": "Dell XPS 13",
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
        },
        {
            "sku": "103",
            "name": "Sony Bravia TV",
            "brand": "Sony",
            "category": "TVs",
            "price": 999.0,
        },
    ]
    matched = _match_from_snapshot(
        snapshot,
        patterns=["%macbook%", "%dell%"],
        category="Laptops",
        min_price=1000.0,
        max_price=2500.0,
        limit=5,
    )
    assert [m["sku"] for m in matched] == ["102", "101"]

    # Verify warm_full_catalog_cache with non-mock client stub
    class FakeBQClient:
        def query(self, sql, job_config=None):
            return None

        def query_and_wait(self, sql, job_config=None, wait_timeout=None):
            return [
                {
                    "sku": "101",
                    "name": "Apple MacBook Pro",
                    "brand": "Apple",
                    "category": "Laptops",
                    "price": 1999.0,
                    "rating": 4.9,
                    "review_count": 120,
                    "specifications": '{"ram": "16GB"}',
                    "url": None,
                    "image_url": "https://example.com/img.jpg",
                    "in_stock": True,
                }
            ]

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(catalog_mod, "_FULL_CATALOG_SNAPSHOT", None)
    monkeypatch.setattr(catalog_mod, "_FULL_CATALOG_SNAPSHOT_EXPIRES", 0.0)
    monkeypatch.setattr(catalog_mod, "_get_shared_bq_client", lambda: FakeBQClient())
    warmed = warm_full_catalog_cache()
    assert warmed is not None and len(warmed) == 1
    assert warm_full_catalog_cache() == warmed
    monkeypatch.setattr(catalog_mod, "_FULL_CATALOG_SNAPSHOT", None)
    monkeypatch.setattr(catalog_mod, "_FULL_CATALOG_SNAPSHOT_EXPIRES", 0.0)

    # Verify query_catalog cache hit path with use_cache=True
    local_bq = MagicMock()
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [
        {
            "sku": "101",
            "name": "Apple MacBook Pro",
            "brand": "Apple",
            "category": "Laptops",
            "price": 1999.0,
            "specifications": {},
            "url": "https://example.com/101",
            "in_stock": True,
        }
    ]
    local_bq.query.return_value = mock_query_job
    res1 = query_catalog(keywords=["MacBook ProUniqueKey"], client=local_bq, use_cache=True)
    res2 = query_catalog(keywords=["MacBook ProUniqueKey"], client=local_bq, use_cache=True)
    assert res1 == res2
    assert local_bq.query.call_count == 1
