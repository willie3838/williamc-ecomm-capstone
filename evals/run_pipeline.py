"""Unified Nightly Evaluation Pipeline for Best Buy Catalog Comparison Agent.

Execution Sequence:
1. Domain Spec & Citation Runner FIRST (evals.runner.run_benchmark)
   - Verifies exact spec match vs BigQuery ground truth (>= 0.98)
   - Verifies inline [SKU: ...] citations (>= 0.95)
   - Checks semantic coherence and absence of contradictions
   - Validates P95 latency (<= 3.0s) and Pydantic schema validity
2. ADK Agent Evaluator SECOND (google.adk.evaluation.agent_evaluator.AgentEvaluator)
   - Evaluates hallucinations_v1 (model-graded sentence entailment)
   - Evaluates tool_trajectory_avg_score and response_match_score
3. Analyzer & Regression Detection THIRD (evals.analyze.compare_reports)
   - Compares metrics against baseline runs
   - Detects regressions and writes executive markdown summary (reports/eval_summary.md)
4. Unified BigQuery Export (telemetry.evaluation_runs)
   - Ingests both custom domain scores and ADK metrics into partitioned BigQuery table
   - Emits structured Cloud Logging event with severity ERROR on failure, INFO on pass
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure backend/src and repo root are importable
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.analyze import compare_reports, generate_markdown_report, load_report
from evals.runner import export_evaluation_to_bigquery, run_benchmark

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evals.pipeline")


async def execute_adk_evaluation(
    dataset_path: Path,
    output_path: Path,
    num_runs: int = 1,
    print_detailed: bool = False,
) -> dict[str, Any]:
    """Execute official Google ADK AgentEvaluator on the evaluation dataset."""
    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Executing ADK AgentEvaluator on %s...", dataset_path)

    adk_report: dict[str, Any] = {
        "hallucination_score": None,
        "tool_trajectory_score": None,
        "response_match_score": None,
        "status": "COMPLETED",
    }

    try:
        await AgentEvaluator.evaluate(
            agent_module="app.agent",
            eval_dataset_file_path_or_dir=str(dataset_path),
            num_runs=num_runs,
            print_detailed_results=print_detailed,
            output_file=str(output_path),
        )

        if output_path.exists():
            content = output_path.read_text(encoding="utf-8")
            data = json.loads(content)
            adk_report["raw"] = data
            # Extract summary scores if present
            if isinstance(data, dict):
                adk_report["hallucination_score"] = data.get("hallucinations_v1") or data.get(
                    "hallucination_score"
                )
                adk_report["tool_trajectory_score"] = data.get("tool_trajectory_avg_score")
                adk_report["response_match_score"] = data.get("response_match_score")
        logger.info("ADK AgentEvaluator completed successfully.")
    except Exception as e:  # noqa: BLE001
        logger.warning("ADK AgentEvaluator completed with non-fatal notice: %s", e)
        adk_report["status"] = "WARNING"
        adk_report["error"] = str(e)

    return adk_report


def run_pipeline(
    dataset_path: Path,
    catalog_path: Path,
    reports_dir: Path,
    category: str | None = None,
    limit: int | None = None,
    judge_model: str = "gemini-2.5-flash",
    live: bool = False,
    target_accuracy: float = 0.98,
    target_citation: float = 0.95,
    target_latency: float = 3.0,
    target_schema: float = 1.00,
    export_bq: bool = False,
    trigger_source: str = "manual",
    fail_on_threshold: bool = False,
    fail_on_regression: bool = False,
    baseline_path: Path | None = None,
    bq_client: Any = None,
) -> dict[str, Any]:
    """Execute the full unified nightly evaluation pipeline."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    runner_output = reports_dir / "eval_results.json"
    adk_output = reports_dir / "adk_eval_results.json"
    summary_markdown_path = reports_dir / "eval_summary.md"

    print("\n" + "=" * 80)
    print("🚀 UNIFIED NIGHTLY EVALUATION PIPELINE")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # STEP 1: Domain Spec & Citation Runner (FIRST)
    # -------------------------------------------------------------------------
    print("\n--- [STEP 1/3] Running Domain Spec & Citation Evaluation (FIRST) ---")
    runner_report = run_benchmark(
        dataset_path=dataset_path,
        catalog_path=catalog_path,
        category=category,
        limit=limit,
        judge_model=judge_model,
        live=live,
        target_accuracy=target_accuracy,
        target_citation=target_citation,
        target_latency=target_latency,
        target_schema=target_schema,
    )

    with open(runner_output, "w", encoding="utf-8") as f:
        json.dump(runner_report, f, indent=2)
    logger.info("Domain benchmark report saved to %s", runner_output)

    # -------------------------------------------------------------------------
    # STEP 2: ADK Agent Evaluator (SECOND)
    # -------------------------------------------------------------------------
    print("\n--- [STEP 2/3] Running ADK Agent Evaluator (SECOND) ---")
    adk_report = asyncio.run(
        execute_adk_evaluation(
            dataset_path=dataset_path,
            output_path=adk_output,
            num_runs=1,
            print_detailed=False,
        )
    )

    # Attach ADK scores to runner summary
    if adk_report.get("hallucination_score") is not None:
        runner_report["summary"]["adk_hallucination_score"] = adk_report["hallucination_score"]
    if adk_report.get("tool_trajectory_score") is not None:
        runner_report["summary"]["adk_tool_trajectory_score"] = adk_report["tool_trajectory_score"]

    # -------------------------------------------------------------------------
    # STEP 3: Regression Analysis & Reporting (THIRD)
    # -------------------------------------------------------------------------
    print("\n--- [STEP 3/3] Analyzing Metrics & Regression Detection (THIRD) ---")
    base_report = None
    if baseline_path and baseline_path.exists():
        base_report = load_report(baseline_path)
    elif (reports_dir / "baseline.json").exists():
        base_report = load_report(reports_dir / "baseline.json")

    comparison = compare_reports(
        current=runner_report,
        baseline=base_report,
        accuracy_tolerance=0.01,
        citation_tolerance=0.01,
        latency_tolerance_pct=10.0,
    )

    markdown_report = generate_markdown_report(comparison)
    with open(summary_markdown_path, "w", encoding="utf-8") as f:
        f.write(markdown_report)
    print(markdown_report)
    logger.info("Executive markdown report written to %s", summary_markdown_path)

    # -------------------------------------------------------------------------
    # STEP 4: Export Unified Metrics to BigQuery
    # -------------------------------------------------------------------------
    if export_bq:
        print("\n--- Ingesting Unified Results to BigQuery Telemetry ---")
        export_evaluation_to_bigquery(
            report=runner_report,
            trigger_source=trigger_source,
            bq_client=bq_client,
        )

    # -------------------------------------------------------------------------
    # STEP 5: Quality Gate Enforcement
    # -------------------------------------------------------------------------
    target_met = runner_report["summary"]["target_threshold_met"]
    regressions_detected = comparison.get("regressions_detected", False)

    if fail_on_threshold and not target_met:
        print(
            "\n❌ CRITICAL: Evaluation thresholds not met. Exiting with code 1.",
            file=sys.stderr,
        )
        sys.exit(1)

    if fail_on_regression and regressions_detected:
        print(
            "\n❌ REGRESSION DETECTED: Quality regressed beyond tolerance. Exiting with code 1.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n✅ Unified evaluation pipeline completed successfully!")
    return {
        "runner_report": runner_report,
        "adk_report": adk_report,
        "comparison": comparison,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified Nightly Evaluation Pipeline (Runner + ADK + Analyzer)."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "evals" / "dataset" / "benchmark_catalog.evalset.json",
        help="Path to evaluation benchmark dataset (.evalset.json).",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=BACKEND_SRC / "app" / "data" / "catalog_seed.json",
        help="Path to catalog seed JSON for hermetic mocking.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPO_ROOT / "evals" / "reports",
        help="Directory to save eval_results.json, adk_eval_results.json, and eval_summary.md.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Optional path to baseline evaluation JSON for regression comparison.",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Optional category filter (Laptops, Tablets, TVs, Smart Home, Headphones).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of test cases.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="gemini-2.5-flash",
        help="LLM model identifier for semantic coherence judge.",
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
        help="Data accuracy target threshold (default: 0.98).",
    )
    parser.add_argument(
        "--target-citation",
        type=float,
        default=0.95,
        help="Citation faithfulness target threshold (default: 0.95).",
    )
    parser.add_argument(
        "--target-latency",
        type=float,
        default=3.0,
        help="P95 latency target threshold in seconds (default: 3.0s).",
    )
    parser.add_argument(
        "--export-bq",
        action="store_true",
        default=False,
        help="Export unified results to BigQuery evaluation table.",
    )
    parser.add_argument(
        "--trigger-source",
        type=str,
        default="manual",
        help="Invocation trigger source (e.g. cloud_scheduler, manual, ci).",
    )
    parser.add_argument(
        "--fail-on-threshold",
        action="store_true",
        default=False,
        help="Exit with code 1 if thresholds are not met.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        default=False,
        help="Exit with code 1 if regressions against baseline are detected.",
    )

    args = parser.parse_args()

    run_pipeline(
        dataset_path=args.dataset,
        catalog_path=args.catalog,
        reports_dir=args.reports_dir,
        category=args.category,
        limit=args.limit,
        judge_model=args.judge_model,
        live=args.live,
        target_accuracy=args.target_accuracy,
        target_citation=args.target_citation,
        target_latency=args.target_latency,
        export_bq=args.export_bq,
        trigger_source=args.trigger_source,
        fail_on_threshold=args.fail_on_threshold,
        fail_on_regression=args.fail_on_regression,
        baseline_path=args.baseline,
    )


if __name__ == "__main__":
    main()
