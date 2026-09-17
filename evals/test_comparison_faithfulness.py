"""Semantic Comparison Quality Evaluation Test Suite.

Directly satisfies Section 3 of SPEC.md:
"3. Semantic Comparison Quality Evaluation
Test: test_comparison_faithfulness
Logic: Nightly runs check 80 comparison pairs. Uses Gemini 3.5 Flash to verify that
the comparison summary accurately reflects the differences listed in the data tables."
"""

import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure backend/src and repo root are importable
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import CompareResponse

from evals.judge import FaithfulnessResult, evaluate_comparison_faithfulness

logger = logging.getLogger("evals.test_comparison_faithfulness")

BENCHMARK_DATASET_PATH = (
    REPO_ROOT / "evals" / "dataset" / "benchmark_catalog.evalset.json"
)
CATALOG_SEED_PATH = (
    REPO_ROOT / "evals" / "dataset" / "fixtures" / "simple_test.evalset.json"
)


def load_80_comparison_pairs() -> list[dict]:
    """Load the 80 benchmark comparison pairs from the canonical evalset."""
    if not BENCHMARK_DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Benchmark dataset not found: {BENCHMARK_DATASET_PATH}"
        )

    with open(BENCHMARK_DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("eval_cases", [])
    if len(cases) != 80:
        raise ValueError(f"Expected exactly 80 comparison pairs, found {len(cases)}")

    extracted = []
    for case in cases:
        eval_id = case.get("eval_id")
        conv = case.get("conversation", [])
        if not conv:
            continue
        user_content = conv[0].get("user_content", {})
        parts = user_content.get("parts", [])
        query = parts[0].get("text", "") if parts else ""
        category = case.get("category")
        expected_skus = case.get("expected_skus", [])
        extracted.append(
            {
                "eval_id": eval_id,
                "query": query,
                "category": category,
                "expected_skus": expected_skus,
                "ground_truth_specs": case.get("ground_truth_specs", {}),
            }
        )
    return extracted


def build_catalog_from_evalset(benchmark_data: list[dict]) -> MagicMock:
    """Build a mock BigQuery client that returns matching catalog items for the 80 pairs."""
    catalog_items = []
    seen_skus = set()

    for item in benchmark_data:
        specs_map = item.get("ground_truth_specs", {})
        for sku, spec_data in specs_map.items():
            if sku in seen_skus:
                continue
            seen_skus.add(sku)
            catalog_items.append(
                {
                    "sku": sku,
                    "name": spec_data.get("name", f"Product {sku}"),
                    "brand": spec_data.get("brand", "Brand"),
                    "category": item.get("category", "Laptops"),
                    "price": spec_data.get("price", 999.0),
                    "rating": 4.5,
                    "review_count": 500,
                    "specifications": json.dumps(spec_data),
                    "url": f"https://www.bestbuy.com/site/sku/{sku}.p",
                    "image_url": f"https://pisces.bbystatic.com/image2/BestBuy_US/images/products/{sku[:4]}/{sku}_sd.jpg",
                    "in_stock": True,
                }
            )

    client = MagicMock()

    def mock_query(sql: str, job_config=None):
        patterns = []
        category = None
        if job_config and hasattr(job_config, "query_parameters"):
            for p in job_config.query_parameters:
                if p.name == "product_patterns":
                    patterns = [pat.replace("%", "").lower() for pat in p.values]
                elif p.name == "category":
                    category = p.value.lower() if p.value else None

        matches = []
        for prod in catalog_items:
            if category and prod.get("category", "").lower() != category:
                continue
            prod_text = f"{prod.get('name', '')} {prod.get('brand', '')}".lower()
            if patterns:
                for pat in patterns:
                    tokens = [t for t in pat.split() if len(t) > 2]
                    if all(t in prod_text for t in tokens):
                        matches.append(prod)
                        break
            else:
                matches.append(prod)

        mock_job = MagicMock()
        mock_job.result.return_value = matches[:10]
        return mock_job

    client.query = mock_query
    return client


def test_comparison_faithfulness():
    """SPEC.md Section 3: Semantic Comparison Quality Evaluation.

    Nightly runs check 80 comparison pairs. Uses Gemini 3.5 Flash to verify that
    the comparison summary accurately reflects the differences listed in the data tables.
    """
    pairs = load_80_comparison_pairs()
    assert len(pairs) == 80, f"Expected 80 comparison pairs, found {len(pairs)}"

    # Determine execution mode: live nightly evaluation vs hermetic fast test
    is_nightly = os.getenv("NIGHTLY_EVAL", "").lower() in (
        "1",
        "true",
        "yes",
    ) or os.getenv("LIVE_EVAL", "").lower() in ("1", "true", "yes")

    bq_client = build_catalog_from_evalset(pairs)
    orchestrator = ComparisonOrchestrator(bq_client=bq_client)

    results: list[dict] = []
    faithfulness_scores: list[int] = []
    contradiction_count = 0
    passed_count = 0

    # For fast developer test suite: evaluate first 5 with Gemini if available, or all 80 in nightly
    eval_subset = pairs if is_nightly else pairs[:5]
    judge_model = os.getenv("JUDGE_MODEL", "gemini-3.5-flash")

    for idx, item in enumerate(eval_subset, start=1):
        query = item["query"]
        category = item["category"]

        # Run comparison orchestrator
        response: CompareResponse = orchestrator.compare(query=query, category=category)

        # Verify response structure
        assert response.summary is not None, f"Empty summary for query: {query}"
        assert len(response.comparison_matrix) > 0, f"Empty matrix for query: {query}"

        # Evaluate comparison faithfulness against data table differences
        verdict: FaithfulnessResult = evaluate_comparison_faithfulness(
            query=query,
            matrix=response.comparison_matrix,
            summary=response.summary,
            model=judge_model,
        )

        faithfulness_scores.append(verdict.score)
        if verdict.has_contradiction:
            contradiction_count += 1
        if verdict.is_faithful:
            passed_count += 1

        results.append(
            {
                "eval_id": item["eval_id"],
                "query": query,
                "is_faithful": verdict.is_faithful,
                "score": verdict.score,
                "has_contradiction": verdict.has_contradiction,
                "reasoning": verdict.reasoning,
            }
        )

    # 1. Zero Contradictions: The comparison summary must NEVER contradict the data table
    assert contradiction_count == 0, (
        f"Detected {contradiction_count} contradictions in comparison summaries!"
    )

    # 2. Faithfulness Pass Rate >= 95%
    pass_rate = passed_count / len(eval_subset)
    assert pass_rate >= 0.95, (
        f"Faithfulness pass rate {pass_rate:.2%} is below 95% target"
    )

    # 3. Mean Faithfulness Score >= 4.0 / 5.0
    mean_score = sum(faithfulness_scores) / len(faithfulness_scores)
    assert mean_score >= 4.0, (
        f"Mean faithfulness score {mean_score:.2f} is below 4.0 / 5.0 threshold"
    )


def test_comparison_faithfulness_detects_inversion():
    """Verify that the Gemini Flash judge correctly catches inverted price/winner claims."""
    from app.models.responses import MatrixRow

    matrix = [
        MatrixRow(
            feature="Price",
            values={"SKU-A": "$500.00", "SKU-B": "$1,000.00"},
            winner_sku="SKU-A",
        ),
        MatrixRow(
            feature="Battery Life",
            values={"SKU-A": "15.0 hours", "SKU-B": "8.0 hours"},
            winner_sku="SKU-A",
        ),
    ]

    # Deliberately inverted contradictory summary
    inverted_summary = (
        "Comparing the devices, [SKU: SKU-B] is significantly cheaper and more affordable "
        "than [SKU: SKU-A], saving you $500. It also lasts much longer on battery."
    )

    verdict = evaluate_comparison_faithfulness(
        query="Compare SKU-A and SKU-B",
        matrix=matrix,
        summary=inverted_summary,
    )

    assert verdict.has_contradiction is True or verdict.is_faithful is False
    assert verdict.score <= 2
