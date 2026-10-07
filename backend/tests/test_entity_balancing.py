"""Unit tests verifying comparative entity balancing, SKU deduplication, and session counter increments."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.agent.multi_agent import ComparisonAgentState, MultiAgentCoordinator
from app.agent.orchestrator import ComparisonOrchestrator
from app.data.analytics import AnalyticsService
from app.models.responses import ProductSpec
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


def test_select_best_entity_candidates_same_brand_selection():
    """Verify _select_best_entity_candidates supports same-brand comparisons without forcing distinct brands."""
    candidates = [
        ProductSpec(
            sku="6534606",
            name='Apple - MacBook Air 13.6" Laptop - M3',
            brand="Apple",
            category="Laptops",
            price=1099.0,
        ),
        ProductSpec(
            sku="6534607",
            name='Apple - MacBook Pro 14" Laptop - M3 Pro',
            brand="Apple",
            category="Laptops",
            price=1999.0,
        ),
        ProductSpec(
            sku="6575132",
            name='Dell - XPS 13" Laptop - Intel Core Ultra 7',
            brand="Dell",
            category="Laptops",
            price=1299.99,
        ),
    ]

    orchestrator = ComparisonOrchestrator()
    selected = orchestrator._select_best_entity_candidates(
        candidates, keywords=["MacBook Air", "MacBook Pro"], target_count=2
    )

    assert len(selected) == 2
    assert selected[0].sku == "6534606", f"Expected MacBook Air, got {selected[0]}"
    assert selected[1].sku == "6534607", f"Expected MacBook Pro, got {selected[1]}"
    assert all(p.brand == "Apple" for p in selected), "Expected both products to be Apple"


def test_select_best_entity_candidates_multi_brand_selection_up_to_five():
    """Verify _select_best_entity_candidates selects distinct candidates matching multi-brand entities."""
    candidates = [
        ProductSpec(
            sku="101",
            name='LG - 65" Class C3 Series OLED 4K UHD Smart webOS TV',
            brand="LG",
            category="TVs",
            price=1499.99,
        ),
        ProductSpec(
            sku="102",
            name='Samsung - 65" Class S90C OLED 4K Smart Tizen TV',
            brand="Samsung",
            category="TVs",
            price=1599.99,
        ),
        ProductSpec(
            sku="103",
            name='Sony - 65" Class BRAVIA XR A80L OLED 4K HDR Google TV',
            brand="Sony",
            category="TVs",
            price=1699.99,
        ),
        ProductSpec(
            sku="104",
            name='TCL - 65" Class QM8 Series Mini-LED 4K QLED Smart Google TV',
            brand="TCL",
            category="TVs",
            price=999.99,
        ),
        ProductSpec(
            sku="105",
            name='Hisense - 65" Class U8 Series Mini-LED 4K QLED Google TV',
            brand="Hisense",
            category="TVs",
            price=899.99,
        ),
        ProductSpec(
            sku="106",
            name='LG - 65" Class B3 Series OLED 4K Smart TV',
            brand="LG",
            category="TVs",
            price=1299.99,
        ),
    ]

    orchestrator = ComparisonOrchestrator()
    keywords = ["Samsung S90C", "LG C3", "Sony BRAVIA", "TCL QM8", "Hisense U8"]
    selected = orchestrator._select_best_entity_candidates(
        candidates, keywords=keywords, target_count=5
    )

    assert len(selected) == 5
    selected_skus = [p.sku for p in selected]
    assert selected_skus == ["102", "101", "103", "104", "105"]


def test_select_best_entity_candidates_empty_or_zero_target_count():
    """Verify _select_best_entity_candidates handles boundary edge cases gracefully."""
    candidates = [
        ProductSpec(sku="1", name="Product 1", brand="BrandA", category="Laptops", price=100.0),
        ProductSpec(sku="2", name="Product 2", brand="BrandB", category="Laptops", price=200.0),
    ]
    orchestrator = ComparisonOrchestrator()

    # Empty candidates
    assert orchestrator._select_best_entity_candidates([], ["BrandA"], target_count=2) == []
    # Target count <= 0
    assert orchestrator._select_best_entity_candidates(candidates, ["BrandA"], target_count=0) == []
    # Empty keywords returns slice of candidates
    assert [
        p.sku for p in orchestrator._select_best_entity_candidates(candidates, [], target_count=2)
    ] == ["1", "2"]


def test_select_best_entity_candidates_partial_keyword_matches_fills_remaining():
    """Verify _select_best_entity_candidates fills unassigned slots with unused candidates without duplication."""
    candidates = [
        ProductSpec(
            sku="6534606",
            name='Apple - MacBook Air 13.6" Laptop - M3',
            brand="Apple",
            category="Laptops",
            price=1099.0,
        ),
        ProductSpec(
            sku="6534607",
            name='Apple - MacBook Pro 14" Laptop - M3 Pro',
            brand="Apple",
            category="Laptops",
            price=1999.0,
        ),
        ProductSpec(
            sku="6575132",
            name='Dell - XPS 13" Laptop - Intel Core Ultra 7',
            brand="Dell",
            category="Laptops",
            price=1299.99,
        ),
    ]

    orchestrator = ComparisonOrchestrator()
    # "NonExistentModel" will not match any candidate
    selected = orchestrator._select_best_entity_candidates(
        candidates, keywords=["MacBook Air", "NonExistentModel"], target_count=2
    )

    assert len(selected) == 2
    assert selected[0].sku == "6534606"
    assert selected[1].sku == "6534607"  # Backfilled from next unused candidate
    assert len({p.sku for p in selected}) == 2


@pytest.mark.asyncio
@patch("app.agent.multi_agent.query_catalog")
async def test_spec_comparison_node_preserves_tagged_sku_click_order_same_brand(mock_query_catalog):
    """Verify _spec_comparison_node preserves exact tagged [SKU: ...] click order for same-brand comparisons."""
    mock_query_catalog.return_value = [
        {
            "sku": "6534606",
            "name": 'Apple - MacBook Air 13.6" Laptop - M3',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "specifications": {"ram_gb": 16},
        },
        {
            "sku": "6534607",
            "name": 'Apple - MacBook Pro 14" Laptop - M3 Pro',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1999.0,
            "specifications": {"ram_gb": 18},
        },
        {
            "sku": "6575132",
            "name": 'Dell - XPS 13" Laptop - Intel Core Ultra 7',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1299.99,
            "specifications": {"ram_gb": 16},
        },
    ]

    coordinator = MultiAgentCoordinator()
    # Click order: MacBook Pro first, then MacBook Air
    initial_state = ComparisonAgentState(
        raw_query=(
            "Compare Product 1: Apple MacBook Pro [SKU: 6534607] and "
            "Product 2: Apple MacBook Air [SKU: 6534606]"
        ),
    )
    final_state, _ = await coordinator.execute_workflow_async(initial_state)

    assert final_state.comparison_response is not None
    assert len(final_state.comparison_response.products) == 2
    # Exact click order asserted: Pro (6534607) then Air (6534606)
    assert final_state.comparison_response.products[0].sku == "6534607"
    assert final_state.comparison_response.products[1].sku == "6534606"
    assert all(p.brand == "Apple" for p in final_state.comparison_response.products)


@pytest.mark.asyncio
@patch("app.agent.multi_agent.query_catalog")
async def test_spec_comparison_node_untagged_falls_back_to_select_best_entity_candidates(
    mock_query_catalog,
):
    """Verify _spec_comparison_node falls back to _select_best_entity_candidates for untagged keyword queries."""
    mock_query_catalog.return_value = [
        {
            "sku": "6534606",
            "name": 'Apple - MacBook Air 13.6" Laptop - M3',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "specifications": {"ram_gb": 16},
        },
        {
            "sku": "6534607",
            "name": 'Apple - MacBook Pro 14" Laptop - M3 Pro',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1999.0,
            "specifications": {"ram_gb": 18},
        },
        {
            "sku": "6575132",
            "name": 'Dell - XPS 13" Laptop - Intel Core Ultra 7',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1299.99,
            "specifications": {"ram_gb": 16},
        },
    ]

    coordinator = MultiAgentCoordinator()
    initial_state = ComparisonAgentState(
        raw_query="MacBook Pro vs MacBook Air",
    )
    final_state, _ = await coordinator.execute_workflow_async(initial_state)

    assert final_state.comparison_response is not None
    assert len(final_state.comparison_response.products) == 2
    skus = {p.sku for p in final_state.comparison_response.products}
    assert skus == {"6534606", "6534607"}
    assert all(p.brand == "Apple" for p in final_state.comparison_response.products)
