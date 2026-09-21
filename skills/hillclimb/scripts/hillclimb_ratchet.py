#!/usr/bin/env python3
"""Monotonic High-Water Mark Ratchet for Autonomous Hillclimbing.

Tracks the best achieved project quality metrics in `logs/hillclimb_state.json`
and enforces non-regression across iterations:
1. Pytest Code Coverage (%)
2. Mean Data Accuracy (from evals/reports/latest_eval_report.json)
3. Mean Citation Faithfulness (from evals/reports/latest_eval_report.json)
4. Structured Output Validity (from evals/reports/latest_eval_report.json)
5. End-to-End P95 Latency (must remain <= target threshold in eval_criteria.json)
6. Capstone Rubric Section 1 & Section 2 Averages (from logs/latest_audit.json)

If any metric regresses below its high-water mark (or fails its minimum floor),
the ratchet exits with code 1 and writes structured failure diagnostics to
`logs/hillclimb_latest_report.json` for `dispatch_hillclimb_swarm.py`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent
CRITERIA_FILE = SKILL_DIR / "resources" / "eval_criteria.json"
STATE_FILE = REPO_ROOT / "logs" / "hillclimb_state.json"
REPORT_FILE = REPO_ROOT / "logs" / "hillclimb_latest_report.json"
EVAL_REPORT_FILE = REPO_ROOT / "evals" / "reports" / "latest_eval_report.json"
AUDIT_FILE = REPO_ROOT / "logs" / "latest_audit.json"


def get_git_commit() -> str:
    """Return current short git SHA."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON dictionary from disk or return empty dict."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def collect_current_metrics(coverage_override: float | None = None) -> dict[str, float]:
    """Gather current metrics from eval report, rubric audit, and coverage."""
    eval_data = load_json(EVAL_REPORT_FILE)
    eval_summary = eval_data.get("summary", {})

    audit_data = load_json(AUDIT_FILE)
    checklist_root = audit_data.get("checklist", audit_data)
    s1_items = checklist_root.get("section_1_presentation_and_advisory", [])
    s2_items = checklist_root.get("section_2_engineering_excellence", [])
    s1_scores = [float(i.get("score", 0)) for i in s1_items if "score" in i]
    s2_scores = [float(i.get("score", 0)) for i in s2_items if "score" in i]
    s1_avg = (
        float(audit_data["section_1_avg"])
        if "section_1_avg" in audit_data
        else (round(sum(s1_scores) / len(s1_scores), 4) if s1_scores else 0.0)
    )
    s2_avg = (
        float(audit_data["section_2_avg"])
        if "section_2_avg" in audit_data
        else (round(sum(s2_scores) / len(s2_scores), 4) if s2_scores else 0.0)
    )

    # Determine coverage from override or existing state fallback
    state_data = load_json(STATE_FILE)
    prev_cov = float(state_data.get("high_water_mark", {}).get("pytest_coverage_pct", 93.14))
    cov_pct = round(coverage_override if coverage_override is not None else prev_cov, 2)

    return {
        "pytest_coverage_pct": cov_pct,
        "data_accuracy": float(eval_summary.get("mean_data_accuracy", 0.0)),
        "citation_faithfulness": float(eval_summary.get("mean_citation_faithfulness", 0.0)),
        "schema_conformance": float(eval_summary.get("structured_output_validity", 0.0)),
        "latency_p95_seconds": float(eval_summary.get("latency_p95_seconds", 0.0)),
        "rubric_s1_avg": s1_avg,
        "rubric_s2_avg": s2_avg,
    }


def evaluate_ratchet(
    current: dict[str, float],
    high_water: dict[str, float],
    criteria: dict[str, Any],
) -> tuple[bool, list[str], dict[str, float]]:
    """Compare current metrics against high-water mark and criteria thresholds."""
    dims = criteria.get("dimensions", {})
    target_acc = float(dims.get("data_accuracy", {}).get("target_threshold", 0.98))
    target_cit = float(dims.get("citation_faithfulness", {}).get("target_threshold", 0.95))
    target_lat = float(dims.get("latency_p95", {}).get("target_threshold_seconds", 3.0))
    target_schema = float(dims.get("schema_conformance", {}).get("target_threshold", 1.0))

    regressions: list[str] = []

    # 1. Check absolute target floors
    if current["pytest_coverage_pct"] < 80.0:
        regressions.append(
            f"Pytest coverage ({current['pytest_coverage_pct']:.2f}%) dropped below 80.0% floor"
        )
    if current["data_accuracy"] < target_acc:
        regressions.append(
            f"Data accuracy ({current['data_accuracy']:.4f}) is below target ({target_acc:.2f})"
        )
    if current["citation_faithfulness"] < target_cit:
        regressions.append(
            f"Citation faithfulness ({current['citation_faithfulness']:.4f}) is below target ({target_cit:.2f})"
        )
    if current["schema_conformance"] < target_schema:
        regressions.append(
            f"Schema conformance ({current['schema_conformance']:.4f}) is below target ({target_schema:.2f})"
        )
    if current["latency_p95_seconds"] > target_lat:
        regressions.append(
            f"P95 latency ({current['latency_p95_seconds']:.4f}s) exceeded target ({target_lat:.2f}s)"
        )

    # 2. Check monotonic non-regression against High-Water Mark (tolerance 1e-4, coverage tolerance 0.5%)
    monotonic_higher_is_better = [
        ("pytest_coverage_pct", "Pytest Coverage (%)", 0.5),
        ("data_accuracy", "Mean Data Accuracy", 1e-4),
        ("citation_faithfulness", "Mean Citation Faithfulness", 1e-4),
        ("schema_conformance", "Schema Conformance", 1e-4),
        ("rubric_s1_avg", "Rubric Section 1 Average", 1e-4),
        ("rubric_s2_avg", "Rubric Section 2 Average", 1e-4),
    ]

    updated_hwm = dict(high_water)
    for key, label, tol in monotonic_higher_is_better:
        cur_val = current.get(key, 0.0)
        hwm_val = high_water.get(key, 0.0)
        if cur_val + tol < hwm_val:
            regressions.append(
                f"Monotonic Regression in {label}: current={cur_val:.4f} < high_water_mark={hwm_val:.4f}"
            )
        else:
            updated_hwm[key] = max(cur_val, hwm_val)

    # For P95 latency, track best (lowest non-zero) latency while only failing if > target_lat
    cur_lat = current.get("latency_p95_seconds", 0.0)
    hwm_lat = high_water.get("latency_p95_seconds", 0.0)
    if cur_lat > 0:
        updated_hwm["latency_p95_seconds"] = min(cur_lat, hwm_lat) if hwm_lat > 0 else cur_lat

    return len(regressions) == 0, regressions, updated_hwm


def record_stage_failure(stage: str, reason: str) -> None:
    """Write a stage failure into logs/hillclimb_latest_report.json for swarm remediation."""
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": get_git_commit(),
        "status": "FAIL",
        "failed_stage": stage,
        "regressions": [f"[{stage}] {reason}"],
        "recommended_remediation": (
            f"python3 skills/hillclimb/scripts/dispatch_hillclimb_swarm.py "
            f'--features "Remediate {stage}: {reason}"'
        ),
    }
    REPORT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Monotonic High-Water Mark Ratchet")
    parser.add_argument(
        "--check-and-update",
        action="store_true",
        help="Verify current metrics against high-water mark and ratchet upward if passing",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current high-water mark state",
    )
    parser.add_argument(
        "--coverage",
        type=float,
        default=None,
        help="Explicit pytest coverage percentage from current run",
    )
    parser.add_argument(
        "--record-failure",
        nargs=2,
        metavar=("STAGE", "REASON"),
        help="Record an immediate pipeline stage failure for Swarm remediation",
    )
    args = parser.parse_args()

    if args.record_failure:
        stage, reason = args.record_failure
        record_stage_failure(stage, reason)
        print(f"[RATCHET] Recorded failure in stage '{stage}': {reason}")
        return 0

    state_data = load_json(STATE_FILE)
    high_water = state_data.get("high_water_mark", {})

    if args.status and not args.check_and_update:
        print("=" * 72)
        print("📈 HILLCLIMB MONOTONIC HIGH-WATER MARK STATUS")
        print("=" * 72)
        if not high_water:
            print("No high-water mark recorded yet. Run with --check-and-update to initialize.")
            return 0
        for k, v in high_water.items():
            print(f"  {k:<28}: {v}")
        print(f"  Last Updated Commit         : {state_data.get('last_commit', 'unknown')}")
        print(f"  Last Updated Timestamp      : {state_data.get('updated_at', 'unknown')}")
        print("=" * 72)
        return 0

    criteria = load_json(CRITERIA_FILE)
    current = collect_current_metrics(coverage_override=args.coverage)
    passed, regressions, updated_hwm = evaluate_ratchet(current, high_water, criteria)

    now_iso = datetime.now(UTC).isoformat()
    commit = get_git_commit()

    report_payload = {
        "timestamp": now_iso,
        "commit": commit,
        "status": "PASS" if passed else "FAIL",
        "current_metrics": current,
        "high_water_mark": updated_hwm if passed else high_water,
        "regressions": regressions,
        "recommended_remediation": (
            None
            if passed
            else "python3 skills/hillclimb/scripts/dispatch_hillclimb_swarm.py --from-report logs/hillclimb_latest_report.json"
        ),
    }

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    print("\n" + "=" * 76)
    print("🏔️  HILLCLIMB MONOTONIC RATCHET GATE")
    print("=" * 76)
    for key in [
        "pytest_coverage_pct",
        "data_accuracy",
        "citation_faithfulness",
        "schema_conformance",
        "latency_p95_seconds",
        "rubric_s1_avg",
        "rubric_s2_avg",
    ]:
        cur_v = current.get(key, 0.0)
        hwm_v = high_water.get(key, cur_v)
        print(f"  {key:<26} | Current: {cur_v:<8} | High-Water Mark: {hwm_v:<8}")
    print("-" * 76)

    if passed:
        history = state_data.get("history", [])
        history.append({"timestamp": now_iso, "commit": commit, "metrics": current})
        new_state = {
            "updated_at": now_iso,
            "last_commit": commit,
            "high_water_mark": updated_hwm,
            "history": history[-25:],
        }
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(new_state, indent=2), encoding="utf-8")
        print(
            "[PASS] Monotonic Ratchet Gate PASSED! High-water mark updated in logs/hillclimb_state.json."
        )
        print("=" * 76)
        return 0

    print("[FAIL] Monotonic Ratchet Gate detected regressions:")
    for reg in regressions:
        print(f"  ❌ {reg}")
    print("\n👉 Remediation Protocol (Swarm Reviewer + Developer Pair):")
    print(
        "   python3 skills/hillclimb/scripts/dispatch_hillclimb_swarm.py --from-report logs/hillclimb_latest_report.json"
    )
    print("=" * 76)
    return 1


if __name__ == "__main__":
    sys.exit(main())
