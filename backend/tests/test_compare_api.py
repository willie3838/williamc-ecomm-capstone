"""Integration tests for the /api/compare API endpoint."""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_compare_endpoint_valid_request(mock_bq_client):
    """Test /api/compare endpoint returns structured comparison with matrix and citations."""
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
            "url": "https://www.bestbuy.com/site/sku/6534606.p",
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
                    "processor": "Intel Core Ultra 7 155H",
                    "ram_gb": 16,
                    "storage_gb": 512,
                    "battery_life_hours": 14.0,
                }
            ),
            "url": "https://www.bestbuy.com/site/sku/6575132.p",
            "image_url": "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6575/6575132_sd.jpg",
            "in_stock": True,
        },
    ]

    mock_job = MagicMock()
    mock_job.result.return_value = sample_rows
    mock_bq_client.query.return_value = mock_job

    with patch("google.cloud.bigquery.Client", return_value=mock_bq_client):
        response = client.post(
            "/api/compare",
            json={"query": "Compare MacBook Air M3 and Dell XPS 13", "category": "Laptops"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert len(data["products"]) == 2
    assert len(data["comparison_matrix"]) > 0
    assert len(data["citations"]) == 2

    # Verify SKU citation format
    for citation in data["citations"]:
        assert "sku" in citation
        assert "url" in citation
        assert citation["url"].startswith("https://www.bestbuy.com/site/sku/")


def test_compare_endpoint_validation():
    """Test validation errors for invalid payloads."""
    # Query too short
    response = client.post("/api/compare", json={"query": "ab"})
    assert response.status_code == 422

    # Query empty/whitespace
    response = client.post("/api/compare", json={"query": "   "})
    assert response.status_code == 400
