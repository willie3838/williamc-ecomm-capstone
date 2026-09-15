"""Evaluation analysis and regression detection tool for Quality Flywheel."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("evals.analyze")


def load_report(path: Path) -> dict[str, Any]:
    """Load JSON evaluation report."""
    if not path.exists():
        raise FileNotFoundError(f"Report file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_delta(
    delta: float, is_percentage: bool = False, higher_is_better: bool = True
) -> str:
    """Format metric delta with visual indicators."""
    if abs(delta) < 0.0001:
        return "= 0.00%" if is_percentage else "= 0.0000"

    sign = "+" if delta > 0 else ""
    val_str = f"{sign}{delta * 100:.2f}%" if is_percentage else f"{sign}{delta:.4f}"

    # Determine if delta is positive or negative change
    improved = (delta > 0) if higher_is_better else (delta < 0)
    indicator = "🟢" if improved else "🔴"
    return f"{indicator} {val_str}"


def compare_reports(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    accuracy_tolerance: float = 0.01,
    citation_tolerance: float = 0.01,
    latency_tolerance_pct: float = 10.0,
) -> dict[str, Any]:
    """Compare current and baseline eval runs, computing deltas and detecting regressions."""
    cur_sum = current.get("summary", {})
    base_sum = baseline.get("summary", {}) if baseline else {}

    cur_acc = cur_sum.get("mean_data_accuracy", 0.0)
    base_acc = base_sum.get("mean_data_accuracy", cur_acc)
    acc_delta = cur_acc - base_acc

    cur_cit = cur_sum.get("mean_citation_faithfulness", 0.0)
    base_cit = base_sum.get("mean_citation_faithfulness", cur_cit)
    cit_delta = cur_cit - base_cit

    cur_lat = cur_sum.get("latency_p95_seconds", 0.0)
    base_lat = base_sum.get("latency_p95_seconds", cur_lat)
    lat_delta = cur_lat - base_lat
    lat_pct_delta = ((lat_delta / base_lat) * 100) if base_lat > 0 else 0.0

    cur_schema = cur_sum.get("structured_output_validity", 0.0)
    base_schema = base_sum.get("structured_output_validity", cur_schema)
    schema_delta = cur_schema - base_schema

    # Identify individual case regressions
    regressions: list[dict[str, Any]] = []
    case_regressions: list[str] = []

    if baseline:
        base_cases = {c["id"]: c for c in baseline.get("details", [])}
        for cur_case in current.get("details", []):
            cid = cur_case["id"]
            if cid in base_cases:
                b_case = base_cases[cid]
                # Check status flip from PASS to FAIL
                if b_case.get("status") == "PASS" and cur_case.get("status") == "FAIL":
                    case_regressions.append(
                        f"Case {cid} flipped from PASS to FAIL: Errors: {cur_case.get('errors')}"
                    )
                # Check accuracy drop
                acc_diff = cur_case.get("data_accuracy", 0.0) - b_case.get(
                    "data_accuracy", 0.0
                )
                if acc_diff < -accuracy_tolerance:
                    case_regressions.append(
                        f"Case {cid} data accuracy dropped by {abs(acc_diff):.4f} ({b_case.get('data_accuracy')} -> {cur_case.get('data_accuracy')})"
                    )
                # Check citation drop
                cit_diff = cur_case.get("citation_faithfulness", 0.0) - b_case.get(
                    "citation_faithfulness", 0.0
                )
                if cit_diff < -citation_tolerance:
                    case_regressions.append(
                        f"Case {cid} citation faithfulness dropped by {abs(cit_diff):.4f} ({b_case.get('citation_faithfulness')} -> {cur_case.get('citation_faithfulness')})"
                    )

    # Check threshold violations
    regressions_found = False
    if baseline:
        if acc_delta < -accuracy_tolerance:
            regressions.append(
                {
                    "metric": "Data Accuracy",
                    "delta": acc_delta,
                    "reason": f"Dropped by {abs(acc_delta):.4f} (tolerance: {accuracy_tolerance:.4f})",
                }
            )
            regressions_found = True
        if cit_delta < -citation_tolerance:
            regressions.append(
                {
                    "metric": "Citation Faithfulness",
                    "delta": cit_delta,
                    "reason": f"Dropped by {abs(cit_delta):.4f} (tolerance: {citation_tolerance:.4f})",
                }
            )
            regressions_found = True
        if lat_pct_delta > latency_tolerance_pct and cur_lat > 1.0:
            regressions.append(
                {
                    "metric": "P95 Latency",
                    "delta": lat_pct_delta,
                    "reason": f"Increased by {lat_pct_delta:.1f}% (tolerance: {latency_tolerance_pct:.1f}%)",
                }
            )
            regressions_found = True

    if case_regressions:
        regressions_found = True

    # Target threshold check
    target_met = cur_sum.get("target_threshold_met", False)
    if not target_met:
        regressions.append(
            {
                "metric": "Target Thresholds",
                "delta": 0.0,
                "reason": "Current run failed one or more primary KPI target thresholds",
            }
        )

    # Category comparisons
    category_diffs: dict[str, Any] = {}
    cur_cats = current.get("category_metrics", {})
    base_cats = baseline.get("category_metrics", {}) if baseline else {}

    for cat, c_data in cur_cats.items():
        b_data = base_cats.get(cat, {})
        category_diffs[cat] = {
            "current_accuracy": c_data.get("mean_data_accuracy", 0.0),
            "baseline_accuracy": b_data.get(
                "mean_data_accuracy", c_data.get("mean_data_accuracy", 0.0)
            ),
            "accuracy_delta": round(
                c_data.get("mean_data_accuracy", 0.0)
                - b_data.get(
                    "mean_data_accuracy", c_data.get("mean_data_accuracy", 0.0)
                ),
                4,
            ),
            "current_citation": c_data.get("mean_citation_faithfulness", 0.0),
            "baseline_citation": b_data.get(
                "mean_citation_faithfulness",
                c_data.get("mean_citation_faithfulness", 0.0),
            ),
            "citation_delta": round(
                c_data.get("mean_citation_faithfulness", 0.0)
                - b_data.get(
                    "mean_citation_faithfulness",
                    c_data.get("mean_citation_faithfulness", 0.0),
                ),
                4,
            ),
            "pass_rate": c_data.get("pass_rate", 0.0),
            "latency_seconds": c_data.get("mean_latency_seconds", 0.0),
        }

    return {
        "summary": {
            "data_accuracy": {
                "current": cur_acc,
                "baseline": base_acc,
                "delta": round(acc_delta, 4),
                "target": cur_sum.get("targets", {}).get("target_accuracy", 0.98),
            },
            "citation_faithfulness": {
                "current": cur_cit,
                "baseline": base_cit,
                "delta": round(cit_delta, 4),
                "target": cur_sum.get("targets", {}).get("target_citation", 0.95),
            },
            "latency_p95_seconds": {
                "current": cur_lat,
                "baseline": base_lat,
                "delta": round(lat_delta, 4),
                "delta_pct": round(lat_pct_delta, 2),
                "target": cur_sum.get("targets", {}).get("target_latency_p95", 3.0),
            },
            "structured_output_validity": {
                "current": cur_schema,
                "baseline": base_schema,
                "delta": round(schema_delta, 4),
                "target": cur_sum.get("targets", {}).get("target_schema_validity", 1.0),
            },
        },
        "category_metrics": category_diffs,
        "regressions_detected": regressions_found,
        "regression_details": regressions,
        "case_regressions": case_regressions,
        "verdict": "PASSED"
        if not regressions_found and target_met
        else "REGRESSION_DETECTED",
    }


def generate_markdown_report(comparison: dict[str, Any]) -> str:
    """Render a structured GitHub-flavored Markdown evaluation analysis report."""
    s = comparison["summary"]
    verdict = comparison["verdict"]
    verdict_emoji = "✅" if verdict == "PASSED" else "❌"

    lines = [
        "# Evaluation Flywheel Analysis Report",
        "",
        f"**Overall Verdict**: {verdict_emoji} **{verdict}**",
        "",
        "## 1. Primary Evaluation Metrics Progression",
        "",
        "| Metric | Baseline | Current | Delta | Target | Threshold Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    # Data Accuracy
    acc = s["data_accuracy"]
    acc_status = "PASS" if acc["current"] >= acc["target"] else "FAIL"
    lines.append(
        f"| **Data Accuracy** | {acc['baseline']:.4f} | {acc['current']:.4f} | {format_delta(acc['delta'], higher_is_better=True)} | $\\ge {acc['target']:.2f}$ | {acc_status} |"
    )

    # Citation Faithfulness
    cit = s["citation_faithfulness"]
    cit_status = "PASS" if cit["current"] >= cit["target"] else "FAIL"
    lines.append(
        f"| **Citation Faithfulness** | {cit['baseline']:.4f} | {cit['current']:.4f} | {format_delta(cit['delta'], higher_is_better=True)} | $\\ge {cit['target']:.2f}$ | {cit_status} |"
    )

    # Schema Validity
    schema = s["structured_output_validity"]
    schema_status = "PASS" if schema["current"] >= schema["target"] else "FAIL"
    lines.append(
        f"| **Structured Output Validity** | {schema['baseline']:.4f} | {schema['current']:.4f} | {format_delta(schema['delta'], higher_is_better=True)} | $1.00$ | {schema_status} |"
    )

    # P95 Latency
    lat = s["latency_p95_seconds"]
    lat_status = "PASS" if lat["current"] <= lat["target"] else "FAIL"
    lines.append(
        f"| **P95 Latency** | {lat['baseline']:.4f}s | {lat['current']:.4f}s | {format_delta(lat['delta_pct'], is_percentage=True, higher_is_better=False)} | $\\le {lat['target']:.1f}$s | {lat_status} |"
    )

    lines.extend(
        [
            "",
            "## 2. Category Performance Breakdown",
            "",
            "| Category | Data Accuracy | Citation Faithfulness | Pass Rate | Mean Latency |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )

    for cat, data in comparison.get("category_metrics", {}).items():
        lines.append(
            f"| **{cat}** | {data['current_accuracy']:.4f} ({format_delta(data['accuracy_delta'])}) | "
            f"{data['current_citation']:.4f} ({format_delta(data['citation_delta'])}) | "
            f"{data['pass_rate'] * 100:.1f}% | {data['latency_seconds']:.4f}s |"
        )

    lines.extend(
        [
            "",
            "## 3. Regression Analysis & Anomalies",
            "",
        ]
    )

    reg_details = comparison.get("regression_details", [])
    case_regs = comparison.get("case_regressions", [])

    if not reg_details and not case_regs:
        lines.append(
            "🎉 **No regressions detected.** All metrics maintained or improved within tolerance thresholds."
        )
    else:
        if reg_details:
            lines.append("### High-Level Metric Violations:")
            for r in reg_details:
                lines.append(f"- ⚠️ **{r['metric']}**: {r['reason']}")
            lines.append("")

        if case_regs:
            lines.append("### Test Case Regressions:")
            for cr in case_regs:
                lines.append(f"- ❌ {cr}")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze evaluation reports and detect metric regressions."
    )
    parser.add_argument(
        "--current",
        type=Path,
        required=True,
        help="Path to current evaluation results JSON.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to baseline evaluation results JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write markdown comparison report.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        default=False,
        help="Exit with status code 1 if any metric regression is detected.",
    )
    parser.add_argument(
        "--accuracy-tolerance",
        type=float,
        default=0.01,
        help="Allowed drop in accuracy before flagging regression (default 0.01).",
    )
    parser.add_argument(
        "--citation-tolerance",
        type=float,
        default=0.01,
        help="Allowed drop in citation faithfulness before flagging regression (default 0.01).",
    )
    parser.add_argument(
        "--latency-tolerance-pct",
        type=float,
        default=10.0,
        help="Allowed percentage increase in latency before flagging regression (default 10.0%%).",
    )

    args = parser.parse_args()

    cur_report = load_report(args.current)
    base_report = load_report(args.baseline) if args.baseline else None

    comparison = compare_reports(
        current=cur_report,
        baseline=base_report,
        accuracy_tolerance=args.accuracy_tolerance,
        citation_tolerance=args.citation_tolerance,
        latency_tolerance_pct=args.latency_tolerance_pct,
    )

    markdown = generate_markdown_report(comparison)
    print("\n" + markdown)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"\n📄 Markdown report written to {args.output}")

    if args.fail_on_regression and comparison["regressions_detected"]:
        print(
            "\n❌ REGRESSION DETECTED: Exiting with status code 1 due to --fail-on-regression.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
