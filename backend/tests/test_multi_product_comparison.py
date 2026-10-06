"""Unit and integration tests for multi-product (2 to 5 products) comparisons."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from evals.runner import evaluate_semantic_coherence

from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import CompareResponse, ProductSpec

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = REPO_ROOT / "backend" / "src" / "app" / "data" / "catalog_seed.json"


@pytest.fixture
def sample_catalog_products() -> list[ProductSpec]:
    """Return 5 distinct Laptop products from the catalog seed."""
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    laptop_items = [p for p in catalog if p.get("category") == "Laptops"]
    return [ProductSpec(**p) for p in laptop_items[:5]]


def test_extract_keywords_multi_product():
    """Verify syntactic keyword extraction handles 3, 4, and 5 comma-separated product entities."""
    # 3 products
    q3 = "Compare MacBook Air 13 M3, Dell XPS 13, and Lenovo ThinkPad X1 Carbon Gen 12"
    kw3 = ComparisonOrchestrator.extract_keywords(q3)
    assert len(kw3) >= 3
    assert any("MacBook" in k for k in kw3)
    assert any("Dell" in k for k in kw3)
    assert any("ThinkPad" in k or "Lenovo" in k for k in kw3)

    # 4 products
    q4 = "Compare MacBook Air 13 M3, Dell XPS 13, Lenovo ThinkPad X1, and ASUS ROG Zephyrus G14"
    kw4 = ComparisonOrchestrator.extract_keywords(q4)
    assert len(kw4) >= 4

    # 5 products
    q5 = "Compare MacBook Air 13 M3, Dell XPS 13, Lenovo ThinkPad X1, ASUS ROG Zephyrus, and HP Spectre x360"
    kw5 = ComparisonOrchestrator.extract_keywords(q5)
    assert len(kw5) >= 5


def test_rank_and_select_products_multi_product(sample_catalog_products):
    """Verify rank_and_select_products selects exactly 3, 4, and 5 products when requested."""
    prods = sample_catalog_products
    assert len(prods) == 5
    orch = ComparisonOrchestrator()

    # 3 products query
    kw3 = ["MacBook Air", "Dell XPS", "ThinkPad"]
    res3 = orch.rank_and_select_products(
        prods, keywords=kw3, original_query="MacBook Air vs Dell XPS vs ThinkPad"
    )
    assert len(res3) == 3
    skus3 = {p.sku for p in res3}
    assert len(skus3) == 3

    # 4 products query
    kw4 = ["MacBook Air", "Dell XPS", "ThinkPad", "Zephyrus"]
    res4 = orch.rank_and_select_products(
        prods, keywords=kw4, original_query="MacBook Air vs Dell XPS vs ThinkPad vs Zephyrus"
    )
    assert len(res4) == 4
    skus4 = {p.sku for p in res4}
    assert len(skus4) == 4

    # 5 products query
    kw5 = ["MacBook Air", "Dell XPS", "ThinkPad", "Zephyrus", "Spectre"]
    res5 = orch.rank_and_select_products(
        prods,
        keywords=kw5,
        original_query="MacBook Air vs Dell XPS vs ThinkPad vs Zephyrus vs Spectre",
    )
    assert len(res5) == 5
    skus5 = {p.sku for p in res5}
    assert len(skus5) == 5


def test_build_comparison_matrix_multi_product(sample_catalog_products):
    """Verify comparison matrix aligns specs and determines winners across 3, 4, and 5 products."""
    orch = ComparisonOrchestrator()

    # 3 products
    matrix3 = orch.build_comparison_matrix(sample_catalog_products[:3])
    assert len(matrix3) >= 5
    for row in matrix3:
        assert len(row.values) == 3
        # Price row must have correct lowest price winner
        if row.feature == "Price":
            min_sku = min(sample_catalog_products[:3], key=lambda p: p.price).sku
            assert row.winner_sku == min_sku

    # 5 products
    matrix5 = orch.build_comparison_matrix(sample_catalog_products[:5])
    assert len(matrix5) >= 5
    for row in matrix5:
        assert len(row.values) == 5
        if row.feature == "Price":
            min_sku = min(sample_catalog_products[:5], key=lambda p: p.price).sku
            assert row.winner_sku == min_sku


def test_evaluate_semantic_coherence_multi_product(sample_catalog_products):
    """Verify evaluate_semantic_coherence evaluates contradiction and entity presence across multi-product sets."""
    p3 = sample_catalog_products[:3]

    # Valid multi-product summary referencing all 3
    valid_summary = (
        f"Comparing {p3[0].name} [SKU: {p3[0].sku}], {p3[1].name} [SKU: {p3[1].sku}], and {p3[2].name} [SKU: {p3[2].sku}]. "
        f"{min(p3, key=lambda x: x.price).name} is the most affordable at ${min(p3, key=lambda x: x.price).price:,.2f}."
    )
    resp_valid = CompareResponse(
        summary=valid_summary,
        products=p3,
        comparison_matrix=[],
        citations=[],
        recommendations="Choose based on needs.",
    )
    score_valid, errs_valid = evaluate_semantic_coherence(resp_valid, live=False)
    assert score_valid >= 0.95
    assert not errs_valid

    # Summary missing one product reference
    incomplete_summary = (
        f"Comparing {p3[0].name} [SKU: {p3[0].sku}] and {p3[1].name} [SKU: {p3[1].sku}]. "
        f"{p3[0].name} is cheaper."
    )
    resp_inc = CompareResponse(
        summary=incomplete_summary,
        products=p3,
        comparison_matrix=[],
        citations=[],
        recommendations="Choose based on needs.",
    )
    score_inc, errs_inc = evaluate_semantic_coherence(resp_inc, live=False)
    assert score_inc < 1.0
    assert any("Summary does not reference product" in err for err in errs_inc)


def test_end_to_end_orchestrator_multi_product(sample_catalog_products):
    """Verify end-to-end CompareResponse generation with 3 and 4 products using mocked BigQuery."""
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    laptop_rows = [p for p in catalog if p.get("category") == "Laptops"][:5]
    headphone_rows = [p for p in catalog if p.get("category") == "Headphones"][:5]

    mock_bq = MagicMock()

    def _query_side_effect(sql, job_config=None, wait_timeout=None):
        params = getattr(job_config, "query_parameters", []) if job_config else []
        cat_val = next(
            (getattr(p, "value", None) for p in params if getattr(p, "name", "") == "category"),
            "Laptops",
        )
        return headphone_rows if cat_val == "Headphones" else laptop_rows

    mock_bq.query_and_wait.side_effect = _query_side_effect
    orch = ComparisonOrchestrator(bq_client=mock_bq)

    # 3-product query
    q3 = "Compare MacBook Air 13 M3, Dell XPS 13, and Lenovo ThinkPad X1 Carbon Gen 12"
    resp3 = orch.compare(query=q3, category="Laptops")
    assert len(resp3.products) == 3
    assert len(resp3.citations) == 3
    assert len(resp3.comparison_matrix) >= 5
    for p in resp3.products:
        assert f"[SKU: {p.sku}]" in resp3.summary

    # 4-product query
    q4 = "Compare Sony WH-1000XM5, Bose QuietComfort Ultra, Apple AirPods Max, and Sennheiser Momentum 4"
    resp4 = orch.compare(query=q4, category="Headphones")
    assert len(resp4.products) == 4
    assert len(resp4.citations) == 4
    for p in resp4.products:
        assert f"[SKU: {p.sku}]" in resp4.summary
