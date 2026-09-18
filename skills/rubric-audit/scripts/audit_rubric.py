#!/usr/bin/env python3
"""Deterministic FDE Capstone Rubric Audit Validator, Panel Consensus & History Recorder.

Provides schema validation, strict Expert Score-3 anti-inflation calibration,
multi-pane FDE Review Panel consensus synthesis (`--synthesize-panel`),
mathematical score computation, and chronological progression logging in
`logs/rubric_audit_history.md`.
"""

from __future__ import annotations

import argparse
import copy
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
PANEL_LAUNCHER_SCRIPT = SCRIPT_DIR / "launch_review_panel.py"

SYCOPHANTIC_GAP_PHRASES = {
    "",
    "none",
    "none.",
    "n/a",
    "no gaps",
    "no failures",
    "no issues",
    "nothing",
    "nil",
    "zero gaps",
    "none identified",
}

EXECUTABLE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".tf",
    ".hcl",
    ".yaml",
    ".yml",
    ".json",
    ".sh",
    ".sql",
    ".toml",
}


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


def extract_evidence_paths(evidence_str: str) -> list[str]:
    """Extract candidate repository file paths from an evidence string."""
    # Match tokens looking like relative paths (e.g. backend/src/app/main.py:10-50 or SPEC.md)
    raw_tokens = re.split(r"[;,\s]+", evidence_str.strip())
    paths: list[str] = []
    for token in raw_tokens:
        cleaned = token.strip("`()[]'\"")
        if not cleaned:
            continue
        # Strip :line_start-line_end suffix
        cleaned = re.sub(r":\d+(?:-\d+)?$", "", cleaned)
        if "/" in cleaned or cleaned.endswith(
            (".md", ".py", ".ts", ".tsx", ".tf", ".yaml", ".yml", ".json", ".sh", "Dockerfile")
        ):
            paths.append(cleaned)
    return paths


def apply_strict_expert_calibration(
    payload: dict[str, Any], repo_root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Enforce harsh Staff/Principal FDE calibration so Score 3 requires true expert mastery.

    Rules enforced:
    1. Verified Evidence Existence: Cited files in `evidence` must exist in `repo_root`.
       If no cited file exists on disk, score is capped at 1.
    2. Paper Architecture Disqualifier (Section 2): Any Engineering Excellence (`s2_*`)
       competency whose existing evidence files are ONLY `.md` prose without executable
       code/IaC/test files is capped at Score 1.
    3. Mandatory Failure/Gap Analysis for Score 3: If an item is scored 3, `failures_and_gaps`
       (when present) cannot be empty or sycophantic ("None", "No issues"), and `reasoning`
       must be substantive (>= 25 chars). Otherwise downgraded to 2.
    """
    calibrated = copy.deepcopy(payload)
    downgrades: list[dict[str, Any]] = []

    for section_key in (
        "section_1_presentation_and_advisory",
        "section_2_engineering_excellence",
    ):
        items = calibrated.get(section_key, [])
        is_engineering = section_key == "section_2_engineering_excellence"

        for item in items:
            cid = str(item.get("id", ""))
            orig_score = int(item.get("score", 0))
            new_score = orig_score
            reasons: list[str] = []

            evidence_str = str(item.get("evidence", ""))
            candidate_paths = extract_evidence_paths(evidence_str)
            existing_paths = [p for p in candidate_paths if (repo_root / p).exists()]

            doc_only_allowed_ids = {"s2_06", "s2_07", "s2_08", "s2_09", "s2_10", "s2_12"}
            requires_executable_code = is_engineering and (cid not in doc_only_allowed_ids)

            if not existing_paths:
                if new_score > 1:
                    new_score = 1
                    reasons.append(
                        f"Evidence path(s) {candidate_paths or [evidence_str]} not found in repository"
                    )
            elif requires_executable_code:
                has_code_or_iac = any(
                    Path(p).suffix.lower() in EXECUTABLE_EXTENSIONS or Path(p).name == "Dockerfile"
                    for p in existing_paths
                )
                if not has_code_or_iac and new_score > 1:
                    new_score = 1
                    reasons.append(
                        "Paper Architecture Disqualifier: Section 2 engineering competency cites only Markdown docs without executable code/IaC/tests"
                    )

            if new_score == 3:
                reasoning_str = str(item.get("reasoning", "")).strip()
                if len(reasoning_str) < 25:
                    new_score = 2
                    reasons.append(
                        "Shallow Reasoning Disqualifier: Score 3 (Expert) requires >= 25 chars of architectural trade-off and failure-mode analysis"
                    )

                if "failures_and_gaps" in item:
                    gaps_str = str(item.get("failures_and_gaps", "")).strip()
                    if gaps_str.lower() in SYCOPHANTIC_GAP_PHRASES or len(gaps_str) < 12:
                        new_score = 2
                        reasons.append(
                            "Sycophancy Disqualifier: Score 3 requires explicit identification of realistic edge cases, limitations, or operational risks in 'failures_and_gaps'"
                        )

            if new_score != orig_score:
                item["score"] = new_score
                penalty_note = f" [PANEL CALIBRATION DOWNGRADE {orig_score}-> {new_score}: {'; '.join(reasons)}]"
                item["reasoning"] = str(item.get("reasoning", "")) + penalty_note
                downgrades.append(
                    {
                        "id": cid,
                        "from_score": orig_score,
                        "to_score": new_score,
                        "reasons": reasons,
                    }
                )

    return calibrated, downgrades


def synthesize_panel_deliberation(panel_dir: Path, repo_root: Path) -> dict[str, Any]:
    """Synthesize multiple panelist JSON evaluations and debate transcript via Adversarial Min-Consensus."""
    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    panelist_files = sorted(panel_dir.glob("panelist_*.json"))
    panelist_payloads: list[dict[str, Any]] = []
    for pfile in panelist_files:
        try:
            panelist_payloads.append(json.loads(pfile.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue

    def merge_section(section_key: str) -> list[dict[str, Any]]:
        merged_items: list[dict[str, Any]] = []
        for schema_item in schema.get(section_key, []):
            cid = schema_item["id"]
            matches: list[dict[str, Any]] = []
            for p_payload in panelist_payloads:
                for p_item in p_payload.get(section_key, []):
                    if p_item.get("id") == cid:
                        matches.append(p_item)

            if not matches:
                merged_items.append(
                    {
                        "id": cid,
                        "category": schema_item.get("category", ""),
                        "name": schema_item.get("name", ""),
                        "criteria": schema_item.get("criteria", ""),
                        "score": 0,
                        "evidence": "Missing panelist evaluation",
                        "successes": "None recorded",
                        "failures_and_gaps": "Not evaluated by panel",
                        "reasoning": "Automatic 0 due to missing panelist evaluation.",
                    }
                )
                continue

            # Adversarial Min-Consensus: adopt the lowest/harshest score across panelists
            scores = [int(m.get("score", 0)) for m in matches]
            consensus_score = min(scores)

            evidences = list(
                dict.fromkeys(
                    str(m.get("evidence", "")).strip()
                    for m in matches
                    if str(m.get("evidence", "")).strip()
                )
            )
            successes = list(
                dict.fromkeys(
                    str(m.get("successes", "")).strip()
                    for m in matches
                    if str(m.get("successes", "")).strip()
                )
            )
            failures = list(
                dict.fromkeys(
                    str(m.get("failures_and_gaps", "")).strip()
                    for m in matches
                    if str(m.get("failures_and_gaps", "")).strip()
                    and str(m.get("failures_and_gaps", "")).strip().lower()
                    not in SYCOPHANTIC_GAP_PHRASES
                )
            )
            reasonings = list(
                dict.fromkeys(
                    str(m.get("reasoning", "")).strip()
                    for m in matches
                    if str(m.get("reasoning", "")).strip()
                )
            )

            merged_items.append(
                {
                    "id": cid,
                    "category": schema_item.get("category", ""),
                    "name": schema_item.get("name", ""),
                    "criteria": schema_item.get("criteria", ""),
                    "score": consensus_score,
                    "panelist_scores": scores,
                    "evidence": "; ".join(evidences) or "None",
                    "successes": " | ".join(successes) or "Working baseline verified.",
                    "failures_and_gaps": " | ".join(failures)
                    or (matches[0].get("failures_and_gaps", "None")),
                    "reasoning": " | ".join(reasonings),
                }
            )
        return merged_items

    raw_consensus = {
        "section_1_presentation_and_advisory": merge_section("section_1_presentation_and_advisory"),
        "section_2_engineering_excellence": merge_section("section_2_engineering_excellence"),
    }

    calibrated_consensus, downgrades = apply_strict_expert_calibration(raw_consensus, repo_root)

    board_path = panel_dir / "discussion_board.md"
    board_excerpt = (
        board_path.read_text(encoding="utf-8")[:4000]
        if board_path.exists()
        else "No discussion board transcript found."
    )

    calibrated_consensus["panel_deliberation_summary"] = {
        "panelists_participated": len(panelist_payloads),
        "panelist_files": [p.name for p in panelist_files],
        "strict_downgrades_applied": len(downgrades),
        "downgrades": downgrades,
        "discussion_board_excerpt": board_excerpt,
    }
    return calibrated_consensus


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

    passed = (avg_s1 >= 2.0) and (avg_s2 >= 2.0) and (0 not in s1_scores) and (0 not in s2_scores)

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
    checklist: dict[str, Any],
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
    ]

    panel_summary = checklist.get("panel_deliberation_summary")
    if isinstance(panel_summary, dict):
        lines.extend(
            [
                "## Multi-Pane FDE Review Panel Deliberation Summary",
                "",
                f"- **Participating Panelists**: `{panel_summary.get('panelists_participated', 0)}` (`{', '.join(panel_summary.get('panelist_files', []))}`)",
                f"- **Strict Anti-Inflation Downgrades Applied**: `{panel_summary.get('strict_downgrades_applied', 0)}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Detailed Competency Breakdown & Scoring Reasoning",
            "",
            "### Section 1 Presentation And Advisory\n",
        ]
    )
    for item in checklist.get("section_1_presentation_and_advisory", []):
        lines.append(f"#### {item['id']}: {item['name']} ({item['score']}/3)")
        lines.append(f"- **Category**: {item.get('category', 'Presentation & Advisory Rigor')}")
        lines.append(f"- **Criteria**: {item.get('criteria', '')}")
        lines.append(f"- **Evidence**: `{item.get('evidence', '')}`")
        if item.get("successes"):
            lines.append(f"- **Verified Successes**: {item.get('successes')}")
        if item.get("failures_and_gaps"):
            lines.append(f"- **Failures & Edge-Case Gaps**: {item.get('failures_and_gaps')}")
        lines.append(f"- **Scoring Reasoning**: {item.get('reasoning', '')}\n")

    lines.append("### Section 2 Engineering Excellence\n")
    for item in checklist.get("section_2_engineering_excellence", []):
        lines.append(f"#### {item['id']}: {item['name']} ({item['score']}/3)")
        lines.append(f"- **Category**: {item.get('category', 'Engineering Excellence')}")
        lines.append(f"- **Criteria**: {item.get('criteria', '')}")
        lines.append(f"- **Evidence**: `{item.get('evidence', '')}`")
        if item.get("successes"):
            lines.append(f"- **Verified Successes**: {item.get('successes')}")
        if item.get("failures_and_gaps"):
            lines.append(f"- **Failures & Edge-Case Gaps**: {item.get('failures_and_gaps')}")
        lines.append(f"- **Scoring Reasoning**: {item.get('reasoning', '')}\n")

    return "\n".join(lines)


def update_historical_log(
    log_path: Path,
    checklist: dict[str, Any],
    avg_s1: float,
    avg_s2: float,
    passed: bool,
    repo_root: Path,
    milestone: str = "All 37 competencies evaluated via Multi-Pane FDE Review Panel",
) -> None:
    """Prepend entry to Timeline table and append detailed snapshot in markdown log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    commit, branch = get_git_info(repo_root)
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_tag = "**PASSED**" if passed else "**FAILED**"

    # Only update LATEST_AUDIT_FILE when writing to the canonical DEFAULT_LOG_FILE
    # (prevents pytest tmp_path tests from poisoning logs/latest_audit.json!)
    if log_path.resolve() == DEFAULT_LOG_FILE.resolve():
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
            LATEST_AUDIT_FILE.write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")
        except OSError:
            pass

    new_timeline_row = f"| {now_utc} | `{commit}` | `{branch}` | {avg_s1:.2f} | {avg_s2:.2f} | {status_tag} | {milestone} |"
    snapshot_report = generate_markdown_report(checklist, avg_s1, avg_s2, passed, now_utc, commit)

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
        content = re.sub(table_pattern, r"\1" + new_timeline_row + "\n", content, count=1)
    else:
        content = new_timeline_row + "\n" + content

    snapshot_block = f"\n\n### Snapshot: {now_utc} (Commit: `{commit}`)\n\n{snapshot_report}\n"
    content += snapshot_block
    log_path.write_text(content, encoding="utf-8")


def load_latest_audit(
    log_path: Path,
) -> tuple[dict[str, list[dict[str, Any]]], float, float, bool, str, str]:
    """Load latest audit data from JSON cache or parse latest snapshot in markdown log."""
    if log_path.resolve() == DEFAULT_LOG_FILE.resolve() and LATEST_AUDIT_FILE.exists():
        try:
            data = json.loads(LATEST_AUDIT_FILE.read_text(encoding="utf-8"))
            checklist = data.get("checklist", {})
            # Guard against poisoned dummy test data (e.g. name == "P1" and reasoning == "Strong")
            s1 = checklist.get("section_1_presentation_and_advisory", [])
            if s1 and s1[0].get("reasoning") != "Strong":
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
            snapshots = list(re.finditer(r"### Snapshot: ([^\n]+) \(Commit: `([^`]+)`\)", content))
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
                    r"(?:-\s+\*\*Verified Successes\*\*:\s+([^\n]+)\n)?"
                    r"(?:-\s+\*\*Failures & Edge-Case Gaps\*\*:\s+([^\n]+)\n)?"
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
                    successes = (m.group(7) or "").strip()
                    failures_and_gaps = (m.group(8) or "").strip()
                    reasoning = (m.group(9) or "").strip()

                    item_data = {
                        "id": cid,
                        "category": category,
                        "name": name,
                        "criteria": criteria,
                        "score": score,
                        "evidence": evidence,
                        "successes": successes,
                        "failures_and_gaps": failures_and_gaps,
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
                    if log_path.resolve() == DEFAULT_LOG_FILE.resolve():
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
    print(f" Baseline Passing Standard (Avg >= 2.00):   {'MET' if passed else 'FAILED'}")

    target_met = True
    if target_score is not None:
        target_score_f = float(target_score)
        if all_items:
            below_target = [
                item for item in all_items if float(item.get("score", 0)) < target_score_f
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
    print(f" OVERALL VERDICT: {'PASSED (Field-Ready)' if overall_verdict else 'ACTION REQUIRED'}")
    print("=" * 60 + "\n")
    return overall_verdict


def print_detailed_breakdown(checklist: dict[str, Any]) -> None:
    """Print full itemized competency breakdown."""
    print("\n--- Detailed Competency Breakdown ---\n")
    for sec_name in (
        "section_1_presentation_and_advisory",
        "section_2_engineering_excellence",
    ):
        items = checklist.get(sec_name, [])
        title = sec_name.replace("_", " ").title()
        print(f"\n[ {title} ]")
        for item in items:
            print(f"  [{item.get('id')}] {item.get('name')}: {item.get('score', 0)}/3")
            print(f"    Category: {item.get('category', '')}")
            print(f"    Criteria: {item.get('criteria', '')}")
            print(f"    Evidence: {item.get('evidence', '')}")
            if item.get("successes"):
                print(f"    Successes: {item.get('successes')}")
            if item.get("failures_and_gaps"):
                print(f"    Failures & Gaps: {item.get('failures_and_gaps')}")
            print(f"    Reasoning: {item.get('reasoning', '')}\n")


def generate_blank_template() -> dict[str, list[dict[str, Any]]]:
    """Generate blank/unscored audit JSON template from checklist schema."""
    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    template: dict[str, list[dict[str, Any]]] = {
        "section_1_presentation_and_advisory": [],
        "section_2_engineering_excellence": [],
    }

    for section_key in (
        "section_1_presentation_and_advisory",
        "section_2_engineering_excellence",
    ):
        for item in schema.get(section_key, []):
            template[section_key].append(
                {
                    "id": item["id"],
                    "category": item.get("category", ""),
                    "name": item.get("name", ""),
                    "criteria": item.get("criteria", ""),
                    "score_3_expert_criteria": item.get("score_3_expert_criteria", ""),
                    "score_3_disqualifiers": item.get("score_3_disqualifiers", []),
                    "score": 0,
                    "evidence": "",
                    "successes": "",
                    "failures_and_gaps": "",
                    "reasoning": "",
                }
            )

    return template


def execute_agentic_audit() -> int:
    """Execute live Multi-Pane FDE Review Panel in tmux."""
    if not PANEL_LAUNCHER_SCRIPT.exists():
        print(f"Error: Panel launcher script not found at {PANEL_LAUNCHER_SCRIPT}", file=sys.stderr)
        return 1

    print(
        "Launching 4-pane Adversarial FDE Review Panel in tmux (Panel Chair + 3 Domain Panelists)..."
    )
    cmd = [sys.executable, str(PANEL_LAUNCHER_SCRIPT), "--wait-and-close"]
    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except Exception as e:
        print(f"Error launching review panel: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main CLI entrypoint for Rubric Auditor."""
    parser = argparse.ArgumentParser(
        description="Deterministic FDE Capstone Rubric Audit Validator, Panel Consensus & History Recorder"
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=REPO_ROOT,
        help="Path to project repository root",
    )
    parser.add_argument(
        "--synthesize-panel",
        type=Path,
        default=None,
        help="Synthesize multi-panelist evaluations from deliberation directory (e.g. logs/panel_deliberation)",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=None,
        help="Record agent audit findings JSON file into history log",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce strict Staff/Principal Score-3 calibration rules when recording",
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
        help="Target minimum score threshold (e.g. 2.0 or 3.0)",
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
        "--panel",
        dest="run_audit",
        action="store_true",
        help="Execute fresh Multi-Pane FDE Review Panel evaluation in tmux",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not update the historical progression log",
    )

    args = parser.parse_args()

    # Mode 0: Synthesize Panel Deliberation
    if args.synthesize_panel:
        if not args.synthesize_panel.exists():
            print(
                f"Error: Panel deliberation directory {args.synthesize_panel} not found.",
                file=sys.stderr,
            )
            return 1
        consensus = synthesize_panel_deliberation(args.synthesize_panel, args.repo_path)
        target_out = args.record or (REPO_ROOT / "logs" / "unbiased_rubric_audit.json")
        target_out.parent.mkdir(parents=True, exist_ok=True)
        target_out.write_text(json.dumps(consensus, indent=2), encoding="utf-8")
        print(f"Synthesized panel consensus saved to {target_out}")
        if not args.record:
            args.record = target_out

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
        match = re.search(r"(## Historical Progression Timeline\n\n[\s\S]*?\n---)", content)
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

        if (
            args.strict
            or args.synthesize_panel
            or any(
                "failures_and_gaps" in item
                for item in payload.get("section_2_engineering_excellence", [])
            )
        ):
            payload, downgrades = apply_strict_expert_calibration(payload, args.repo_path)
            if downgrades:
                print(
                    f"[Strict Expert Calibration] Applied {len(downgrades)} score downgrade(s) for unsubstantiated Score 3s."
                )

        avg_s1, avg_s2, passed, s1_scores, s2_scores = calculate_scores(payload)
        no_zeros = (0 not in s1_scores) and (0 not in s2_scores)
        all_items = payload.get("section_1_presentation_and_advisory", []) + payload.get(
            "section_2_engineering_excellence", []
        )

        if not args.no_log:
            update_historical_log(args.log_file, payload, avg_s1, avg_s2, passed, args.repo_path)
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
            report = generate_markdown_report(payload, avg_s1, avg_s2, passed, now_utc, commit)
            args.output.write_text(report, encoding="utf-8")
            print(f"Report saved to {args.output}")

        return 0 if success else 1

    # Mode 4: Fresh Multi-Pane Panel Evaluation
    if args.run_audit:
        return execute_agentic_audit()

    # Mode 5: Summary / Detailed / Verify of latest audit
    checklist, avg_s1, avg_s2, passed, commit, _timestamp = load_latest_audit(args.log_file)
    avg_s1, avg_s2, passed, s1_scores, s2_scores = calculate_scores(checklist)
    no_zeros = (0 not in s1_scores) and (0 not in s2_scores)
    all_items = checklist.get("section_1_presentation_and_advisory", []) + checklist.get(
        "section_2_engineering_excellence", []
    )

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
        report = generate_markdown_report(checklist, avg_s1, avg_s2, passed, now_utc, commit)
        args.output.write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
