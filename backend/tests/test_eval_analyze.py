"""Unit tests for evals.analyze regression detection and reporting."""

from pathlib import Path

import pytest

from evals.analyze import compare_reports, format_delta, generate_markdown_report, load_report


def test_format_delta():
    """Verify delta formatting and directional color indicators."""
    # Zero delta
    assert "= 0.0000" in format_delta(0.0)
    assert "= 0.00%" in format_delta(0.0, is_percentage=True)

    # Positive improvement (accuracy higher is better)
    assert "🟢" in format_delta(0.05, higher_is_better=True)
    assert "+0.0500" in format_delta(0.05, higher_is_better=True)

    # Negative drop (accuracy lower is worse)
    assert "🔴" in format_delta(-0.02, higher_is_better=True)
    assert "-0.0200" in format_delta(-0.02, higher_is_better=True)

    # Latency (lower is better: negative delta is improvement)
    assert "🟢" in format_delta(-0.15, is_percentage=True, higher_is_better=False)
    assert "🔴" in format_delta(0.25, is_percentage=True, higher_is_better=False)


def test_compare_reports_no_regression():
    """Verify comparison when current run meets or exceeds baseline."""
    base_report = {
        "summary": {
            "mean_data_accuracy": 0.98,
            "mean_citation_faithfulness": 0.95,
            "latency_p95_seconds": 1.5,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
            "targets": {
                "target_accuracy": 0.98,
                "target_citation": 0.95,
                "target_latency_p95": 3.0,
                "target_schema_validity": 1.0,
            },
        },
        "details": [
            {"id": "case-1", "status": "PASS", "data_accuracy": 0.98, "citation_faithfulness": 0.95}
        ],
    }
    curr_report = {
        "summary": {
            "mean_data_accuracy": 0.99,
            "mean_citation_faithfulness": 0.96,
            "latency_p95_seconds": 1.4,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
            "targets": {
                "target_accuracy": 0.98,
                "target_citation": 0.95,
                "target_latency_p95": 3.0,
                "target_schema_validity": 1.0,
            },
        },
        "details": [
            {"id": "case-1", "status": "PASS", "data_accuracy": 0.99, "citation_faithfulness": 0.96}
        ],
    }

    res = compare_reports(curr_report, base_report)
    assert res["verdict"] == "PASSED"
    assert res["regressions_detected"] is False
    assert len(res["regression_details"]) == 0


def test_compare_reports_accuracy_regression():
    """Verify detection when data accuracy regresses beyond tolerance."""
    base_report = {
        "summary": {
            "mean_data_accuracy": 0.99,
            "mean_citation_faithfulness": 0.95,
            "latency_p95_seconds": 1.0,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
        },
        "details": [
            {"id": "case-1", "status": "PASS", "data_accuracy": 0.99, "citation_faithfulness": 0.95}
        ],
    }
    curr_report = {
        "summary": {
            "mean_data_accuracy": 0.90,  # Big drop
            "mean_citation_faithfulness": 0.95,
            "latency_p95_seconds": 1.0,
            "structured_output_validity": 1.0,
            "target_threshold_met": False,
        },
        "details": [
            {"id": "case-1", "status": "PASS", "data_accuracy": 0.90, "citation_faithfulness": 0.95}
        ],
    }

    res = compare_reports(curr_report, base_report, accuracy_tolerance=0.01)
    assert res["verdict"] == "REGRESSION_DETECTED"
    assert res["regressions_detected"] is True
    assert any("Data Accuracy" in r["metric"] for r in res["regression_details"])


def test_compare_reports_case_flip_regression():
    """Verify detection when individual test case flips from PASS to FAIL."""
    base_report = {
        "summary": {
            "mean_data_accuracy": 0.98,
            "mean_citation_faithfulness": 0.95,
            "latency_p95_seconds": 1.0,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
        },
        "details": [
            {"id": "case-1", "status": "PASS", "data_accuracy": 0.98, "citation_faithfulness": 0.95}
        ],
    }
    curr_report = {
        "summary": {
            "mean_data_accuracy": 0.98,
            "mean_citation_faithfulness": 0.95,
            "latency_p95_seconds": 1.0,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
        },
        "details": [
            {
                "id": "case-1",
                "status": "FAIL",
                "data_accuracy": 0.98,
                "citation_faithfulness": 0.95,
                "errors": ["Sample Error"],
            }
        ],
    }

    res = compare_reports(curr_report, base_report)
    assert res["regressions_detected"] is True
    assert len(res["case_regressions"]) >= 1
    assert "case-1" in res["case_regressions"][0]


def test_generate_markdown_report():
    """Verify markdown output formatting."""
    comparison = {
        "summary": {
            "data_accuracy": {"current": 0.99, "baseline": 0.98, "delta": 0.01, "target": 0.98},
            "citation_faithfulness": {
                "current": 0.96,
                "baseline": 0.95,
                "delta": 0.01,
                "target": 0.95,
            },
            "latency_p95_seconds": {
                "current": 1.2,
                "baseline": 1.5,
                "delta": -0.3,
                "delta_pct": -20.0,
                "target": 3.0,
            },
            "structured_output_validity": {
                "current": 1.0,
                "baseline": 1.0,
                "delta": 0.0,
                "target": 1.0,
            },
        },
        "category_metrics": {
            "Laptops": {
                "current_accuracy": 1.0,
                "accuracy_delta": 0.0,
                "current_citation": 1.0,
                "citation_delta": 0.0,
                "pass_rate": 1.0,
                "latency_seconds": 0.01,
            }
        },
        "verdict": "PASSED",
        "regressions_detected": False,
        "regression_details": [],
        "case_regressions": [],
    }

    md = generate_markdown_report(comparison)
    assert "# Evaluation Flywheel Analysis Report" in md
    assert "PASSED" in md
    assert "Data Accuracy" in md
    assert "Laptops" in md
    assert "No regressions detected" in md


def test_compare_reports_tool_trajectory_regression():
    """Verify regression detection when tool trajectory score drops beyond tolerance."""
    base_report = {
        "summary": {
            "mean_data_accuracy": 0.99,
            "mean_citation_faithfulness": 0.95,
            "mean_tool_trajectory_score": 1.0,
            "latency_p95_seconds": 1.0,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
        },
        "details": [{"id": "case-1", "status": "PASS", "tool_trajectory_score": 1.0}],
    }
    curr_report = {
        "summary": {
            "mean_data_accuracy": 0.99,
            "mean_citation_faithfulness": 0.95,
            "mean_tool_trajectory_score": 0.80,  # 20% drop
            "latency_p95_seconds": 1.0,
            "structured_output_validity": 1.0,
            "target_threshold_met": False,
        },
        "details": [{"id": "case-1", "status": "PASS", "tool_trajectory_score": 0.80}],
    }

    res = compare_reports(curr_report, base_report, trajectory_tolerance=0.05)
    assert res["regressions_detected"] is True
    assert any("Tool Trajectory Quality" in r["metric"] for r in res["regression_details"])


def test_generate_markdown_report_with_tool_trajectory():
    """Verify markdown output formats tool trajectory in summary table and category matrix."""
    comparison = {
        "summary": {
            "data_accuracy": {"current": 0.99, "baseline": 0.98, "delta": 0.01, "target": 0.98},
            "citation_faithfulness": {
                "current": 0.96,
                "baseline": 0.95,
                "delta": 0.01,
                "target": 0.95,
            },
            "tool_trajectory": {
                "current": 1.0,
                "baseline": 1.0,
                "delta": 0.0,
                "target": 1.0,
            },
            "latency_p95_seconds": {
                "current": 1.2,
                "baseline": 1.5,
                "delta": -0.3,
                "delta_pct": -20.0,
                "target": 3.0,
            },
            "structured_output_validity": {
                "current": 1.0,
                "baseline": 1.0,
                "delta": 0.0,
                "target": 1.0,
            },
        },
        "category_metrics": {
            "Laptops": {
                "current_accuracy": 1.0,
                "accuracy_delta": 0.0,
                "current_citation": 1.0,
                "citation_delta": 0.0,
                "current_trajectory": 1.0,
                "trajectory_delta": 0.0,
                "pass_rate": 1.0,
                "latency_seconds": 0.01,
            }
        },
        "verdict": "PASSED",
        "regressions_detected": False,
        "regression_details": [],
        "case_regressions": [],
    }

    md = generate_markdown_report(comparison)
    assert "Tool Trajectory Quality" in md
    assert "Tool Trajectory" in md
    assert "PASSED" in md


def test_load_report_file_not_found():
    """Verify FileNotFoundError on nonexistent report file."""
    with pytest.raises(FileNotFoundError):
        load_report(Path("/nonexistent/report.json"))


def test_compare_reports_latency_within_target_no_regression():
    """Verify P95 latency within target_latency_p95 (<= 3.0s) does not trigger false regression against offline mock baseline."""
    base_report = {
        "summary": {
            "mean_data_accuracy": 1.0,
            "mean_citation_faithfulness": 1.0,
            "latency_p95_seconds": 0.0469,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
            "targets": {"target_latency_p95": 3.0},
        },
        "details": [],
    }
    curr_report = {
        "summary": {
            "mean_data_accuracy": 1.0,
            "mean_citation_faithfulness": 1.0,
            "latency_p95_seconds": 2.6859,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
            "targets": {"target_latency_p95": 3.0},
        },
        "details": [],
    }
    res = compare_reports(curr_report, base_report)
    assert res["verdict"] == "PASSED"
    assert res["regressions_detected"] is False


def test_compare_reports_latency_exceeds_target_regression():
    """Verify P95 latency exceeding both target_latency_p95 and tolerance triggers regression."""
    base_report = {
        "summary": {
            "mean_data_accuracy": 1.0,
            "mean_citation_faithfulness": 1.0,
            "latency_p95_seconds": 2.5,
            "structured_output_validity": 1.0,
            "target_threshold_met": True,
            "targets": {"target_latency_p95": 3.0},
        },
        "details": [],
    }
    curr_report = {
        "summary": {
            "mean_data_accuracy": 1.0,
            "mean_citation_faithfulness": 1.0,
            "latency_p95_seconds": 3.5,
            "structured_output_validity": 1.0,
            "target_threshold_met": False,
            "targets": {"target_latency_p95": 3.0},
        },
        "details": [],
    }
    res = compare_reports(curr_report, base_report, latency_tolerance_pct=10.0)
    assert res["regressions_detected"] is True
    assert any("P95 Latency" in r["metric"] for r in res["regression_details"])
