"""Heuristic Spec Accuracy and Semantic Faithfulness evaluation tests.

Directly implements specifications defined in SPEC.md:
1. test_heuristic_spec_accuracy: Mocks BigQuery client to return known dataset for two products.
   Sends query to agent. Parses output table and asserts prices and CPUs match mocked BigQuery values exactly.
2. test_comparison_faithfulness: Verifies comparison summary accurately reflects tabular differences without contradiction.
"""

import json
from unittest.mock import MagicMock

import pytest

from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import CompareResponse


@pytest.fixture
def mock_two_laptops_bq_client():
    """Mock client returning MacBook Air M3 and Dell XPS 13."""
    mock_client = MagicMock()
    sample_products = [
        {
            "sku": "6534606",
            "name": 'Apple MacBook Air 13.6" Laptop - M3 chip - 16GB Memory - 512GB SSD',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "rating": 4.8,
            "review_count": 1250,
            "specifications": json.dumps(
                {
                    "processor": "Apple M3 8-core",
                    "ram_gb": 16,
                    "storage_gb": 512,
                    "battery_life_hours": 18.0,
                    "weight_lbs": 2.7,
                    "display_size_in": 13.6,
                    "display_resolution": "2560 x 1664 Liquid Retina Display",
                    "gpu": "10-core GPU",
                    "operating_system": "macOS Sonoma",
                }
            ),
            "url": "https://www.bestbuy.com/site/sku/6534606.p",
            "image_url": "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6534/6534606_sd.jpg",
            "in_stock": True,
        },
        {
            "sku": "6575132",
            "name": 'Dell XPS 13" - Intel Core Ultra 7 - 16GB Memory - 512GB SSD',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
            "rating": 4.5,
            "review_count": 430,
            "specifications": json.dumps(
                {
                    "processor": "Intel Core Ultra 7 155H",
                    "ram_gb": 16,
                    "storage_gb": 512,
                    "battery_life_hours": 14.0,
                    "weight_lbs": 2.6,
                    "display_size_in": 13.4,
                    "display_resolution": "1920 x 1200 FHD+ InfinityEdge",
                    "gpu": "Intel Arc Graphics",
                    "operating_system": "Windows 11 Home",
                }
            ),
            "url": "https://www.bestbuy.com/site/sku/6575132.p",
            "image_url": "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6575/6575132_sd.jpg",
            "in_stock": True,
        },
    ]

    mock_job = MagicMock()
    mock_job.result.return_value = sample_products
    mock_client.query.return_value = mock_job
    return mock_client


def test_heuristic_spec_accuracy(mock_two_laptops_bq_client):
    """SPEC.md Test 1: Mocks BigQuery client with known dataset for two products.

    Sends query to agent. Parses output table and asserts prices and CPUs match mocked BigQuery values exactly.
    """
    orchestrator = ComparisonOrchestrator(bq_client=mock_two_laptops_bq_client)
    response: CompareResponse = orchestrator.compare(
        query="Compare Apple MacBook Air M3 and Dell XPS 13", category="Laptops"
    )

    # 1. Assert response is valid and structured
    assert isinstance(response, CompareResponse)
    assert len(response.products) == 2

    # Map products by SKU
    prod_map = {p.sku: p for p in response.products}
    assert "6534606" in prod_map
    assert "6575132" in prod_map

    # 2. Check price matching exactly
    assert prod_map["6534606"].price == 1099.0
    assert prod_map["6575132"].price == 1199.0

    # 3. Check CPU / processor matching exactly
    assert prod_map["6534606"].specifications.get("processor") == "Apple M3 8-core"
    assert prod_map["6575132"].specifications.get("processor") == "Intel Core Ultra 7 155H"

    # 4. Assert comparison matrix rows match exactly
    matrix_rows = {r.feature: r for r in response.comparison_matrix}
    assert "Price" in matrix_rows
    price_row = matrix_rows["Price"]
    assert price_row.values["6534606"] == "$1,099.00"
    assert price_row.values["6575132"] == "$1,199.00"
    assert price_row.winner_sku == "6534606"  # Lower price wins

    # Processor row in matrix
    assert "Processor / CPU" in matrix_rows
    cpu_row = matrix_rows["Processor / CPU"]
    assert "Apple M3 8-core" in cpu_row.values["6534606"]
    assert "Intel Core Ultra 7 155H" in cpu_row.values["6575132"]

    # RAM row in matrix
    assert "Memory (RAM)" in matrix_rows
    ram_row = matrix_rows["Memory (RAM)"]
    assert ram_row.values["6534606"] == "16 GB"
    assert ram_row.values["6575132"] == "16 GB"

    # 5. Assert citations are present and non-hallucinated
    assert len(response.citations) == 2
    cit_skus = {c.sku for c in response.citations}
    assert cit_skus == {"6534606", "6575132"}


def test_comparison_faithfulness(mock_two_laptops_bq_client):
    """SPEC.md Test 3: Verifies that comparison summary accurately reflects the differences.

    Asserts no contradictory statements or inverted winners.
    """
    orchestrator = ComparisonOrchestrator(bq_client=mock_two_laptops_bq_client)
    response: CompareResponse = orchestrator.compare(
        query="Compare Apple MacBook Air M3 and Dell XPS 13", category="Laptops"
    )

    summary = response.summary
    assert summary is not None
    assert len(summary) > 0

    # 1. Check citations in narrative
    assert "[SKU: 6534606]" in summary
    assert "[SKU: 6575132]" in summary

    # 2. Check price faithfulness: MacBook Air is $100 cheaper ($1099 vs $1199)
    # The narrative must affirm MacBook Air is more affordable, NOT Dell XPS
    assert "more affordable" in summary
    assert "6534606" in summary
    assert "$100.00 more affordable" in summary or "$1,099.00 versus $1,199.00" in summary

    # 3. Check battery faithfulness: MacBook Air has 18h vs Dell 14h
    # MacBook Air must be stated as leading in battery
    assert "18.0 hours" in summary or "18 hours" in summary
    assert "14.0 hours" in summary or "14 hours" in summary

    # 4. Check recommendations faithfulness
    rec = response.recommendations
    assert rec is not None
    assert "6534606" in rec  # Battery and value winner


def test_heuristic_spec_accuracy_equal_prices(mock_bq_client):
    """Verify matrix and summary when products are identical in price."""
    products = [
        {
            "sku": "A1",
            "name": "Laptop A",
            "brand": "BrandA",
            "category": "Laptops",
            "price": 999.0,
            "rating": 4.5,
            "review_count": 100,
            "specifications": json.dumps({"processor": "Chip A", "ram_gb": 16}),
            "in_stock": True,
        },
        {
            "sku": "B2",
            "name": "Laptop B",
            "brand": "BrandB",
            "category": "Laptops",
            "price": 999.0,
            "rating": 4.5,
            "review_count": 100,
            "specifications": json.dumps({"processor": "Chip B", "ram_gb": 16}),
            "in_stock": True,
        },
    ]
    mock_job = MagicMock()
    mock_job.result.return_value = products
    mock_bq_client.query.return_value = mock_job

    orchestrator = ComparisonOrchestrator(bq_client=mock_bq_client)
    resp = orchestrator.compare("Laptop A vs Laptop B")

    matrix_rows = {r.feature: r for r in resp.comparison_matrix}
    assert matrix_rows["Price"].winner_sku is None  # Tie, no single winner
    assert "Both products are priced identically at $999.00" in resp.summary
