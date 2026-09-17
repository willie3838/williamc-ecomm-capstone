"""Unit tests verifying integrity, distribution, and schema of canonical ADK benchmark dataset."""

import json
from collections import Counter
from pathlib import Path

from google.adk.evaluation.eval_set import EvalSet

BENCHMARK_EVALSET_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "evals"
    / "dataset"
    / "benchmark_catalog.evalset.json"
)


def test_eval_dataset_file_exists_and_parses():
    """Assert benchmark_catalog.evalset.json exists and conforms to ADK EvalSet."""
    assert BENCHMARK_EVALSET_PATH.exists(), f"Benchmark dataset missing at {BENCHMARK_EVALSET_PATH}"

    with open(BENCHMARK_EVALSET_PATH, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    eval_set = EvalSet.model_validate(data)
    assert eval_set.eval_set_id == "bestbuy_catalog_benchmarks_80_pairs"
    assert len(eval_set.eval_cases) == 80, (
        f"Expected exactly 80 benchmark queries, got {len(eval_set.eval_cases)}"
    )


def test_eval_dataset_categories_distribution():
    """Assert all 5 core categories have exactly 16 comparison pairs."""
    with open(BENCHMARK_EVALSET_PATH, encoding="utf-8") as f:
        data = json.load(f)

    categories = [c["category"] for c in data["eval_cases"]]
    counts = Counter(categories)

    expected_categories = {"Laptops", "Tablets", "Headphones", "Smart Home", "TVs"}
    assert set(counts.keys()) == expected_categories

    for cat in expected_categories:
        assert counts[cat] == 16, f"Category '{cat}' has {counts[cat]} queries instead of 16"


def test_eval_dataset_schema_and_uniqueness():
    """Assert each test case has unique ID, trajectory, and valid ground truth specs."""
    with open(BENCHMARK_EVALSET_PATH, encoding="utf-8") as f:
        data = json.load(f)

    seen_ids = set()
    for case in data["eval_cases"]:
        cid = case.get("eval_id") or case.get("id")
        assert cid is not None, "Missing test case ID"
        assert cid not in seen_ids, f"Duplicate test case ID: {cid}"
        seen_ids.add(cid)

        # Validate required keys
        assert "category" in case and case["category"]
        assert "expected_skus" in case and len(case["expected_skus"]) == 2
        assert "key_differential_features" in case and len(case["key_differential_features"]) >= 1
        assert "ground_truth_specs" in case and isinstance(case["ground_truth_specs"], dict)

        # Validate ADK conversation invocation
        assert "conversation" in case and len(case["conversation"]) == 1
        inv = case["conversation"][0]
        assert "user_content" in inv and inv["user_content"]["parts"][0]["text"]
        assert "intermediate_data" in inv
        assert len(inv["intermediate_data"]["tool_uses"]) >= 1
        assert inv["intermediate_data"]["tool_uses"][0]["name"] == "query_catalog"
        assert "final_response" in inv and len(inv["final_response"]["parts"][0]["text"]) > 20

        # Check ground truth matches expected SKUs
        gt = case["ground_truth_specs"]
        for sku in case["expected_skus"]:
            assert sku in gt, f"SKU {sku} missing in ground_truth_specs for case {cid}"
            sku_specs = gt[sku]
            assert "name" in sku_specs
            assert "brand" in sku_specs
            assert "price" in sku_specs and sku_specs["price"] > 0
