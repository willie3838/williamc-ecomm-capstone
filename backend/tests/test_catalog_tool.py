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
