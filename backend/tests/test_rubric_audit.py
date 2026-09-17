"""Unit tests for the Deterministic FDE Capstone Rubric Audit Validator & Recorder."""

import json
import sys
from pathlib import Path

# Add skill script directory to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_SCRIPT_DIR = REPO_ROOT / "skills" / "rubric-audit" / "scripts"
if str(SKILL_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPT_DIR))

from audit_rubric import (  # noqa: E402
    CHECKLIST_PATH,
    DEFAULT_LOG_FILE,
    calculate_scores,
    generate_blank_template,
    generate_markdown_report,
    get_git_info,
    load_latest_audit,
    print_summary,
    update_historical_log,
    validate_audit_payload,
)


def test_checklist_schema_definition() -> None:
    """Verify that rubric_checklist.json contains all 37 competencies."""
    assert CHECKLIST_PATH.exists()
    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        checklist = json.load(f)

    s1 = checklist.get("section_1_presentation_and_advisory", [])
    s2 = checklist.get("section_2_engineering_excellence", [])

    assert len(s1) == 5
    assert len(s2) == 32
    assert len(s1) + len(s2) == 37

    # Verify ID sequencing
    s1_ids = [item["id"] for item in s1]
    assert s1_ids == [f"s1_0{i}" for i in range(1, 6)]

    s2_ids = [item["id"] for item in s2]
    assert s2_ids == [f"s2_{i:02d}" for i in range(1, 33)]


def test_generate_blank_template() -> None:
    """Verify that generate_blank_template produces an unscored 37-competency payload."""
    template = generate_blank_template()
    s1 = template.get("section_1_presentation_and_advisory", [])
    s2 = template.get("section_2_engineering_excellence", [])

    assert len(s1) == 5
    assert len(s2) == 32
    for item in s1 + s2:
        assert item["score"] == 0
        assert item["evidence"] == ""
        assert item["reasoning"] == ""


def test_calculate_scores_pass_and_fail() -> None:
    """Verify calculate_scores mathematical rules, average thresholds, and zero-score disqualification."""
    # Passing payload
    passing_payload = {
        "section_1_presentation_and_advisory": [{"score": 3}] * 5,
        "section_2_engineering_excellence": [{"score": 3}] * 32,
    }
    avg_s1, avg_s2, passed, s1_scores, s2_scores = calculate_scores(passing_payload)
    assert avg_s1 == 3.0
    assert avg_s2 == 3.0
    assert passed is True
    assert 0 not in s1_scores and 0 not in s2_scores

    # Disqualifying 0-score
    failing_zero_payload = {
        "section_1_presentation_and_advisory": [{"score": 3}] * 4 + [{"score": 0}],
        "section_2_engineering_excellence": [{"score": 3}] * 32,
    }
    avg_s1, avg_s2, passed, s1_scores, s2_scores = calculate_scores(failing_zero_payload)
    assert passed is False
    assert 0 in s1_scores

    # Below average threshold (< 2.0)
    low_score_payload = {
        "section_1_presentation_and_advisory": [{"score": 1}] * 5,
        "section_2_engineering_excellence": [{"score": 3}] * 32,
    }
    avg_s1, avg_s2, passed, _, _ = calculate_scores(low_score_payload)
    assert avg_s1 == 1.0
    assert passed is False


def test_validate_audit_payload_schema() -> None:
    """Verify that validate_audit_payload enforces schema completeness and bounds."""
    # Malformed payload
    valid, err = validate_audit_payload({"invalid": []})
    assert valid is False
    assert "Section 1" in err

    # Missing items
    short_payload = {
        "section_1_presentation_and_advisory": [{"id": "s1_01", "score": 3}],
        "section_2_engineering_excellence": [],
    }
    valid, err = validate_audit_payload(short_payload)
    assert valid is False

    # Valid payload structure
    valid_payload = {
        "section_1_presentation_and_advisory": [
            {"id": f"s1_0{i}", "score": 3, "evidence": "docs/file.md", "reasoning": "Reason"}
            for i in range(1, 6)
        ],
        "section_2_engineering_excellence": [
            {"id": f"s2_{i:02d}", "score": 3, "evidence": "src/app.py", "reasoning": "Reason"}
            for i in range(1, 33)
        ],
    }
    valid, err = validate_audit_payload(valid_payload)
    assert valid is True
    assert err == "Valid"

    # Invalid score range (e.g. 4)
    valid_payload["section_1_presentation_and_advisory"][0]["score"] = 4
    valid, err = validate_audit_payload(valid_payload)
    assert valid is False
    assert "invalid score" in err


def test_summary_and_target_score_verdict() -> None:
    """Verify that print_summary accurately evaluates target-score thresholds."""
    all_items = [
        {"id": "s1_01", "score": 3},
        {"id": "s1_02", "score": 3},
    ]
    # When all meet target 3.0
    res = print_summary(3.0, 3.0, passed=True, no_zeros=True, target_score=3.0, all_items=all_items)
    assert res is True

    # When an item is degraded to 2
    all_items[1]["score"] = 2
    res_degraded = print_summary(
        2.5, 2.5, passed=True, no_zeros=True, target_score=3.0, all_items=all_items
    )
    assert res_degraded is False


def test_generate_markdown_report_and_historical_log(tmp_path: Path) -> None:
    """Verify markdown report generation and historical progression logging."""
    test_payload = {
        "section_1_presentation_and_advisory": [
            {"id": f"s1_0{i}", "name": f"P{i}", "score": 3, "evidence": "doc.md", "reasoning": "Strong"}
            for i in range(1, 6)
        ],
        "section_2_engineering_excellence": [
            {"id": f"s2_{i:02d}", "name": f"E{i}", "score": 3, "evidence": "src.py", "reasoning": "Strong"}
            for i in range(1, 33)
        ],
    }

    report = generate_markdown_report(test_payload, 3.0, 3.0, True, "2026-09-17 20:00:00 UTC", "testsha")
    assert "# Capstone Rubric Compliance Audit Report" in report
    assert "3.00 / 3.00" in report
    assert "s1_01" in report
    assert "s2_32" in report

    # Test updating log file in tmp_path
    log_file = tmp_path / "rubric_history.md"
    update_historical_log(log_file, test_payload, 3.0, 3.0, True, REPO_ROOT)
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "## Historical Progression Timeline" in content
    assert "| 3.00 | 3.00 | **PASSED** |" in content


def test_load_latest_audit_from_log() -> None:
    """Verify that load_latest_audit successfully loads historical snapshot."""
    checklist, avg_s1, avg_s2, passed, commit, timestamp = load_latest_audit(DEFAULT_LOG_FILE)
    assert passed is True
    assert avg_s1 >= 2.0
    assert avg_s2 >= 2.0
    assert len(checklist.get("section_1_presentation_and_advisory", [])) == 5
    assert len(checklist.get("section_2_engineering_excellence", [])) == 32


def test_get_git_info() -> None:
    """Verify git info extraction returns non-empty commit and branch."""
    commit, branch = get_git_info(REPO_ROOT)
    assert len(commit) > 0
    assert len(branch) > 0
