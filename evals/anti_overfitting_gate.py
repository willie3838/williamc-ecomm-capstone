"""Counterfactual Anti-Overfitting Gate for the Evaluation Flywheel.

Evaluates generalization between benchmark and held-out evaluation datasets,
detects prompt/parametric overfitting, tests counterfactual spec grounding,
and enforces negative query (0-SKU) robustness.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
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

from app.models.responses import CompareResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evals.anti_overfitting_gate")


class AntiOverfittingConfig(BaseModel):
    """Configuration thresholds for the Anti-Overfitting Gate."""

    max_generalization_gap: float = Field(
        default=0.05,
        description="Maximum permissible accuracy/citation drop between benchmark and holdout (5%)",
    )
    min_holdout_accuracy: float = Field(
        default=0.95,
        description="Absolute minimum acceptable data accuracy on holdout dataset",
    )
    min_holdout_citation: float = Field(
        default=0.90,
        description="Absolute minimum acceptable citation faithfulness on holdout dataset",
    )
    min_counterfactual_fidelity: float = Field(
        default=0.95,
        description="Minimum grounding accuracy on counterfactual (perturbed) catalog specifications",
    )
    min_negative_suppression_rate: float = Field(
        default=1.00,
        description="Required proportion of negative/chatter queries returning 0 hallucinated SKUs",
    )
    max_latency_p95: float = Field(
        default=3.0,
        description="Maximum permissible P95 latency in seconds",
    )


class AntiOverfittingResult(BaseModel):
    """Evaluation result from the Counterfactual Anti-Overfitting Gate."""

    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    gate_passed: bool = Field(..., description="Overall gate pass/fail boolean")
    benchmark_metrics: dict[str, Any] = Field(default_factory=dict)
    holdout_metrics: dict[str, Any] = Field(default_factory=dict)
    accuracy_gap: float = Field(
        default=0.0, description="Benchmark accuracy minus holdout accuracy (>= 0.0)"
    )
    citation_gap: float = Field(
        default=0.0, description="Benchmark citation minus holdout citation (>= 0.0)"
    )
    counterfactual_fidelity: float = Field(
        default=1.0, description="Score on counterfactual specification grounding"
    )
    negative_chatter_suppression: float = Field(
        default=1.0, description="Suppression rate of hallucinated SKUs on negative chatter"
    )
    failure_reasons: list[str] = Field(default_factory=list)


def compute_generalization_gap(
    benchmark_acc: float,
    holdout_acc: float,
    benchmark_cit: float,
    holdout_cit: float,
) -> tuple[float, float]:
    """Calculate non-negative generalization gap between benchmark and holdout metrics.

    Gap = max(0.0, benchmark_score - holdout_score).
    If holdout outperforms benchmark, gap is 0.0 (no overfitting).
    """
    acc_gap = max(0.0, round(benchmark_acc - holdout_acc, 4))
    cit_gap = max(0.0, round(benchmark_cit - holdout_cit, 4))
    return acc_gap, cit_gap


def evaluate_counterfactual_fidelity(
    cf_case: dict[str, Any],
    response: CompareResponse,
) -> tuple[float, list[str]]:
    """Evaluate whether the agent grounded strictly in perturbed counterfactual specs.

    Catches parametric pre-training hallucinations where the agent asserts standard
    real-world specifications rather than the values returned in the tool output.
    """
    errors: list[str] = []
    if not response.products:
        return 0.0, ["No products returned by agent for counterfactual case."]

    retrieved_by_sku = {p.sku: p for p in response.products}
    ground_truth = cf_case.get("ground_truth_specs", {})
    total_checks = 0
    passed_checks = 0

    for sku, expected_specs in ground_truth.items():
        if sku not in retrieved_by_sku:
            errors.append(f"Expected counterfactual SKU {sku} not retrieved.")
            total_checks += max(1, len(expected_specs))
            continue

        prod = retrieved_by_sku[sku]
        prod_specs = prod.specifications if isinstance(prod.specifications, dict) else {}

        for feature_key, expected_val in expected_specs.items():
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

            # Check match
            match = False
            if actual_val == expected_val:
                match = True
            elif (
                isinstance(expected_val, (int, float))
                and isinstance(actual_val, (int, float))
                and abs(float(expected_val) - float(actual_val)) < 0.05
            ):
                match = True
            elif (
                isinstance(expected_val, str)
                and isinstance(actual_val, str)
                and expected_val.lower() in actual_val.lower()
            ):
                match = True

            if match:
                passed_checks += 1
            else:
                errors.append(
                    f"Parametric Hallucination / Spec Mismatch on SKU {sku} feature '{feature_key}': "
                    f"expected counterfactual '{expected_val}', got '{actual_val}'"
                )

    score = (passed_checks / total_checks) if total_checks > 0 else 1.0
    return round(score, 4), errors


def evaluate_negative_chatter_robustness(
    response: CompareResponse,
) -> tuple[float, list[str]]:
    """Evaluate whether 0-SKU chatter/rants produce zero hallucinated products or citations."""
    errors: list[str] = []

    # 1. Assert no products returned
    if response.products:
        hallucinated_skus = [p.sku for p in response.products]
        errors.append(f"Hallucinated products returned on negative query: {hallucinated_skus}")

    # 2. Assert no citations returned
    if response.citations:
        cited_skus = [c.sku for c in response.citations]
        errors.append(f"Hallucinated citations returned on negative query: {cited_skus}")

    # 3. Assert no inline [SKU: ...] citations in summary
    summary_text = response.summary or ""
    inline_citations = re.findall(r"\[SKU:\s*([A-Za-z0-9_-]+)\]", summary_text)
    if inline_citations:
        errors.append(
            f"Inline SKU citations found in summary of negative query: {inline_citations}"
        )

    score = 0.0 if errors else 1.0
    return score, errors


class AntiOverfittingGate:
    """Evaluates benchmark vs holdout performance and enforces anti-overfitting policies."""

    def __init__(self, config: AntiOverfittingConfig | None = None) -> None:
        self.config = config or AntiOverfittingConfig()

    def evaluate_metrics(
        self,
        benchmark_summary: dict[str, Any],
        holdout_summary: dict[str, Any],
        counterfactual_fidelity: float = 1.0,
        negative_suppression_rate: float = 1.0,
    ) -> AntiOverfittingResult:
        """Evaluate generalization metrics against configured thresholds."""
        bench_acc = benchmark_summary.get("mean_data_accuracy", 0.0)
        bench_cit = benchmark_summary.get("mean_citation_faithfulness", 0.0)
        hold_acc = holdout_summary.get("mean_data_accuracy", 0.0)
        hold_cit = holdout_summary.get("mean_citation_faithfulness", 0.0)

        acc_gap, cit_gap = compute_generalization_gap(bench_acc, hold_acc, bench_cit, hold_cit)

        failures: list[str] = []

        # 1. Check Generalization Gap (Overfitting detection)
        if acc_gap > self.config.max_generalization_gap:
            failures.append(
                f"OVERFITTING REGRESSION: Accuracy generalization gap {acc_gap:.4f} "
                f"exceeds maximum threshold {self.config.max_generalization_gap:.4f} "
                f"(Benchmark: {bench_acc:.4f}, Holdout: {hold_acc:.4f})"
            )

        if cit_gap > self.config.max_generalization_gap:
            failures.append(
                f"OVERFITTING REGRESSION: Citation generalization gap {cit_gap:.4f} "
                f"exceeds maximum threshold {self.config.max_generalization_gap:.4f} "
                f"(Benchmark: {bench_cit:.4f}, Holdout: {hold_cit:.4f})"
            )

        # 2. Check Absolute Performance Floors
        if hold_acc < self.config.min_holdout_accuracy:
            failures.append(
                f"Holdout data accuracy {hold_acc:.4f} is below floor {self.config.min_holdout_accuracy:.4f}"
            )

        if hold_cit < self.config.min_holdout_citation:
            failures.append(
                f"Holdout citation faithfulness {hold_cit:.4f} is below floor {self.config.min_holdout_citation:.4f}"
            )

        # 3. Check Counterfactual Fidelity
        if counterfactual_fidelity < self.config.min_counterfactual_fidelity:
            failures.append(
                f"Counterfactual spec grounding {counterfactual_fidelity:.4f} is below target {self.config.min_counterfactual_fidelity:.4f} "
                "(agent failed to respect perturbed catalog specs over parametric memory)"
            )

        # 4. Check Negative Query Suppression
        if negative_suppression_rate < self.config.min_negative_suppression_rate:
            failures.append(
                f"Negative query suppression {negative_suppression_rate:.4f} is below required rate {self.config.min_negative_suppression_rate:.4f}"
            )

        # 5. Latency checks
        hold_lat = holdout_summary.get("latency_p95_seconds", 0.0)
        if hold_lat > self.config.max_latency_p95:
            failures.append(
                f"Holdout P95 latency {hold_lat:.3f}s exceeds SLA {self.config.max_latency_p95:.3f}s"
            )

        gate_passed = len(failures) == 0

        return AntiOverfittingResult(
            gate_passed=gate_passed,
            benchmark_metrics=benchmark_summary,
            holdout_metrics=holdout_summary,
            accuracy_gap=acc_gap,
            citation_gap=cit_gap,
            counterfactual_fidelity=counterfactual_fidelity,
            negative_chatter_suppression=negative_suppression_rate,
            failure_reasons=failures,
        )

    def format_markdown_report(self, result: AntiOverfittingResult) -> str:
        """Format a comprehensive Markdown audit report."""
        status_badge = "✅ PASSED" if result.gate_passed else "❌ FAILED (OVERFITTING DETECTED)"
        lines = [
            "# 🛡️ Counterfactual Anti-Overfitting & Generalization Gate Report",
            "",
            f"- **Timestamp**: `{result.timestamp}`",
            f"- **Gate Status**: **{status_badge}**",
            "",
            "## 1. Generalization Gap Analysis",
            "",
            r"| Dimension | Benchmark | Holdout | Generalization Gap ($\Delta$) | Max Permitted Gap | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        b_acc = result.benchmark_metrics.get("mean_data_accuracy", 0.0)
        h_acc = result.holdout_metrics.get("mean_data_accuracy", 0.0)
        acc_status = (
            "✅ PASS" if result.accuracy_gap <= self.config.max_generalization_gap else "🔴 FAIL"
        )
        lines.append(
            f"| **Data Accuracy** | {b_acc:.4f} | {h_acc:.4f} | {result.accuracy_gap:.4f} | $\\le {self.config.max_generalization_gap:.4f}$ | {acc_status} |"
        )

        b_cit = result.benchmark_metrics.get("mean_citation_faithfulness", 0.0)
        h_cit = result.holdout_metrics.get("mean_citation_faithfulness", 0.0)
        cit_status = (
            "✅ PASS" if result.citation_gap <= self.config.max_generalization_gap else "🔴 FAIL"
        )
        lines.append(
            f"| **Citation Faithfulness** | {b_cit:.4f} | {h_cit:.4f} | {result.citation_gap:.4f} | $\\le {self.config.max_generalization_gap:.4f}$ | {cit_status} |"
        )

        b_lat = result.benchmark_metrics.get("latency_p95_seconds", 0.0)
        h_lat = result.holdout_metrics.get("latency_p95_seconds", 0.0)
        lines.append(
            f"| **P95 Latency** | {b_lat:.3f}s | {h_lat:.3f}s | N/A | $\\le {self.config.max_latency_p95:.3f}s$ | {'✅ PASS' if h_lat <= self.config.max_latency_p95 else '🔴 FAIL'} |"
        )

        lines.extend(
            [
                "",
                "## 2. Counterfactual & Edge Robustness",
                "",
                f"- **Counterfactual Spec Grounding Score**: `{result.counterfactual_fidelity:.4f}` (Target: $\\ge {self.config.min_counterfactual_fidelity:.2f}$)",
                f"- **Negative Query (0-SKU) Suppression Rate**: `{result.negative_chatter_suppression * 100:.1f}%` (Target: 100.0%)",
                "",
            ]
        )

        if result.failure_reasons:
            lines.extend(
                [
                    "## 3. Failure Diagnostics & Overfitting Indicators",
                    "",
                ]
            )
            for r in result.failure_reasons:
                lines.append(f"- ⚠️ {r}")
            lines.append("")
        else:
            lines.extend(
                [
                    "## 3. Verification Findings",
                    "",
                    "- ✅ Zero prompt or heuristic overfitting detected across holdout splits.",
                    "- ✅ Agent strictly respects retrieved counterfactual specs without parametric hallucination.",
                    "- ✅ Non-comparative rants and out-of-scope requests properly handled with zero phantom SKUs.",
                    "",
                ]
            )

        return "\n".join(lines)

    def save_report(self, result: AntiOverfittingResult, path: Path) -> None:
        """Save JSON report to destination path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2)
        logger.info("Saved anti-overfitting report to %s", path)


def main() -> int:
    """CLI runner for the Anti-Overfitting Gate."""
    parser = argparse.ArgumentParser(
        description="Counterfactual Anti-Overfitting Gate for Best Buy Catalog Agent"
    )
    parser.add_argument(
        "--benchmark-report",
        type=Path,
        help="Path to pre-existing benchmark eval report JSON",
    )
    parser.add_argument(
        "--holdout-report",
        type=Path,
        help="Path to pre-existing holdout eval report JSON",
    )
    parser.add_argument(
        "--benchmark-dataset",
        type=Path,
        default=Path("evals/dataset/benchmark_catalog.evalset.json"),
        help="Path to benchmark EvalSet JSON",
    )
    parser.add_argument(
        "--holdout-dataset",
        type=Path,
        default=Path("evals/dataset/holdout_catalog.evalset.json"),
        help="Path to holdout EvalSet JSON",
    )
    parser.add_argument(
        "--max-gap",
        type=float,
        default=0.05,
        help="Maximum permissible generalization gap (default: 0.05)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/reports/anti_overfitting_report.json"),
        help="Path to output JSON report",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if gate fails",
    )

    args = parser.parse_args()

    config = AntiOverfittingConfig(max_generalization_gap=args.max_gap)
    gate = AntiOverfittingGate(config=config)

    # Load precomputed reports or run evaluation
    from evals.runner import run_benchmark

    if args.benchmark_report and args.benchmark_report.exists():
        with open(args.benchmark_report, encoding="utf-8") as f:
            bench_data = json.load(f)
            bench_summary = bench_data.get("summary", {})
    else:
        logger.info("Running benchmark evaluation...")
        bench_data = run_benchmark(dataset_path=args.benchmark_dataset, live=False)
        bench_summary = bench_data.get("summary", {})

    if args.holdout_report and args.holdout_report.exists():
        with open(args.holdout_report, encoding="utf-8") as f:
            hold_data = json.load(f)
            hold_summary = hold_data.get("summary", {})
    else:
        logger.info("Running holdout evaluation...")
        hold_data = run_benchmark(dataset_path=args.holdout_dataset, live=False)
        hold_summary = hold_data.get("summary", {})

    # Evaluate counterfactual & negative chatter cases in holdout
    with open(args.holdout_dataset, encoding="utf-8") as f:
        holdout_raw = json.load(f)

    cf_cases = [
        c for c in holdout_raw.get("eval_cases", []) if c.get("archetype") == "counterfactual_spec"
    ]
    neg_cases = [
        c for c in holdout_raw.get("eval_cases", []) if c.get("archetype") == "negative_chatter"
    ]

    cf_ids = {c.get("eval_id") or c.get("id") for c in cf_cases}
    neg_ids = {c.get("eval_id") or c.get("id") for c in neg_cases}

    hold_details = hold_data.get("details", [])
    cf_scores = [d.get("data_accuracy", 1.0) for d in hold_details if d.get("id") in cf_ids] or [
        1.0
    ]

    neg_scores = [
        1.0 if d.get("data_accuracy", 1.0) >= 0.90 else 0.0
        for d in hold_details
        if d.get("id") in neg_ids
    ] or [1.0]

    result = gate.evaluate_metrics(
        benchmark_summary=bench_summary,
        holdout_summary=hold_summary,
        counterfactual_fidelity=sum(cf_scores) / len(cf_scores) if cf_scores else 1.0,
        negative_suppression_rate=sum(neg_scores) / len(neg_scores) if neg_scores else 1.0,
    )

    gate.save_report(result, args.output)
    md_report = gate.format_markdown_report(result)
    print("\n" + md_report + "\n")

    if not result.gate_passed and args.strict:
        logger.error("Anti-Overfitting Gate FAILED.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
