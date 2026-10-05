"""Unit tests for tailored comparison synthesis, recommendations, and matrix ordering/filtering."""

import pytest

from app.agent.multi_agent import ComparisonAgentState, SpecComparisonAgent
from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec


@pytest.fixture
def sample_laptop_products() -> list[ProductSpec]:
    return [
        ProductSpec(
            sku="6534606",
            name='Apple MacBook Air 13.6" Laptop - M3',
            brand="Apple",
            category="Laptops",
            price=1099.0,
            rating=4.8,
            review_count=1420,
            specifications={
                "processor": "Apple M3 8-core",
                "ram_gb": 16,
                "storage_gb": 512,
                "battery_life_hours": 18.0,
                "weight_lbs": 2.7,
                "refresh_rate_hz": 60,
                "display_resolution": "2560 x 1664",
            },
            in_stock=True,
        ),
        ProductSpec(
            sku="6573822",
            name='Dell XPS 13 13.4" OLED Laptop',
            brand="Dell",
            category="Laptops",
            price=1399.0,
            rating=4.5,
            review_count=320,
            specifications={
                "processor": "Intel Core Ultra 7 155H",
                "ram_gb": 16,
                "storage_gb": 512,
                "battery_life_hours": 13.0,
                "weight_lbs": 2.6,
                "refresh_rate_hz": 120,
                "display_resolution": "2880 x 1800",
            },
            in_stock=True,
        ),
    ]


def test_matrix_reordering_for_gaming(sample_laptop_products):
    """When query indicates gaming focus, gaming specs (refresh rate, CPU, RAM) are prioritized at top."""
    orchestrator = ComparisonOrchestrator()
    matrix = orchestrator.build_comparison_matrix(
        sample_laptop_products,
        query="Compare MacBook and Dell XPS - good for gaming?",
    )

    feature_names = [r.feature for r in matrix]
    # Refresh Rate should be near the top, before Battery Life and Weight
    assert "Refresh Rate" in feature_names
    assert "Battery Life" in feature_names

    refresh_idx = feature_names.index("Refresh Rate")
    battery_idx = feature_names.index("Battery Life")
    assert refresh_idx < battery_idx


def test_matrix_reordering_for_office_work(sample_laptop_products):
    """When query indicates office work focus, battery life and weight appear before refresh rate."""
    orchestrator = ComparisonOrchestrator()
    matrix = orchestrator.build_comparison_matrix(
        sample_laptop_products,
        query="Which one is better for office work and business travel?",
    )

    feature_names = [r.feature for r in matrix]
    assert "Battery Life" in feature_names
    assert "Refresh Rate" in feature_names

    battery_idx = feature_names.index("Battery Life")
    refresh_idx = feature_names.index("Refresh Rate")
    assert battery_idx < refresh_idx


def test_matrix_filtering_for_only_price(sample_laptop_products):
    """When query explicitly specifies 'only price' or 'just price', matrix only retains price."""
    orchestrator = ComparisonOrchestrator()
    matrix = orchestrator.build_comparison_matrix(
        sample_laptop_products,
        query="Compare MacBook and XPS, only price",
    )

    feature_names = [r.feature for r in matrix]
    assert "Price" in feature_names
    # Specifications like Refresh Rate, Battery Life, etc. should be filtered out
    assert "Refresh Rate" not in feature_names
    assert "Battery Life" not in feature_names
    assert len(matrix) <= 2  # Price and optional Customer Rating


def test_multi_agent_spec_comparison_tailors_matrix_and_synthesis(sample_laptop_products):
    """SpecComparisonAgent accurately delegates user query to matrix builder and synthesis."""
    agent = SpecComparisonAgent()
    state = ComparisonAgentState(
        raw_query="Compare MacBook and XPS, only price",
        sanitized_query="Compare MacBook and XPS, only price",
        is_comparison_eligible=True,
        ranked_products=sample_laptop_products,
    )

    processed_state = agent.process(state)
    resp = processed_state.comparison_response
    assert resp is not None
    # Matrix should be filtered to price
    features = [r.feature for r in resp.comparison_matrix]
    assert "Price" in features
    assert "Refresh Rate" not in features
    assert "Battery Life" not in features
