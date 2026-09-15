"""Unit tests verifying integrity, distribution, and schema of benchmark dataset."""

import json
from pathlib import Path


def test_eval_dataset_file_exists_and_parses():
    """Assert benchmark_queries.json exists and is valid JSON."""
    dataset_path = (
        Path(__file__).resolve().parent.parent.parent
        / "evals"
        / "dataset"
        / "benchmark_queries.json"
    )
    assert dataset_path.exists(), f"Benchmark dataset missing at {dataset_path}"

    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert len(data) == 80, f"Expected exactly 80 benchmark queries, got {len(data)}"


def test_eval_dataset_categories_distribution():
    """Assert all 5 core categories have exactly 16 comparison pairs."""
    dataset_path = (
        Path(__file__).resolve().parent.parent.parent
        / "evals"
        / "dataset"
        / "benchmark_queries.json"
    )
    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    categories = [c["category"] for c in data]
    from collections import Counter

    counts = Counter(categories)

    expected_categories = {"Laptops", "Tablets", "Headphones", "Smart Home", "TVs"}
    assert set(counts.keys()) == expected_categories

    for cat in expected_categories:
        assert counts[cat] == 16, f"Category '{cat}' has {counts[cat]} queries instead of 16"


def test_eval_dataset_schema_and_uniqueness():
    """Assert each test case has unique ID and satisfies strict benchmark schema."""
    dataset_path = (
        Path(__file__).resolve().parent.parent.parent
        / "evals"
        / "dataset"
        / "benchmark_queries.json"
    )
    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    seen_ids = set()
    for case in data:
        cid = case.get("id")
        assert cid is not None, "Missing test case ID"
        assert cid not in seen_ids, f"Duplicate test case ID: {cid}"
        seen_ids.add(cid)

        # Validate required keys
        assert "category" in case and case["category"]
        assert "query" in case and len(case["query"]) >= 10
        assert "expected_skus" in case and len(case["expected_skus"]) == 2
        assert "key_differential_features" in case and len(case["key_differential_features"]) >= 1
        assert "ground_truth_specs" in case and isinstance(case["ground_truth_specs"], dict)

        # Check ground truth matches expected SKUs
        gt = case["ground_truth_specs"]
        for sku in case["expected_skus"]:
            assert sku in gt, f"SKU {sku} missing in ground_truth_specs for case {cid}"
            sku_specs = gt[sku]
            assert "name" in sku_specs
            assert "brand" in sku_specs
            assert "price" in sku_specs and sku_specs["price"] > 0
