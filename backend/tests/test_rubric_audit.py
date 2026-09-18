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
            {
                "id": f"s1_0{i}",
                "name": f"P{i}",
                "score": 3,
                "evidence": "doc.md",
                "reasoning": "Strong",
            }
            for i in range(1, 6)
        ],
        "section_2_engineering_excellence": [
            {
                "id": f"s2_{i:02d}",
                "name": f"E{i}",
                "score": 3,
                "evidence": "src.py",
                "reasoning": "Strong",
            }
            for i in range(1, 33)
        ],
    }

    report = generate_markdown_report(
        test_payload, 3.0, 3.0, True, "2026-09-17 20:00:00 UTC", "testsha"
    )
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


def test_checklist_has_expert_score_3_criteria_and_disqualifiers() -> None:
    """Verify rubric_checklist.json defines explicit Score 3 expert criteria and disqualifiers."""
    with open(CHECKLIST_PATH, encoding="utf-8") as f:
        checklist = json.load(f)

    all_items = checklist.get("section_1_presentation_and_advisory", []) + checklist.get(
        "section_2_engineering_excellence", []
    )
    assert len(all_items) == 37
    for item in all_items:
        assert "score_3_expert_criteria" in item, f"Missing score_3_expert_criteria in {item['id']}"
        assert len(item["score_3_expert_criteria"]) > 20
        assert "score_3_disqualifiers" in item, f"Missing score_3_disqualifiers in {item['id']}"
        assert isinstance(item["score_3_disqualifiers"], list)
        assert len(item["score_3_disqualifiers"]) >= 1


def test_apply_strict_expert_calibration_downgrades_inflated_scores() -> None:
    """Verify that apply_strict_expert_calibration harshly downgrades undeserved Score 3s."""
    from audit_rubric import apply_strict_expert_calibration

    inflated_payload = {
        "section_1_presentation_and_advisory": [
            {
                "id": f"s1_0{i}",
                "name": f"P{i}",
                "score": 3,
                "evidence": "SPEC.md:1-50; ARCHITECTURE.md:1-40",
                "successes": "Clear business problem and TCO model comparison.",
                "failures_and_gaps": "Assumes stable BigQuery on-demand pricing without slot reservation.",
                "reasoning": "Demonstrates deep executive framing, quantified TCO trade-offs, and persona workflows.",
            }
            for i in range(1, 6)
        ],
        "section_2_engineering_excellence": [
            {
                "id": f"s2_{i:02d}",
                "name": f"E{i}",
                "score": 3,
                # s2_01 has ONLY markdown evidence -> must be downgraded from 3!
                "evidence": "SPEC.md:10-20"
                if i == 1
                else "backend/src/app/main.py:1-50; backend/tests/test_compare_api.py:1-30",
                "successes": "Implemented endpoint and schema."
                if i != 2
                else "Good implementation.",
                # s2_02 has empty/sycophantic failures_and_gaps ("None") -> must be downgraded to 2!
                "failures_and_gaps": "None"
                if i == 2
                else "Does not handle cross-region BigQuery dataset replication failover.",
                # s2_03 cites a non-existent file -> must be downgraded!
                "reasoning": "Short"
                if i == 3
                else "Expert implementation with verified unit tests, edge-case handling, and failure mode coverage.",
            }
            for i in range(1, 33)
        ],
    }
    inflated_payload["section_2_engineering_excellence"][2]["evidence"] = (
        "non_existent_dir/fake_file.py:10-20"
    )

    calibrated, downgrades = apply_strict_expert_calibration(inflated_payload, REPO_ROOT)
    s2_map = {item["id"]: item for item in calibrated["section_2_engineering_excellence"]}

    # s2_01 (docs-only evidence for engineering competency) downgraded to <= 1
    assert s2_map["s2_01"]["score"] <= 1
    # s2_02 (claimed "None" for failures_and_gaps) downgraded from 3 to 2
    assert s2_map["s2_02"]["score"] == 2
    # s2_03 (non-existent file + shallow reasoning) downgraded from 3
    assert s2_map["s2_03"]["score"] < 3
    # s2_04 (valid code + test evidence + real failure analysis + deep reasoning) keeps 3
    assert s2_map["s2_04"]["score"] == 3
    assert len(downgrades) >= 3


def test_synthesize_panel_deliberation_adversarial_consensus(tmp_path: Path) -> None:
    """Verify multi-panelist synthesis takes adversarial min-consensus and records successes/failures."""
    from audit_rubric import synthesize_panel_deliberation

    panel_dir = tmp_path / "panel_deliberation"
    panel_dir.mkdir(parents=True, exist_ok=True)

    # Create 2 panelist payloads where Panelist 1 scores s2_01 as 3, but Panelist 2 spots a flaw and scores s2_01 as 2
    def make_panelist_payload(s2_01_score: int, gap_note: str) -> dict:
        return {
            "panelist_role": "Panelist",
            "section_1_presentation_and_advisory": [
                {
                    "id": f"s1_0{i}",
                    "name": f"P{i}",
                    "score": 2,
                    "evidence": "SPEC.md:1-30; ARCHITECTURE.md:1-30",
                    "successes": "Solid persona alignment.",
                    "failures_and_gaps": "Missing multi-year enterprise discount modeling.",
                    "reasoning": "Meets Field-Ready FDE expectations with solid TCO analysis.",
                }
                for i in range(1, 6)
            ],
            "section_2_engineering_excellence": [
                {
                    "id": f"s2_{i:02d}",
                    "name": f"E{i}",
                    "score": s2_01_score if i == 1 else 2,
                    "evidence": "backend/src/app/main.py:1-50; backend/tests/test_compare_api.py:1-40",
                    "successes": "Clean ADK agent routing and Pydantic validation.",
                    "failures_and_gaps": gap_note,
                    "reasoning": "Evaluated implementation and edge cases against production standards.",
                }
                for i in range(1, 33)
            ],
        }

    (panel_dir / "panelist_ai_ml.json").write_text(
        json.dumps(make_panelist_payload(3, "Minor latency variance under cold start.")),
        encoding="utf-8",
    )
    (panel_dir / "panelist_sec_infra.json").write_text(
        json.dumps(
            make_panelist_payload(
                2, "Missing multi-turn session state eviction under memory pressure."
            )
        ),
        encoding="utf-8",
    )
    (panel_dir / "discussion_board.md").write_text(
        "# Panel Deliberation\n- **Successes**: Grounded SKU retrieval.\n- **Failures**: Session state eviction gap in s2_01.\n",
        encoding="utf-8",
    )

    consensus = synthesize_panel_deliberation(panel_dir, REPO_ROOT)
    s2_01 = next(
        item for item in consensus["section_2_engineering_excellence"] if item["id"] == "s2_01"
    )
    # Adversarial min-consensus must adopt Score 2 (not 3) because Panelist 2 identified a flaw
    assert s2_01["score"] == 2
    assert "session state eviction" in s2_01["failures_and_gaps"]
    assert "panel_deliberation_summary" in consensus


def test_update_historical_log_does_not_poison_latest_audit_on_tmp_path(tmp_path: Path) -> None:
    """Verify that passing a custom tmp_path log_file does not overwrite logs/latest_audit.json."""
    from audit_rubric import LATEST_AUDIT_FILE

    original_bytes = LATEST_AUDIT_FILE.read_bytes() if LATEST_AUDIT_FILE.exists() else None
    try:
        dummy_payload = {
            "section_1_presentation_and_advisory": [
                {
                    "id": f"s1_0{i}",
                    "name": "Dummy",
                    "score": 1,
                    "evidence": "SPEC.md",
                    "reasoning": "Dummy",
                }
                for i in range(1, 6)
            ],
            "section_2_engineering_excellence": [
                {
                    "id": f"s2_{i:02d}",
                    "name": "Dummy",
                    "score": 1,
                    "evidence": "SPEC.md",
                    "reasoning": "Dummy",
                }
                for i in range(1, 33)
            ],
        }
        tmp_log = tmp_path / "custom_history.md"
        update_historical_log(tmp_log, dummy_payload, 1.0, 1.0, False, REPO_ROOT)
        if original_bytes is not None:
            assert LATEST_AUDIT_FILE.read_bytes() == original_bytes
    finally:
        if original_bytes is not None:
            LATEST_AUDIT_FILE.write_bytes(original_bytes)


def test_multi_pane_review_panel_configuration_and_prompts(tmp_path: Path) -> None:
    """Verify panel_prompts.json and launch_review_panel.py role prompt construction."""
    from launch_review_panel import PANEL_PROMPTS_PATH, build_role_prompt

    assert PANEL_PROMPTS_PATH.exists()
    cfg = json.loads(PANEL_PROMPTS_PATH.read_text(encoding="utf-8"))
    roles = cfg.get("roles", [])
    assert len(roles) == 4
    role_ids = [r["role_id"] for r in roles]
    assert role_ids == [
        "panel_chair",
        "panelist_ai_ml",
        "panelist_sec_infra",
        "panelist_sre_cto",
    ]

    for role in roles:
        prompt_text = build_role_prompt(role, REPO_ROOT)
        assert "MANDATORY GRADING CALIBRATION (HARSH EXPERT STANDARD)" in prompt_text
        assert "Default Working Code to Score 2 (Competent)" in prompt_text
        assert "Paper Architecture Disqualifier" in prompt_text
        assert str(role["persona"]) in prompt_text
