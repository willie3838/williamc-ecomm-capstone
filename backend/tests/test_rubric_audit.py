"""Unit tests for the Universal FDE Capstone Rubric Audit Engine."""

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
    ProjectExplorer,
    UniversalRubricAuditor,
    calculate_scores,
    load_latest_audit,
    print_summary,
    validate_audit_payload,
)


def test_project_explorer_discovery() -> None:
    """Verify that ProjectExplorer dynamically indexes files across the repository."""
    explorer = ProjectExplorer(REPO_ROOT)
    assert len(explorer.python_files) > 0
    assert len(explorer.markdown_docs) > 0
    assert len(explorer.tf_files) > 0
    assert len(explorer.yaml_files) > 0
    assert len(explorer.all_files) > 10

    # Verify helper methods
    matches = explorer.search_text(explorer.markdown_docs, r"rubric", case_sensitive=False)
    assert len(matches) > 0
    assert any("RUBRIC.md" in m[0] or "AGENTS.md" in m[0] for m in matches)


def test_universal_rubric_auditor_all_competencies() -> None:
    """Verify that UniversalRubricAuditor audits all 37 competencies in checklist."""
    assert CHECKLIST_PATH.exists()
    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        checklist = json.load(f)

    explorer = ProjectExplorer(REPO_ROOT)
    auditor = UniversalRubricAuditor(explorer)
    audited = auditor.audit_all(checklist)

    s1 = audited.get("section_1_presentation_and_advisory", [])
    s2 = audited.get("section_2_engineering_excellence", [])

    assert len(s1) == 5
    assert len(s2) == 32
    assert len(s1) + len(s2) == 37

    # Every item must have valid score, non-empty evidence, and non-empty reasoning
    for item in s1 + s2:
        assert item["score"] in {0, 1, 2, 3}
        assert isinstance(item["evidence"], str) and len(item["evidence"]) > 0
        assert isinstance(item["reasoning"], str) and len(item["reasoning"]) > 0


def test_current_codebase_baseline_pass() -> None:
    """Verify that the current codebase satisfies the baseline passing standard (avg >= 2.0, no 0s)."""
    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        checklist = json.load(f)

    explorer = ProjectExplorer(REPO_ROOT)
    auditor = UniversalRubricAuditor(explorer)
    audited = auditor.audit_all(checklist)

    avg_s1, avg_s2, passed, s1_scores, s2_scores = calculate_scores(audited)

    assert passed is True
    assert 0 not in s1_scores
    assert 0 not in s2_scores
    assert avg_s1 >= 2.0
    assert avg_s2 >= 2.0


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


def test_mock_scaffold_failure_detection(tmp_path: Path) -> None:
    """Verify that the auditor detects empty/missing components on an arbitrary project."""
    dummy_repo = tmp_path / "dummy_project"
    dummy_repo.mkdir()
    (dummy_repo / "README.md").write_text("# Dummy Project\n", encoding="utf-8")

    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        checklist = json.load(f)

    explorer = ProjectExplorer(dummy_repo)
    auditor = UniversalRubricAuditor(explorer)
    audited = auditor.audit_all(checklist)

    avg_s1, avg_s2, passed, s1_scores, s2_scores = calculate_scores(audited)

    # Empty dummy project must NOT pass
    assert passed is False
    assert 0 in s2_scores  # Missing agent and retrieval triggers 0 score


def test_validate_audit_payload_schema() -> None:
    """Verify that validate_audit_payload enforces schema completeness and bounds."""
    # Malformed payload
    valid, err = validate_audit_payload({"invalid": []})
    assert valid is False
    assert "Section 1" in err

    # Valid payload structure
    valid_payload = {
        "section_1_presentation_and_advisory": [
            {"id": f"s1_0{i}", "score": 3, "evidence": "file.md", "reasoning": "Reason"}
            for i in range(1, 6)
        ],
        "section_2_engineering_excellence": [
            {"id": f"s2_{i:02d}", "score": 3, "evidence": "src.py", "reasoning": "Reason"}
            for i in range(1, 33)
        ],
    }
    valid, err = validate_audit_payload(valid_payload)
    assert valid is True
    assert err == "Valid"


def test_load_latest_audit_from_log() -> None:
    """Verify that load_latest_audit successfully loads historical snapshot."""
    checklist, avg_s1, avg_s2, passed, commit, timestamp = load_latest_audit(DEFAULT_LOG_FILE)
    assert passed is True
    assert avg_s1 >= 2.0
    assert avg_s2 >= 2.0
    assert len(checklist.get("section_1_presentation_and_advisory", [])) == 5
    assert len(checklist.get("section_2_engineering_excellence", [])) == 32
