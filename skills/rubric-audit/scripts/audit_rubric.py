#!/usr/bin/env python3
"""Deterministic FDE Capstone Rubric Audit Validator & History Recorder.

Provides schema validation, mathematical score computation, chronological
progression logging in logs/rubric_audit_history.md, and command-line reporting
for Agent-Driven Rubric Audits. All qualitative and architectural evaluation
is performed agentically by the LLM agent without keyword or regex heuristics.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RESOURCES_DIR = SKILL_DIR / "resources"
CHECKLIST_PATH = RESOURCES_DIR / "rubric_checklist.json"
REPO_ROOT = SKILL_DIR.parent.parent
DEFAULT_LOG_FILE = REPO_ROOT / "logs" / "rubric_audit_history.md"
LATEST_AUDIT_FILE = REPO_ROOT / "logs" / "latest_audit.json"
LAUNCHER_SCRIPT = SCRIPT_DIR / "launch_unbiased_reviewer.sh"


def get_git_info(repo_root: Path) -> tuple[str, str]:
    """Retrieve current git commit short SHA and branch name."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.SubprocessError, OSError):
        commit = "unknown"

    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.SubprocessError, OSError):
        branch = "unknown"

    return commit, branch


def calculate_scores(
    checklist: dict[str, list[dict[str, Any]]],
) -> tuple[float, float, bool, list[int], list[int]]:
    """Calculate averages and pass/fail status across Section 1 and Section 2."""
    s1_items = checklist.get("section_1_presentation_and_advisory", [])
    s2_items = checklist.get("section_2_engineering_excellence", [])

    s1_scores = [int(item["score"]) for item in s1_items if "score" in item]
    s2_scores = [int(item["score"]) for item in s2_items if "score" in item]

    avg_s1 = sum(s1_scores) / len(s1_scores) if s1_scores else 0.0
    avg_s2 = sum(s2_scores) / len(s2_scores) if s2_scores else 0.0

    passed = (
        (avg_s1 >= 2.0)
        and (avg_s2 >= 2.0)
        and (0 not in s1_scores)
        and (0 not in s2_scores)
    )

    return avg_s1, avg_s2, passed, s1_scores, s2_scores


def validate_audit_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    """Validate completeness and schema of an audit findings payload."""
    if not isinstance(payload, dict):
        return False, "Payload must be a JSON object"

    s1 = payload.get("section_1_presentation_and_advisory")
    s2 = payload.get("section_2_engineering_excellence")

    if not isinstance(s1, list) or len(s1) != 5:
        return (
            False,
            f"Section 1 must contain exactly 5 items, found {len(s1) if isinstance(s1, list) else 0}",
        )

    if not isinstance(s2, list) or len(s2) != 32:
        return (
            False,
            f"Section 2 must contain exactly 32 items, found {len(s2) if isinstance(s2, list) else 0}",
        )

    all_items = s1 + s2
    seen_ids = set()
    for idx, item in enumerate(all_items):
        if not isinstance(item, dict):
            return False, f"Item at index {idx} is not an object"
        cid = item.get("id")
        if not cid:
            return False, f"Item at index {idx} missing 'id'"
        if cid in seen_ids:
            return False, f"Duplicate competency ID '{cid}'"
        seen_ids.add(cid)

        score = item.get("score")
        if score not in {0, 1, 2, 3}:
            return (
                False,
                f"Item '{cid}' has invalid score '{score}' (must be 0, 1, 2, or 3)",
            )

        evidence = item.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            return False, f"Item '{cid}' has empty evidence"

        reasoning = item.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            return False, f"Item '{cid}' has empty reasoning"

    return True, "Valid"


def generate_markdown_report(
    checklist: dict[str, list[dict[str, Any]]],
    avg_s1: float,
    avg_s2: float,
    passed: bool,
    now_utc: str,
    commit: str,
) -> str:
    """Generate structured markdown report from checklist data."""
    status_str = "**PASSED**" if passed else "**ACTION REQUIRED**"

    lines = [
        "# Capstone Rubric Compliance Audit Report",
        "",
        f"- **Audit Date**: {now_utc}",
        f"- **Commit**: `{commit}`",
        f"- **Section 1 Score (Presentation & Advisory)**: **{avg_s1:.2f} / 3.00**",
        f"- **Section 2 Score (Engineering Excellence)**: **{avg_s2:.2f} / 3.00**",
        f"- **Overall Result**: {status_str}",
        "",
        "---",
        "",
        "## Detailed Competency Breakdown & Scoring Reasoning",
        "",
    ]

    lines.append("### Section 1 Presentation And Advisory\n")
    for item in checklist.get("section_1_presentation_and_advisory", []):
        lines.append(f"#### {item['id']}: {item['name']} ({item['score']}/3)")
        lines.append(
            f"- **Category**: {item.get('category', 'Presentation & Advisory Rigor')}"
        )
        lines.append(f"- **Criteria**: {item.get('criteria', '')}")
        lines.append(f"- **Evidence**: `{item.get('evidence', '')}`")
        lines.append(f"- **Scoring Reasoning**: {item.get('reasoning', '')}\n")

    lines.append("### Section 2 Engineering Excellence\n")
    for item in checklist.get("section_2_engineering_excellence", []):
        lines.append(f"#### {item['id']}: {item['name']} ({item['score']}/3)")
        lines.append(
            f"- **Category**: {item.get('category', 'Engineering Excellence')}"
        )
        lines.append(f"- **Criteria**: {item.get('criteria', '')}")
        lines.append(f"- **Evidence**: `{item.get('evidence', '')}`")
        lines.append(f"- **Scoring Reasoning**: {item.get('reasoning', '')}\n")

    return "\n".join(lines)


def update_historical_log(
    log_path: Path,
    checklist: dict[str, list[dict[str, Any]]],
    avg_s1: float,
    avg_s2: float,
    passed: bool,
    repo_root: Path,
    milestone: str = "All 37 competencies verified via Agent-Driven Rubric Audit",
) -> None:
    """Prepend entry to Timeline table and append detailed snapshot in markdown log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    commit, branch = get_git_info(repo_root)
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_tag = "**PASSED**" if passed else "**FAILED**"

    # Save structured JSON cache for instantaneous retrieval
    latest_payload = {
        "timestamp": now_utc,
        "commit": commit,
        "branch": branch,
        "section_1_avg": round(avg_s1, 2),
        "section_2_avg": round(avg_s2, 2),
        "passed": passed,
        "checklist": checklist,
    }
    try:
        LATEST_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        LATEST_AUDIT_FILE.write_text(
            json.dumps(latest_payload, indent=2), encoding="utf-8"
        )
    except OSError:
        pass

    new_timeline_row = f"| {now_utc} | `{commit}` | `{branch}` | {avg_s1:.2f} | {avg_s2:.2f} | {status_tag} | {milestone} |"
    snapshot_report = generate_markdown_report(
        checklist, avg_s1, avg_s2, passed, now_utc, commit
    )

    if not log_path.exists():
        content = (
            "# Capstone Rubric Historical Progression Log\n\n"
            "This log tracks the chronological evaluation score progression for the **Best Buy Catalog Comparison Agent** against the FDE Capstone Rubric.\n\n"
            "## Historical Progression Timeline\n\n"
            "| Timestamp (UTC) | Commit | Branch | Section 1 Avg | Section 2 Avg | Status | Milestone / Highlights |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f"{new_timeline_row}\n\n"
            "---\n\n"
            "## Historical Audit Snapshots\n\n"
            f"### Snapshot: {now_utc} (Commit: `{commit}`)\n\n"
            f"{snapshot_report}\n"
        )
        log_path.write_text(content, encoding="utf-8")
        return

    content = log_path.read_text(encoding="utf-8")

    table_pattern = r"(\| :--- \| :--- \| :--- \| :--- \| :--- \| :--- \| :--- \|\n)"
    if re.search(table_pattern, content):
        content = re.sub(
            table_pattern, r"\1" + new_timeline_row + "\n", content, count=1
        )
    else:
        content = new_timeline_row + "\n" + content

    snapshot_block = (
        f"\n\n### Snapshot: {now_utc} (Commit: `{commit}`)\n\n{snapshot_report}\n"
    )
    content += snapshot_block
    log_path.write_text(content, encoding="utf-8")


def load_latest_audit(
    log_path: Path,
) -> tuple[dict[str, list[dict[str, Any]]], float, float, bool, str, str]:
    """Load latest audit data from JSON cache or parse latest snapshot in markdown log."""
    if LATEST_AUDIT_FILE.exists():
        try:
            data = json.loads(LATEST_AUDIT_FILE.read_text(encoding="utf-8"))
            checklist = data.get("checklist", {})
            avg_s1 = float(data.get("section_1_avg", 0.0))
            avg_s2 = float(data.get("section_2_avg", 0.0))
            passed = bool(data.get("passed", False))
            commit = str(data.get("commit", "unknown"))
            timestamp = str(data.get("timestamp", ""))
            return checklist, avg_s1, avg_s2, passed, commit, timestamp
        except (json.JSONDecodeError, OSError):
            pass

    # Parse latest snapshot from markdown log if available
    if log_path.exists():
        try:
            content = log_path.read_text(encoding="utf-8")
            snapshots = list(
                re.finditer(r"### Snapshot: ([^\n]+) \(Commit: `([^`]+)`\)", content)
            )
            if snapshots:
                last_match = snapshots[-1]
                timestamp = last_match.group(1).strip()
                commit = last_match.group(2).strip()
                snapshot_text = content[last_match.start() :]

                item_pattern = re.compile(
                    r"####\s+(s[12]_\d+):\s+([^\n]+?)\s+\((\d+)/3\)\n"
                    r"(?:-\s+\*\*Category\*\*:\s+([^\n]+)\n)?"
                    r"(?:-\s+\*\*Criteria\*\*:\s+([^\n]+)\n)?"
                    r"-\s+\*\*Evidence\*\*:\s+`?([^`\n]+)`?\n"
                    r"-\s+\*\*Scoring Reasoning\*\*:\s+([^\n]+)",
                    re.MULTILINE,
                )

                s1_items: list[dict[str, Any]] = []
                s2_items: list[dict[str, Any]] = []

                for m in item_pattern.finditer(snapshot_text):
                    cid = m.group(1).strip()
                    name = m.group(2).strip()
                    score = int(m.group(3))
                    category = (m.group(4) or "").strip()
                    criteria = (m.group(5) or "").strip()
                    evidence = (m.group(6) or "").strip()
                    reasoning = (m.group(7) or "").strip()

                    item_data = {
                        "id": cid,
                        "category": category,
                        "name": name,
                        "criteria": criteria,
                        "score": score,
                        "evidence": evidence,
                        "reasoning": reasoning,
                    }
                    if cid.startswith("s1_"):
                        s1_items.append(item_data)
                    else:
                        s2_items.append(item_data)

                if len(s1_items) == 5 and len(s2_items) == 32:
                    checklist = {
                        "section_1_presentation_and_advisory": s1_items,
                        "section_2_engineering_excellence": s2_items,
                    }
                    avg_s1, avg_s2, passed, _, _ = calculate_scores(checklist)
                    try:
                        LATEST_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
                        LATEST_AUDIT_FILE.write_text(
                            json.dumps(
                                {
                                    "timestamp": timestamp,
                                    "commit": commit,
                                    "branch": "main",
                                    "section_1_avg": round(avg_s1, 2),
                                    "section_2_avg": round(avg_s2, 2),
                                    "passed": passed,
                                    "checklist": checklist,
                                },
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    except OSError:
                        pass
                    return checklist, avg_s1, avg_s2, passed, commit, timestamp
        except (OSError, UnicodeDecodeError, ValueError):
            pass

    # Fallback to empty checklist
    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        checklist = json.load(f)
    commit, _ = get_git_info(REPO_ROOT)
    return checklist, 0.0, 0.0, False, commit, "baseline"


def print_summary(
    avg_s1: float,
    avg_s2: float,
    passed: bool,
    no_zeros: bool,
    target_score: float | None = None,
    all_items: list[dict[str, Any]] | None = None,
) -> bool:
    """Print high-level scorecard summary to terminal and determine pass/fail."""
    print("\n" + "=" * 60)
    print("       FDE CAPSTONE RUBRIC AUDIT SCORECARD")
    print("=" * 60)
    print(f" Section 1 (Presentation & Advisory Rigor): {avg_s1:4.2f} / 3.00")
    print(f" Section 2 (Engineering Excellence):        {avg_s2:4.2f} / 3.00")
    print(
        f" Zero 0-Scores Standard:                    {'MET' if no_zeros else 'FAILED (Contains 0 score)'}"
    )
    print(
        f" Baseline Passing Standard (Avg >= 2.00):   {'MET' if passed else 'FAILED'}"
    )

    target_met = True
    if target_score is not None:
        target_score_f = float(target_score)
        if all_items:
            below_target = [
                item
                for item in all_items
                if float(item.get("score", 0)) < target_score_f
            ]
            if below_target:
                target_met = False
                print(
                    f" Target Score Standard (>={target_score_f:.1f}):            FAILED ({len(below_target)} below target)"
                )
                print("\n Competencies Below Target Score:")
                for item in below_target:
                    print(
                        f"   - {item.get('id', '')}: {item.get('name', '')} -> Score {item.get('score', 0)}/3"
                    )
            else:
                print(
                    f" Target Score Standard (>={target_score_f:.1f}):            MET (All competencies satisfy target)"
                )
        else:
            target_met = (avg_s1 >= target_score_f) and (avg_s2 >= target_score_f)
            print(
                f" Target Score Standard (>={target_score_f:.1f}):            {'MET' if target_met else 'FAILED'}"
            )

    print("=" * 60)
    overall_verdict = passed and target_met
    print(
        f" OVERALL VERDICT: {'PASSED (Field-Ready)' if overall_verdict else 'ACTION REQUIRED'}"
    )
    print("=" * 60 + "\n")
    return overall_verdict


def print_detailed_breakdown(checklist: dict[str, list[dict[str, Any]]]) -> None:
    """Print full itemized competency breakdown."""
    print("\n--- Detailed Competency Breakdown ---\n")
    for sec_name, items in checklist.items():
        title = sec_name.replace("_", " ").title()
        print(f"\n[ {title} ]")
        for item in items:
            print(f"  [{item.get('id')}] {item.get('name')}: {item.get('score', 0)}/3")
            print(f"    Category: {item.get('category', '')}")
            print(f"    Criteria: {item.get('criteria', '')}")
            print(f"    Evidence: {item.get('evidence', '')}")
            print(f"    Reasoning: {item.get('reasoning', '')}\n")


def generate_blank_template() -> dict[str, list[dict[str, Any]]]:
    """Generate blank/unscored audit JSON template from checklist schema."""
    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    template: dict[str, list[dict[str, Any]]] = {
        "section_1_presentation_and_advisory": [],
        "section_2_engineering_excellence": [],
    }

    for item in schema.get("section_1_presentation_and_advisory", []):
        template["section_1_presentation_and_advisory"].append(
            {
                "id": item["id"],
                "category": item.get("category", ""),
                "name": item.get("name", ""),
                "criteria": item.get("criteria", ""),
                "score": 0,
                "evidence": "",
                "reasoning": "",
            }
        )

    for item in schema.get("section_2_engineering_excellence", []):
        template["section_2_engineering_excellence"].append(
            {
                "id": item["id"],
                "category": item.get("category", ""),
                "name": item.get("name", ""),
                "criteria": item.get("criteria", ""),
                "score": 0,
                "evidence": "",
                "reasoning": "",
            }
        )

    return template


def execute_agentic_audit() -> int:
    """Execute live Agent-Driven rubric evaluation by launching the unbiased reviewer."""
    if not LAUNCHER_SCRIPT.exists():
        print(f"Error: Launcher script not found at {LAUNCHER_SCRIPT}", file=sys.stderr)
        return 1

    print("Launching independent LLM agent review pane in tmux (clean context, zero heuristic shortcuts)...")
    cmd = ["bash", str(LAUNCHER_SCRIPT), "--wait-and-close"]
    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except Exception as e:
        print(f"Error launching agentic audit: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main CLI entrypoint for Rubric Auditor."""
    parser = argparse.ArgumentParser(
        description="Deterministic FDE Capstone Rubric Audit Validator & History Recorder"
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=REPO_ROOT,
        help="Path to project repository root",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=None,
        help="Record agent audit findings JSON file into history log",
    )
    parser.add_argument(
        "--summary", action="store_true", help="Print summary scorecard of latest audit"
    )
    parser.add_argument(
        "--detailed", action="store_true", help="Print detailed competency breakdown"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify whether latest audit passes criteria and target score",
    )
    parser.add_argument(
        "--target-score",
        type=float,
        default=None,
        help="Target minimum score threshold (e.g. 3.0)",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Print historical progression timeline table",
    )
    parser.add_argument(
        "--template",
        action="store_true",
        help="Output blank checklist template JSON to stdout",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Save standalone markdown report to path",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_FILE,
        help="Path to historical progression markdown log",
    )
    parser.add_argument(
        "--run",
        "--evaluate",
        dest="run_audit",
        action="store_true",
        help="Execute fresh Agent-Driven rubric evaluation via independent LLM reviewer",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not update the historical progression log",
    )

    args = parser.parse_args()

    # Mode 1: Template Dump
    if args.template:
        template = generate_blank_template()
        output_str = json.dumps(template, indent=2)
        if args.output:
            args.output.write_text(output_str, encoding="utf-8")
            print(f"Blank audit template saved to {args.output}")
        else:
            print(output_str)
        return 0

    # Mode 2: Show History Timeline Table
    if args.history:
        if not args.log_file.exists():
            print(f"History log {args.log_file} does not exist yet.", file=sys.stderr)
            return 1
        content = args.log_file.read_text(encoding="utf-8")
        match = re.search(
            r"(## Historical Progression Timeline\n\n[\s\S]*?\n---)", content
        )
        if match:
            print(match.group(1))
        else:
            print("No timeline found in history log.")
        return 0

    # Mode 3: Record Agent Audit Findings JSON
    if args.record:
        if not args.record.exists():
            print(f"Error: Findings file {args.record} not found.", file=sys.stderr)
            return 1
        try:
            payload = json.loads(args.record.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error: Failed to parse JSON findings: {e}", file=sys.stderr)
            return 1

        valid, err = validate_audit_payload(payload)
        if not valid:
            print(f"Error: Invalid audit payload: {err}", file=sys.stderr)
            return 1

        avg_s1, avg_s2, passed, s1_scores, s2_scores = calculate_scores(payload)
        no_zeros = (0 not in s1_scores) and (0 not in s2_scores)
        all_items = payload.get(
            "section_1_presentation_and_advisory", []
        ) + payload.get("section_2_engineering_excellence", [])

        if not args.no_log:
            update_historical_log(
                args.log_file, payload, avg_s1, avg_s2, passed, args.repo_path
            )
            print(f"Successfully recorded audit snapshot to {args.log_file}")

        success = print_summary(
            avg_s1,
            avg_s2,
            passed,
            no_zeros,
            target_score=args.target_score,
            all_items=all_items,
        )

        if args.output:
            commit, _ = get_git_info(args.repo_path)
            now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            report = generate_markdown_report(
                payload, avg_s1, avg_s2, passed, now_utc, commit
            )
            args.output.write_text(report, encoding="utf-8")
            print(f"Report saved to {args.output}")

        return 0 if success else 1

    # Mode 4: Fresh Agentic Evaluation
    if args.run_audit:
        return execute_agentic_audit()

    # Mode 5: Summary / Detailed / Verify of latest audit
    checklist, avg_s1, avg_s2, passed, commit, _timestamp = load_latest_audit(
        args.log_file
    )
    avg_s1, avg_s2, passed, s1_scores, s2_scores = calculate_scores(checklist)
    no_zeros = (0 not in s1_scores) and (0 not in s2_scores)
    all_items = checklist.get(
        "section_1_presentation_and_advisory", []
    ) + checklist.get("section_2_engineering_excellence", [])

    if args.detailed:
        print_detailed_breakdown(checklist)

    success = print_summary(
        avg_s1,
        avg_s2,
        passed,
        no_zeros,
        target_score=args.target_score,
        all_items=all_items,
    )

    if args.output:
        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        report = generate_markdown_report(
            checklist, avg_s1, avg_s2, passed, now_utc, commit
        )
        args.output.write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
