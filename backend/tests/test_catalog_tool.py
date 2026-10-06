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
    mock_bq_client.query_and_wait.assert_not_called()


def test_query_catalog_success(mock_bq_client):
    """Verify parameterized query execution and response formatting."""
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

    mock_bq_client.query_and_wait.return_value = mock_rows

    results = query_catalog(
        keywords=["MacBook Air", "Dell XPS"],
        category="Laptops",
        min_price=900.0,
        max_price=1500.0,
        limit=2,
        client=mock_bq_client,
    )

    assert len(results) == 2
    mock_bq_client.query_and_wait.assert_called_once()
    sql_arg = mock_bq_client.query_and_wait.call_args[0][0]
    job_config = mock_bq_client.query_and_wait.call_args[1]["job_config"]

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
    mock_bq_client.query_and_wait.side_effect = RuntimeError("BigQuery connection failed")

    with pytest.raises(RuntimeError) as exc_info:
        query_catalog(keywords=["MacBook"], client=mock_bq_client)

    assert "BigQuery" in str(exc_info.value)


def test_query_catalog_whitespace_keywords(mock_bq_client):
    """Verify whitespace-only keywords return empty list."""
    results = query_catalog(keywords=["  ", ""], client=mock_bq_client)
    assert results == []
    mock_bq_client.query_and_wait.assert_not_called()


def test_query_catalog_invalid_specifications_json(mock_bq_client):
    """Verify fallback to empty dict when specifications contains invalid JSON."""
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
    mock_bq_client.query_and_wait.return_value = mock_rows

    results = query_catalog(keywords=["Generic"], client=mock_bq_client)
    assert len(results) == 2
    assert results[0]["specifications"] == {}
    assert results[1]["specifications"] == {}


def test_catalog_circuit_breaker_and_stateless_execution():
    """Verify CatalogCircuitBreaker and stateless execution without in-memory catalog caching."""
    import app.tools.catalog as catalog_mod
    from app.tools.catalog import CatalogCircuitBreaker, query_catalog

    # 1. Verify that all in-memory catalog cache symbols have been removed
    assert not hasattr(catalog_mod, "CatalogResponseCache")
    assert not hasattr(catalog_mod, "catalog_cache")
    assert not hasattr(catalog_mod, "warm_full_catalog_cache")
    assert not hasattr(catalog_mod, "_FULL_CATALOG_SNAPSHOT")
    assert not hasattr(catalog_mod, "_FULL_CATALOG_SNAPSHOT_EXPIRES")
    assert not hasattr(catalog_mod, "_FULL_CATALOG_LOCK")
    assert not hasattr(catalog_mod, "_match_from_snapshot")

    # 2. Verify CatalogCircuitBreaker state transitions
    cb = CatalogCircuitBreaker(failure_threshold=2, recovery_timeout_sec=10.0)
    assert cb.allow_request() is True
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.allow_request() is False
    cb.reset()
    assert cb.state == "CLOSED"

    # 3. Verify query_catalog always executes direct BigQuery queries (stateless, zero in-memory cache)
    local_bq = MagicMock()
    local_bq.query_and_wait.return_value = [
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
    res1 = query_catalog(keywords=["MacBook ProUniqueKey"], client=local_bq)
    res2 = query_catalog(keywords=["MacBook ProUniqueKey"], client=local_bq)
    assert res1 == res2
    # Stateless: Every query invokes client.query_and_wait, no in-memory cache hit
    assert local_bq.query_and_wait.call_count == 2


def test_shared_bq_client_keyed_by_class_identity_across_patches():
    """Verify _get_shared_bq_client re-instantiates when bigquery.Client is patched across multiple blocks without assert_called checks."""
    from pathlib import Path
    from unittest.mock import patch

    import app.tools.catalog as catalog_mod
    from app.tools.catalog import _get_shared_bq_client, query_catalog

    catalog_src = Path(catalog_mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("PYTEST_CURRENT_TEST", "assert_called", "pytest", '"Mock"'):
        assert forbidden not in catalog_src, f"Forbidden token {forbidden!r} found in catalog.py"

    with patch("app.tools.catalog.bigquery.Client") as mock_cls_1:
        mock_client_1 = MagicMock()
        mock_client_1.query_and_wait.return_value = [
            {
                "sku": "111",
                "name": "Laptop 1",
                "brand": "Apple",
                "category": "Laptops",
                "price": 999.0,
                "specifications": {},
                "url": "https://www.techbuy.com/site/sku/111.p",
                "in_stock": True,
            }
        ]
        mock_cls_1.return_value = mock_client_1

        c1_a = _get_shared_bq_client()
        c1_b = _get_shared_bq_client()
        assert c1_a is mock_client_1
        assert c1_b is mock_client_1
        assert mock_cls_1.call_count == 1

        res_1 = query_catalog(keywords=["Laptop 1"])
        assert len(res_1) == 1
        assert res_1[0]["sku"] == "111"

    with patch("app.tools.catalog.bigquery.Client") as mock_cls_2:
        mock_client_2 = MagicMock()
        mock_client_2.query_and_wait.return_value = [
            {
                "sku": "222",
                "name": "Laptop 2",
                "brand": "Dell",
                "category": "Laptops",
                "price": 1099.0,
                "specifications": {},
                "url": "https://www.techbuy.com/site/sku/222.p",
                "in_stock": True,
            }
        ]
        mock_cls_2.return_value = mock_client_2

        c2 = _get_shared_bq_client()
        assert c2 is mock_client_2
        assert c2 is not mock_client_1
        assert mock_cls_2.call_count == 1

        res_2 = query_catalog(keywords=["Laptop 2"])
        assert len(res_2) == 1
        assert res_2[0]["sku"] == "222"
