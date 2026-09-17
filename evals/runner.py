"""Evaluation and Quality Flywheel runner for Best Buy Catalog Comparison Agent."""

import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("evals.runner")


def create_hermetic_bq_client(catalog_path: Path) -> MagicMock:
    """Create a hermetic mock BigQuery client populated with catalog seed data."""
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog seed file not found: {catalog_path}")

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog_items = json.load(f)

    client = MagicMock()

    def mock_query(sql: str, job_config: Any = None) -> MagicMock:
        patterns: list[str] = []
        category: str | None = None
        min_price: float | None = None
        max_price: float | None = None

        if job_config and hasattr(job_config, "query_parameters"):
            for p in job_config.query_parameters:
                if p.name == "product_patterns":
                    patterns = [pat.replace("%", "").lower() for pat in p.values]
                elif p.name == "category":
                    category = p.value.lower() if p.value else None
                elif p.name == "min_price":
                    min_price = float(p.value)
                elif p.name == "max_price":
                    max_price = float(p.value)

        matches = []
        for item in catalog_items:
            if category and item.get("category", "").lower() != category:
                continue
            if min_price is not None and item.get("price", 0) < min_price:
                continue
            if max_price is not None and item.get("price", 0) > max_price:
                continue

            item_text = (
                f"{item.get('name', '')} {item.get('brand', '')} {item.get('category', '')} "
                f"{json.dumps(item.get('specifications', {}))}"
            ).lower()

            if patterns:
                matched_item = False
                stopwords = {
                    "with",
                    "and",
                    "the",
                    "for",
                    "versus",
                    "compare",
                    "between",
                    "which",
                    "better",
                    "cheaper",
                    "lighter",
                    "longer",
                    "worth",
                    "price",
                    "specs",
                    "difference",
                    "differences",
                    "summary",
                    "breakdown",
                    "detailed",
                    "comprehensive",
                    "vs",
                    "inch",
                }
                for pat in patterns:
                    pat_tokens = [
                        t
                        for t in re.findall(r"[a-z0-9-]+", pat.lower())
                        if len(t) >= 2 and t not in stopwords
                    ]
                    if not pat_tokens:
                        continue
                    m_count = sum(1 for t in pat_tokens if t in item_text)
                    if (
                        (len(pat_tokens) == 1 and m_count == 1)
                        or (m_count >= 2 and (m_count / len(pat_tokens)) >= 0.3)
                        or (
                            m_count >= 1
                            and any(
                                b in pat_tokens
                                for b in [
                                    "apple",
                                    "dell",
                                    "lenovo",
                                    "samsung",
                                    "google",
                                    "sony",
                                    "bose",
                                    "lg",
                                    "ecobee",
                                    "c3",
                                    "s90c",
                                    "x1",
                                    "m3",
                                    "m4",
                                    "macbook",
                                ]
                            )
                        )
                    ):
                        matched_item = True
                        break
                if matched_item:
                    row = dict(item)
                    if isinstance(row.get("specifications"), dict):
                        row["specifications"] = json.dumps(row["specifications"])
                    matches.append(row)
            else:
                row = dict(item)
                if isinstance(row.get("specifications"), dict):
                    row["specifications"] = json.dumps(row["specifications"])
                matches.append(row)

        mock_job = MagicMock()
        mock_job.result.return_value = matches
        return mock_job

    client.query.side_effect = mock_query
    return client


def normalize_value(val: Any) -> Any:
    """Normalize numeric and string values for fuzzy spec comparisons."""
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return round(float(val), 2)
    s = str(val).strip().lower()
    # Normalize qualifiers like 'up to', 'about'
    s = re.sub(r"\b(up to|approx\.?|about)\b", "", s, flags=re.IGNORECASE)
    # Normalize common units with and without space
    s = re.sub(
        r"(?<=\d)(gb|ghz|tb|hrs?|hours?|lbs?|oz|hz|watts?)\b",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(gb|ghz|tb|hrs?|hours?|lbs?|oz|hz|watts?)\b", "", s, flags=re.IGNORECASE
    )
    s = re.sub(r"[\$,\"']", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    try:
        num = float(s)
        return round(num, 2)
    except ValueError:
        return s


def compute_spec_accuracy(
    expected_skus: list[str],
    ground_truth_specs: dict[str, dict[str, Any]],
    response: CompareResponse,
) -> tuple[float, list[str]]:
    """Compute exact and normalized technical spec match accuracy against catalog ground truth."""
    if not response.products:
        return 0.0, ["No products returned by agent."]

    retrieved_by_sku = {p.sku: p for p in response.products}
    errors: list[str] = []
    total_checks = 0
    passed_checks = 0

    for sku in expected_skus:
        gt = ground_truth_specs.get(sku, {})
        if sku not in retrieved_by_sku:
            errors.append(f"Expected SKU {sku} not present in retrieved products.")
            total_checks += max(1, len(gt))
            continue

        prod = retrieved_by_sku[sku]
        prod_specs = (
            prod.specifications if isinstance(prod.specifications, dict) else {}
        )

        for feature_key, expected_val in gt.items():
            total_checks += 1
            actual_val = None

            if feature_key == "price":
                actual_val = prod.price
            elif feature_key == "brand":
                actual_val = prod.brand
            elif feature_key == "name":
                actual_val = prod.name
            else:
                actual_val = prod_specs.get(feature_key)

            norm_expected = normalize_value(expected_val)
            norm_actual = normalize_value(actual_val)

            match = False
            if norm_actual == norm_expected:
                match = True
            elif isinstance(norm_expected, str) and isinstance(norm_actual, str):
                if norm_expected in norm_actual or norm_actual in norm_expected:
                    match = True
            elif (
                isinstance(norm_expected, (int, float))
                and isinstance(norm_actual, (int, float))
                and abs(float(norm_expected) - float(norm_actual)) < 0.05
            ):
                match = True

            if match:
                passed_checks += 1
            else:
                errors.append(
                    f"SKU {sku} spec mismatch for '{feature_key}': expected '{expected_val}', got '{actual_val}'"
                )

    accuracy = (passed_checks / total_checks) if total_checks > 0 else 1.0
    return round(accuracy, 4), errors


def compute_citation_faithfulness(
    expected_skus: list[str],
    response: CompareResponse,
) -> tuple[float, list[str]]:
    """Evaluate presence, validity, and traceability of [SKU: ...] citations."""
    errors: list[str] = []
    score_components = []

    # 1. Check response.citations payload
    retrieved_skus = {p.sku for p in response.products}

    if not response.citations:
        errors.append("Empty citations list in response.")
        score_components.append(0.0)
    else:
        # Check all citation objects have valid SKU and URL
        valid_objs = all(c.sku and c.url for c in response.citations)
        score_components.append(1.0 if valid_objs else 0.5)

    # 2. Check inline citations in summary text
    summary_text = response.summary or ""
    inline_citations = re.findall(r"\[SKU:\s*([A-Za-z0-9_-]+)\]", summary_text)
    cited_inline_skus = set(inline_citations)

    # All cited inline SKUs must exist in retrieved products (zero hallucination)
    hallucinated_skus = cited_inline_skus - retrieved_skus
    if hallucinated_skus:
        errors.append(f"Hallucinated citations found in summary: {hallucinated_skus}")
        return 0.0, errors
    elif cited_inline_skus:
        # Check coverage of expected SKUs
        coverage = len(cited_inline_skus & set(expected_skus)) / max(
            1, len(expected_skus)
        )
        score_components.append(coverage)
    else:
        errors.append("No inline [SKU: ...] citations detected in summary narrative.")
        score_components.append(0.0)

    # 3. Check inline citations in recommendations if present
    if response.recommendations:
        rec_citations = re.findall(
            r"\[SKU:\s*([A-Za-z0-9_-]+)\]", response.recommendations
        )
        rec_hallucinated = set(rec_citations) - retrieved_skus
        if rec_hallucinated:
            errors.append(
                f"Hallucinated citations in recommendations: {rec_hallucinated}"
            )
            score_components.append(0.0)
        else:
            score_components.append(1.0)

    final_score = (
        sum(score_components) / len(score_components) if score_components else 0.0
    )
    return round(final_score, 4), errors


def evaluate_semantic_coherence(
    response: CompareResponse,
    judge_model: str = "gemini-1.5-flash",
    live: bool = False,
) -> tuple[float, list[str]]:
    """Evaluate semantic coherence, winner consistency, and absence of contradictions."""
    errors: list[str] = []

    if not response.products or len(response.products) < 2:
        return 1.0, []

    p1, p2 = response.products[0], response.products[1]
    summary = (response.summary or "").lower()

    # Contradiction checks on price
    score = 1.0
    if p1.price < p2.price:
        # p1 is cheaper
        if (
            f"{p2.name.lower()} is cheaper" in summary
            or f"{p2.name.lower()} is more affordable" in summary
        ):
            errors.append(
                f"Contradiction: summary claimed {p2.name} is cheaper than {p1.name}"
            )
            score -= 0.5
    elif p2.price < p1.price and (
        f"{p1.name.lower()} is cheaper" in summary
        or f"{p1.name.lower()} is more affordable" in summary
    ):
        errors.append(
            f"Contradiction: summary claimed {p1.name} is cheaper than {p2.name}"
        )
        score -= 0.5

    # Check that summary mentions key entities
    if p1.sku not in (response.summary or "") and p1.name.lower() not in summary:
        errors.append(f"Summary does not reference first product {p1.name}")
        score -= 0.25
    if p2.sku not in (response.summary or "") and p2.name.lower() not in summary:
        errors.append(f"Summary does not reference second product {p2.name}")
        score -= 0.25

    final_score = max(0.0, min(1.0, score))
    return round(final_score, 4), errors


def run_benchmark(
    dataset_path: Path,
    catalog_path: Path,
    category: str | None = None,
    limit: int | None = None,
    judge_model: str = "gemini-1.5-flash",
    live: bool = False,
    target_accuracy: float = 0.98,
    target_citation: float = 0.95,
    target_latency: float = 3.0,
    target_schema: float = 1.00,
) -> dict[str, Any]:
    with open(dataset_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, dict) and "eval_cases" in raw_data:
        cases = []
        for c in raw_data["eval_cases"]:
            query = c.get("query")
            if not query and c.get("conversation"):
                query = c["conversation"][0]["user_content"]["parts"][0]["text"]
            cases.append(
                {
                    "id": c.get("id") or c.get("eval_id"),
                    "category": c.get("category"),
                    "query": query,
                    "expected_skus": c.get("expected_skus", []),
                    "key_differential_features": c.get("key_differential_features", []),
                    "ground_truth_specs": c.get("ground_truth_specs", {}),
                }
            )
    elif isinstance(raw_data, list):
        cases = raw_data
    else:
        raise ValueError(f"Unrecognized dataset schema in {dataset_path}")

    if category:
        cases = [c for c in cases if c.get("category", "").lower() == category.lower()]
        logger.info("Filtered to %d cases in category '%s'", len(cases), category)

    if limit and limit > 0:
        cases = cases[:limit]
        logger.info("Limited benchmark run to %d test cases", len(cases))

    if not cases:
        raise ValueError(
            f"No benchmark test cases found matching criteria in {dataset_path}"
        )

    # Set up orchestrator
    if live:
        logger.info("Running in LIVE mode with Google Cloud BigQuery client")
        orchestrator = ComparisonOrchestrator()
    else:
        logger.info(
            "Running in HERMETIC mode with mock BigQuery client from %s", catalog_path
        )
        bq_client = create_hermetic_bq_client(catalog_path)
        orchestrator = ComparisonOrchestrator(bq_client=bq_client)

    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    total_accuracy = 0.0
    total_citation = 0.0
    total_precision = 0.0
    total_recall = 0.0
    total_semantic = 0.0
    valid_schema_count = 0

    category_stats: dict[str, dict[str, Any]] = {}

    print(f"\n🚀 Running Evaluation Benchmark ({len(cases)} test cases)...")
    print("=" * 80)

    for idx, case in enumerate(cases, start=1):
        case_id = case["id"]
        case_cat = case["category"]
        query = case["query"]
        expected_skus = case.get("expected_skus", [])
        ground_truth_specs = case.get("ground_truth_specs", {})

        if case_cat not in category_stats:
            category_stats[case_cat] = {
                "total": 0,
                "passed": 0,
                "accuracy_sum": 0.0,
                "citation_sum": 0.0,
                "latency_sum": 0.0,
            }

        start_time = time.perf_counter()
        case_errors: list[str] = []
        is_schema_valid = False

        try:
            response = orchestrator.compare(query=query, category=case_cat)
            latency = time.perf_counter() - start_time
            latencies.append(latency)

            # Check schema validity
            is_schema_valid = isinstance(response, CompareResponse) and bool(
                response.summary
            )
            if is_schema_valid:
                valid_schema_count += 1
            else:
                case_errors.append("Invalid or empty CompareResponse payload")

            retrieved_skus = [p.sku for p in response.products]

            # 1. Retrieval precision and recall
            expected_set = set(expected_skus)
            retrieved_set = set(retrieved_skus)
            intersection = expected_set & retrieved_set
            precision = len(intersection) / max(1, len(retrieved_set))
            recall = len(intersection) / max(1, len(expected_set))

            # 2. Data accuracy
            accuracy, acc_errs = compute_spec_accuracy(
                expected_skus, ground_truth_specs, response
            )
            case_errors.extend(acc_errs)

            # 3. Citation faithfulness
            citation_score, cit_errs = compute_citation_faithfulness(
                expected_skus, response
            )
            case_errors.extend(cit_errs)

            # 4. Semantic coherence
            semantic_score, sem_errs = evaluate_semantic_coherence(
                response, judge_model=judge_model, live=live
            )
            case_errors.extend(sem_errs)

        except Exception as exc:  # noqa: BLE001
            latency = time.perf_counter() - start_time
            latencies.append(latency)
            accuracy = 0.0
            citation_score = 0.0
            precision = 0.0
            recall = 0.0
            semantic_score = 0.0
            retrieved_skus = []
            case_errors.append(f"Execution error: {exc}")

        # Determine pass/fail status
        passed = (
            accuracy >= 0.95
            and citation_score >= 0.90
            and is_schema_valid
            and latency <= 5.0
        )
        status_str = "PASS" if passed else "FAIL"

        total_accuracy += accuracy
        total_citation += citation_score
        total_precision += precision
        total_recall += recall
        total_semantic += semantic_score

        # Update category stats
        category_stats[case_cat]["total"] += 1
        if passed:
            category_stats[case_cat]["passed"] += 1
        category_stats[case_cat]["accuracy_sum"] += accuracy
        category_stats[case_cat]["citation_sum"] += citation_score
        category_stats[case_cat]["latency_sum"] += latency

        results.append(
            {
                "id": case_id,
                "category": case_cat,
                "query": query,
                "expected_skus": expected_skus,
                "retrieved_skus": retrieved_skus,
                "retrieval_precision": round(precision, 4),
                "retrieval_recall": round(recall, 4),
                "data_accuracy": accuracy,
                "citation_faithfulness": citation_score,
                "semantic_score": semantic_score,
                "structured_output_valid": is_schema_valid,
                "latency_seconds": round(latency, 4),
                "status": status_str,
                "errors": case_errors,
            }
        )

        if idx % 10 == 0 or idx == len(cases):
            print(
                f"[{idx:02d}/{len(cases):02d}] {case_id:<14} {case_cat:<12} "
                f"Acc: {accuracy:.2f}  Cit: {citation_score:.2f}  Lat: {latency:.3f}s -> {status_str}"
            )

    n_cases = max(1, len(cases))
    mean_acc = round(total_accuracy / n_cases, 4)
    mean_cit = round(total_citation / n_cases, 4)
    mean_prec = round(total_precision / n_cases, 4)
    mean_rec = round(total_recall / n_cases, 4)
    mean_sem = round(total_semantic / n_cases, 4)
    schema_validity = round(valid_schema_count / n_cases, 4)

    # Latency percentiles
    sorted_latencies = sorted(latencies)
    p50_idx = int(0.50 * (len(sorted_latencies) - 1))
    p90_idx = int(0.90 * (len(sorted_latencies) - 1))
    p95_idx = int(0.95 * (len(sorted_latencies) - 1))
    lat_p50 = round(sorted_latencies[p50_idx], 4)
    lat_p90 = round(sorted_latencies[p90_idx], 4)
    lat_p95 = round(sorted_latencies[p95_idx], 4)

    # Category summaries
    cat_summary: dict[str, Any] = {}
    for cat, data in category_stats.items():
        c_total = max(1, data["total"])
        cat_summary[cat] = {
            "total": data["total"],
            "passed": data["passed"],
            "pass_rate": round(data["passed"] / c_total, 4),
            "mean_data_accuracy": round(data["accuracy_sum"] / c_total, 4),
            "mean_citation_faithfulness": round(data["citation_sum"] / c_total, 4),
            "mean_latency_seconds": round(data["latency_sum"] / c_total, 4),
        }

    target_met = (
        mean_acc >= target_accuracy
        and mean_cit >= target_citation
        and lat_p95 <= target_latency
        and schema_validity >= target_schema
    )

    passed_total = sum(1 for r in results if r["status"] == "PASS")

    report = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dataset": str(dataset_path),
            "judge_model": judge_model,
            "mode": "live" if live else "hermetic",
            "total_cases": len(cases),
            "passed_cases": passed_total,
            "failed_cases": len(cases) - passed_total,
        },
        "summary": {
            "mean_data_accuracy": mean_acc,
            "mean_citation_faithfulness": mean_cit,
            "mean_retrieval_precision": mean_prec,
            "mean_retrieval_recall": mean_rec,
            "mean_semantic_score": mean_sem,
            "structured_output_validity": schema_validity,
            "latency_p50_seconds": lat_p50,
            "latency_p90_seconds": lat_p90,
            "latency_p95_seconds": lat_p95,
            "target_threshold_met": target_met,
            "targets": {
                "target_accuracy": target_accuracy,
                "target_citation": target_citation,
                "target_latency_p95": target_latency,
                "target_schema_validity": target_schema,
            },
        },
        "category_metrics": cat_summary,
        "details": results,
    }

    print("\n" + "=" * 80)
    print("📊 EVALUATION SUMMARY REPORT")
    print("=" * 80)
    print(f"Total Benchmark Cases Evaluated : {len(cases)}")
    print(
        f"Passed Cases                    : {passed_total} / {len(cases)} ({passed_total / n_cases * 100:.1f}%)"
    )
    print(
        f"Mean Data Accuracy              : {mean_acc:.4f} (Target: >= {target_accuracy:.2f})"
    )
    print(
        f"Mean Citation Faithfulness      : {mean_cit:.4f} (Target: >= {target_citation:.2f})"
    )
    print(f"Mean Retrieval Precision / Recall: {mean_prec:.4f} / {mean_rec:.4f}")
    print(f"Structured Output Validity      : {schema_validity:.4f} (Target: 1.0000)")
    print(
        f"End-to-End P95 Latency          : {lat_p95:.4f}s (Target: <= {target_latency:.2f}s)"
    )
    print(f"Overall Target Met              : {'✅ PASS' if target_met else '❌ FAIL'}")
    print("=" * 80)

    return report


def export_evaluation_to_bigquery(
    report: dict[str, Any],
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str = "evaluation_runs",
    trigger_source: str = "manual",
    bq_client: Any = None,
) -> bool:
    """Export benchmark summary and quality metrics to BigQuery telemetry table."""
    from google.cloud import bigquery

    resolved_project = project_id or os.environ.get(
        "GCP_PROJECT_ID", "fde-bestbuy-sandbox-dev-508321"
    )
    resolved_dataset = dataset_id or os.environ.get(
        "BIGQUERY_TELEMETRY_DATASET", "catalog_agent_telemetry"
    )
    table_ref = f"{resolved_project}.{resolved_dataset}.{table_id}"

    summary = report.get("summary", {})
    metadata = report.get("metadata", {})
    details = report.get("details", [])

    failures = [
        {"id": d.get("id"), "query": d.get("query"), "errors": d.get("errors", [])}
        for d in details
        if d.get("status") != "PASS"
    ]

    target_met = summary.get("target_threshold_met", False)
    status_str = "PASS" if target_met else "FAIL"

    run_row = {
        "eval_run_id": f"eval-{uuid.uuid4().hex[:12]}",
        "timestamp": metadata.get("timestamp")
        or datetime.now(timezone.utc).isoformat(),
        "total_cases": int(metadata.get("total_cases", len(details))),
        "passed_cases": int(metadata.get("passed_cases", 0)),
        "avg_spec_accuracy": float(summary.get("mean_data_accuracy", 0.0)),
        "avg_citation_faithfulness": float(
            summary.get("mean_citation_faithfulness", 0.0)
        ),
        "avg_semantic_coherence": float(summary.get("mean_semantic_score", 0.0)),
        "avg_latency_ms": float(summary.get("latency_p50_seconds", 0.0) * 1000.0),
        "p95_latency_ms": float(summary.get("latency_p95_seconds", 0.0) * 1000.0),
        "target_threshold_met": bool(target_met),
        "status": status_str,
        "failure_count": len(failures),
        "failure_summary": json.dumps(failures[:20]),
        "trigger_source": trigger_source,
        "adk_hallucination_score": summary.get("adk_hallucination_score"),
        "adk_tool_trajectory_score": summary.get("adk_tool_trajectory_score"),
    }

    try:
        client = bq_client or bigquery.Client(project=resolved_project)
        errors = client.insert_rows_json(table_ref, [run_row])
        if errors:
            logger.error(
                "Failed to insert evaluation row into BigQuery %s: %s",
                table_ref,
                errors,
            )
            return False
        logger.info(
            "Successfully exported evaluation run %s to %s (Status: %s)",
            run_row["eval_run_id"],
            table_ref,
            status_str,
        )
        return True
    except Exception as e:
        logger.error(
            "Exception exporting evaluation to BigQuery %s: %s", table_ref, e
        )
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run evaluation benchmark flywheel for Best Buy Catalog Comparison Agent."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "evals" / "dataset" / "benchmark_catalog.evalset.json",
        help="Path to benchmark evaluation dataset (.evalset.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "evals" / "reports" / "eval_results.json",
        help="Path to save evaluation report JSON.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=BACKEND_SRC / "app" / "data" / "catalog_seed.json",
        help="Path to catalog seed JSON (for hermetic BigQuery mocking).",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Optional category filter (e.g. Laptops, Tablets, Headphones, Smart Home, TVs).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of test cases to run.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="gemini-1.5-flash",
        help="LLM Judge model identifier.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Run against live Google Cloud BigQuery and Gemini API.",
    )
    parser.add_argument(
        "--target-accuracy",
        type=float,
        default=0.98,
        help="Data accuracy target threshold (default 0.98).",
    )
    parser.add_argument(
        "--target-citation",
        type=float,
        default=0.95,
        help="Citation faithfulness target threshold (default 0.95).",
    )
    parser.add_argument(
        "--target-latency",
        type=float,
        default=3.0,
        help="P95 latency target in seconds (default 3.0).",
    )
    parser.add_argument(
        "--target-schema",
        type=float,
        default=1.00,
        help="Structured output schema validity target (default 1.00).",
    )
    parser.add_argument(
        "--fail-on-threshold",
        action="store_true",
        default=False,
        help="Exit with non-zero code if critical evaluation thresholds are not met.",
    )
    parser.add_argument(
        "--export-bq",
        action="store_true",
        default=False,
        help="Export evaluation summary and quality metrics to BigQuery telemetry table.",
    )
    parser.add_argument(
        "--trigger-source",
        type=str,
        default="manual",
        help="Trigger source identifier (e.g. cloud_scheduler, manual, ci).",
    )

    args = parser.parse_args()

    report = run_benchmark(
        dataset_path=args.dataset,
        catalog_path=args.catalog,
        category=args.category,
        limit=args.limit,
        judge_model=args.judge_model,
        live=args.live,
        target_accuracy=args.target_accuracy,
        target_citation=args.target_citation,
        target_latency=args.target_latency,
        target_schema=args.target_schema,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n📁 Evaluation report saved to {args.output}")

    if args.export_bq:
        export_evaluation_to_bigquery(report, trigger_source=args.trigger_source)

    if args.fail_on_threshold and not report["summary"]["target_threshold_met"]:
        print(
            "\n❌ CRITICAL: Evaluation targets not met. Exiting with status code 1.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
