"""Unit tests verifying integrity, distribution, and schema of the Holdout & Counterfactual dataset."""

import json
from pathlib import Path

from google.adk.evaluation.eval_set import EvalSet

HOLDOUT_EVALSET_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "evals"
    / "dataset"
    / "holdout_catalog.evalset.json"
)
BENCHMARK_EVALSET_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "evals"
    / "dataset"
    / "benchmark_catalog.evalset.json"
)


def test_holdout_dataset_file_exists_and_parses():
    """Assert holdout_catalog.evalset.json exists and conforms to ADK EvalSet."""
    assert HOLDOUT_EVALSET_PATH.exists(), f"Holdout dataset missing at {HOLDOUT_EVALSET_PATH}"

    with open(HOLDOUT_EVALSET_PATH, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    eval_set = EvalSet.model_validate(data)
    assert eval_set.eval_set_id == "bestbuy_catalog_holdout_counterfactual"
    assert len(eval_set.eval_cases) >= 25, (
        f"Expected at least 25 holdout/counterfactual test cases, got {len(eval_set.eval_cases)}"
    )


def test_holdout_dataset_zero_leakage_with_benchmark():
    """Assert zero ID collisions or identical queries between benchmark and holdout datasets."""
    assert BENCHMARK_EVALSET_PATH.exists()
    assert HOLDOUT_EVALSET_PATH.exists()

    with open(BENCHMARK_EVALSET_PATH, encoding="utf-8") as f:
        bench_data = json.load(f)
    with open(HOLDOUT_EVALSET_PATH, encoding="utf-8") as f:
        holdout_data = json.load(f)

    bench_ids = {c.get("eval_id") or c.get("id") for c in bench_data.get("eval_cases", [])}
    holdout_ids = {c.get("eval_id") or c.get("id") for c in holdout_data.get("eval_cases", [])}

    assert None not in bench_ids
    assert None not in holdout_ids
    overlap_ids = bench_ids.intersection(holdout_ids)
    assert not overlap_ids, (
        f"Found overlapping test case IDs between benchmark and holdout: {overlap_ids}"
    )

    bench_queries = {
        c["conversation"][0]["user_content"]["parts"][0]["text"].strip().lower()
        for c in bench_data.get("eval_cases", [])
        if c.get("conversation")
    }
    holdout_queries = {
        c["conversation"][0]["user_content"]["parts"][0]["text"].strip().lower()
        for c in holdout_data.get("eval_cases", [])
        if c.get("conversation")
    }
    query_overlap = bench_queries.intersection(holdout_queries)
    assert not query_overlap, (
        f"Found overlapping queries between benchmark and holdout: {query_overlap}"
    )


def test_holdout_dataset_archetype_coverage():
    """Assert all 4 critical evaluation archetypes are well-represented in the holdout dataset."""
    with open(HOLDOUT_EVALSET_PATH, encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("eval_cases", [])
    archetypes = {c.get("archetype") for c in cases if c.get("archetype")}

    expected_archetypes = {
        "holdout_comparison",
        "counterfactual_spec",
        "negative_chatter",
        "cross_category",
    }
    assert expected_archetypes.issubset(archetypes), (
        f"Missing archetypes: {expected_archetypes - archetypes}"
    )

    # Verify counts per archetype
    counterfactual_cases = [c for c in cases if c.get("archetype") == "counterfactual_spec"]
    negative_cases = [c for c in cases if c.get("archetype") == "negative_chatter"]
    cross_cat_cases = [c for c in cases if c.get("archetype") == "cross_category"]
    comparison_cases = [c for c in cases if c.get("archetype") == "holdout_comparison"]

    assert len(counterfactual_cases) >= 5, "Need at least 5 counterfactual spec cases"
    assert len(negative_cases) >= 4, "Need at least 4 negative chatter/rant cases"
    assert len(cross_cat_cases) >= 2, "Need at least 2 cross-category mismatch cases"
    assert len(comparison_cases) >= 10, "Need at least 10 holdout comparison cases"


def test_holdout_dataset_schema_and_integrity():
    """Assert each test case has unique ID and correct ground truth or negative structure."""
    with open(HOLDOUT_EVALSET_PATH, encoding="utf-8") as f:
        data = json.load(f)

    seen_ids = set()
    for case in data.get("eval_cases", []):
        cid = case.get("eval_id") or case.get("id")
        assert cid not in seen_ids, f"Duplicate ID in holdout set: {cid}"
        seen_ids.add(cid)

        assert "conversation" in case and len(case["conversation"]) == 1
        inv = case["conversation"][0]
        assert "user_content" in inv and inv["user_content"]["parts"][0]["text"]
        assert "final_response" in inv and len(inv["final_response"]["parts"][0]["text"]) > 10

        archetype = case.get("archetype")
        if archetype == "negative_chatter":
            # Negative chatter should expect 0 products
            assert case.get("expected_skus") == []
            assert case.get("ground_truth_specs", {}) == {}
        elif archetype == "holdout_comparison" or archetype == "counterfactual_spec":
            assert len(case.get("expected_skus", [])) >= 2
            gt = case.get("ground_truth_specs", {})
            for sku in case["expected_skus"]:
                assert sku in gt, f"SKU {sku} missing in ground_truth_specs for case {cid}"
