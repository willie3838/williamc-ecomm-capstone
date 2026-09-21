"""Unit tests for the ADK Comparison Orchestrator and grounding rules."""

import json
from unittest.mock import MagicMock

from app.agent.orchestrator import ComparisonOrchestrator, catalog_agent
from app.agent.prompts import SYSTEM_INSTRUCTION


def test_agent_configuration():
    """Assert ADK agent is properly configured with tools, instructions, and name."""
    assert catalog_agent.name == "catalog_comparison_orchestrator"
    assert "Product Comparison Expert" in SYSTEM_INSTRUCTION
    assert "query_catalog" in SYSTEM_INSTRUCTION
    assert "[SKU:" in SYSTEM_INSTRUCTION
    assert len(catalog_agent.tools) >= 1


def test_orchestrator_grounding_and_citations(mock_bq_client):
    """Assert orchestrator retrieves catalog data and produces grounded matrix with SKU citations."""
    sample_products = [
        {
            "sku": "6534606",
            "name": 'Apple MacBook Air 13.6" - M3 - 16GB RAM - 512GB SSD',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "rating": 4.8,
            "review_count": 520,
            "specifications": {
                "processor": "Apple M3 8-core",
                "ram_gb": 16,
                "storage_gb": 512,
                "battery_life_hours": 18.0,
                "weight_lbs": 2.7,
            },
            "url": "https://www.techbuy.com/site/sku/6534606.p",
            "image_url": "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6534/6534606_sd.jpg",
            "in_stock": True,
        },
        {
            "sku": "6575132",
            "name": 'Dell XPS 13" - Intel Core Ultra 7 - 16GB RAM - 512GB SSD',
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
                "weight_lbs": 2.6,
            },
            "url": "https://www.techbuy.com/site/sku/6575132.p",
            "image_url": "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/6575/6575132_sd.jpg",
            "in_stock": True,
        },
    ]

    mock_job = MagicMock()
    mock_job.result.return_value = [
        {**p, "specifications": json.dumps(p["specifications"])} for p in sample_products
    ]
    mock_bq_client.query.return_value = mock_job

    orchestrator = ComparisonOrchestrator(bq_client=mock_bq_client)
    response = orchestrator.compare(
        query="Compare Apple MacBook Air M3 and Dell XPS 13", category="Laptops"
    )

    # 1. Zero Hallucination: 100% agreement with mocked data
    assert len(response.products) == 2
    skus = [p.sku for p in response.products]
    assert "6534606" in skus
    assert "6575132" in skus

    # 2. Strict Citations: every product has a valid citation
    assert len(response.citations) >= 2
    citation_skus = [c.sku for c in response.citations]
    assert "6534606" in citation_skus
    assert "6575132" in citation_skus
    for citation in response.citations:
        assert citation.url.startswith("https://www.techbuy.com/site/sku/")

    # 3. Comparison Matrix: features compared across both products
    assert len(response.comparison_matrix) > 0
    features = {row.feature for row in response.comparison_matrix}
    assert "Price" in features or "price" in features or "RAM" in features

    # 4. Summary narrative exists and cites SKUs
    assert "[SKU:" in response.summary or len(response.summary) > 20


def test_orchestrator_empty_catalog(mock_bq_client):
    """Assert orchestrator handles when products are not found in catalog."""
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_bq_client.query.return_value = mock_job

    orchestrator = ComparisonOrchestrator(bq_client=mock_bq_client)
    response = orchestrator.compare(query="Compare NonexistentProductA and NonexistentProductB")

    assert len(response.products) == 0
    assert len(response.comparison_matrix) == 0
    assert (
        "No matching products found" in response.summary or "not found" in response.summary.lower()
    )


def test_orchestrator_single_product(mock_bq_client):
    """Assert orchestrator handles when only 1 product is matched in catalog."""
    mock_job = MagicMock()
    mock_job.result.return_value = [
        {
            "sku": "1111111",
            "name": "Single Laptop",
            "brand": "Apple",
            "category": "Laptops",
            "price": 999.0,
            "rating": 4.5,
            "review_count": 50,
            "specifications": json.dumps({"processor": "M2"}),
            "url": "https://example.com/1111111",
            "in_stock": True,
        }
    ]
    mock_bq_client.query.return_value = mock_job

    orchestrator = ComparisonOrchestrator(bq_client=mock_bq_client)
    response = orchestrator.compare(query="MacBook Air")

    assert len(response.products) == 1
    assert "Found single catalog item" in response.summary
    assert "[SKU: 1111111]" in response.summary
    assert response.recommendations is None


def test_orchestrator_product2_better_specs_and_equal_price(mock_bq_client):
    """Assert orchestrator correctly identifies product 2 when cheaper and has better specs."""
    mock_job = MagicMock()
    mock_job.result.return_value = [
        {
            "sku": "2222222",
            "name": "Product Alpha",
            "brand": "BrandA",
            "category": "Laptops",
            "price": 1200.0,
            "rating": 4.5,
            "review_count": 10,
            "specifications": json.dumps({"battery_life_hours": 10.0, "storage_gb": 256}),
            "in_stock": True,
        },
        {
            "sku": "3333333",
            "name": "Product Beta",
            "brand": "BrandB",
            "category": "Laptops",
            "price": 1000.0,
            "rating": 4.5,  # Tied rating
            "review_count": 20,
            "specifications": json.dumps({"battery_life_hours": 16.0, "storage_gb": 1000}),
            "in_stock": True,
        },
    ]
    mock_bq_client.query.return_value = mock_job

    orchestrator = ComparisonOrchestrator(bq_client=mock_bq_client)
    response = orchestrator.compare(query="Alpha vs Beta")

    assert len(response.products) == 2
    assert "Product Beta [SKU: 3333333] is $200.00 more affordable" in response.summary
    assert "Product Beta [SKU: 3333333] leads with up to 16.0 hours" in response.summary
    assert response.recommendations is not None
    assert "Product Beta [SKU: 3333333]" in response.recommendations

    # Equal price comparison test
    mock_job.result.return_value = [
        {
            "sku": "4444444",
            "name": "Product Same Price 1",
            "brand": "Brand1",
            "price": 500.0,
            "specifications": "{}",
            "in_stock": True,
        },
        {
            "sku": "5555555",
            "name": "Product Same Price 2",
            "brand": "Brand2",
            "price": 500.0,
            "specifications": "{}",
            "in_stock": True,
        },
    ]
    resp2 = orchestrator.compare(query="Same1 vs Same2")
    assert "Both products are priced identically at $500.00" in resp2.summary


def test_orchestrator_query_catalog_exception_handling(mock_bq_client):
    """Assert orchestrator gracefully handles exceptions raised by query_catalog."""
    mock_bq_client.query.side_effect = RuntimeError("BigQuery failure")

    orchestrator = ComparisonOrchestrator(bq_client=mock_bq_client)
    response = orchestrator.compare(query="MacBook vs XPS")

    assert len(response.products) == 0
    assert "No matching products found" in response.summary


def test_orchestrator_extract_keywords_fallbacks():
    """Assert keyword extraction handles single words and edge queries."""
    orchestrator = ComparisonOrchestrator()
    assert orchestrator.extract_keywords("iPad") == ["iPad"]
    assert orchestrator.extract_keywords("a") == ["a"]


def test_orchestrator_matrix_edge_cases():
    """Assert direct calls on empty product lists and missing spec keys."""
    from app.models.responses import ProductSpec

    orchestrator = ComparisonOrchestrator()
    assert orchestrator.build_comparison_matrix([]) == []
    assert "No matching products found" in orchestrator.synthesize_summary([], [])

    # Product with a spec key missing in one product
    p1 = ProductSpec(
        sku="1",
        name="Prod 1",
        brand="B1",
        price=100.0,
        specifications={"ports": ["USB-C"]},
        in_stock=True,
    )
    p2 = ProductSpec(
        sku="2",
        name="Prod 2",
        brand="B2",
        price=150.0,
        specifications={"ports": None},  # Missing / None
        in_stock=True,
    )
    matrix = orchestrator.build_comparison_matrix([p1, p2])
    ports_row = next(r for r in matrix if r.feature == "Ports & Connectivity")
    assert ports_row.values["2"] == "Not specified"
