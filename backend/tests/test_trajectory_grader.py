"""Unit tests for the ADK Trajectory Grader and evaluation suite."""

from pathlib import Path

from evals.trajectory_grader import (
    MatchType,
    ToolCallRecord,
    TrajectoryCriterion,
    TrajectoryGrader,
    TrajectoryRecorder,
    TrajectoryResult,
)


def test_trajectory_models_initialization():
    """Verify ToolCallRecord, TrajectoryCriterion, and TrajectoryResult schemas."""
    record = ToolCallRecord(
        name="query_catalog",
        args={"keywords": ["MacBook Air", "Dell XPS 13"], "category": "Laptops"},
        call_id="call_123",
        execution_time_seconds=0.15,
    )
    assert record.name == "query_catalog"
    assert record.args["category"] == "Laptops"
    assert record.execution_time_seconds == 0.15

    crit = TrajectoryCriterion(
        threshold=1.0,
        match_type=MatchType.EXACT,
        ignore_args=False,
    )
    assert crit.threshold == 1.0
    assert crit.match_type == MatchType.EXACT
    assert crit.ignore_args is False


def test_exact_match_success():
    """Verify exact match when actual tool calls match expected tool calls identically."""
    grader = TrajectoryGrader()
    actual = [
        ToolCallRecord(
            name="query_catalog",
            args={"keywords": ["MacBook Air", "Dell XPS 13"], "category": "Laptops"},
        )
    ]
    expected = [
        ToolCallRecord(
            name="query_catalog",
            args={"keywords": ["MacBook Air", "Dell XPS 13"], "category": "Laptops"},
        )
    ]

    result: TrajectoryResult = grader.grade(
        actual=actual, expected=expected, match_type=MatchType.EXACT
    )
    assert result.passed is True
    assert result.score == 1.0
    assert result.actual_tool_count == 1
    assert result.expected_tool_count == 1
    assert len(result.diagnosis.unmatched_expected) == 0
    assert len(result.diagnosis.unexpected_calls) == 0
    assert len(result.diagnosis.parameter_mismatches) == 0


def test_exact_match_fails_on_argument_mismatch():
    """Verify exact match fails when argument values differ."""
    grader = TrajectoryGrader()
    actual = [
        ToolCallRecord(
            name="query_catalog",
            args={"keywords": ["MacBook Air"], "category": "Laptops"},
        )
    ]
    expected = [
        ToolCallRecord(
            name="query_catalog",
            args={"keywords": ["MacBook Pro", "ThinkPad"], "category": "Laptops"},
        )
    ]

    result = grader.grade(actual=actual, expected=expected, match_type=MatchType.EXACT)
    assert result.passed is False
    assert result.score < 1.0
    assert len(result.diagnosis.parameter_mismatches) > 0


def test_in_order_match_with_intermediate_exploration():
    """Verify in-order match allows extra tool calls between expected steps."""
    grader = TrajectoryGrader()
    actual = [
        ToolCallRecord(name="helper_search", args={"term": "ultrabooks"}),
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["MacBook Air"], "category": "Laptops"}
        ),
        ToolCallRecord(name="format_specs", args={}),
    ]
    expected = [
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["MacBook Air"], "category": "Laptops"}
        ),
    ]

    # Under IN_ORDER, the sequence satisfies the expected path
    result_in_order = grader.grade(actual=actual, expected=expected, match_type=MatchType.IN_ORDER)
    assert result_in_order.passed is True
    assert result_in_order.score == 1.0

    # Under EXACT with strict sequence, extra tool calls cause failure
    result_exact = grader.grade(actual=actual, expected=expected, match_type=MatchType.EXACT)
    assert result_exact.passed is False


def test_any_order_match():
    """Verify any-order match passes when expected tools are called in reverse order."""
    grader = TrajectoryGrader()
    actual = [
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["Dell XPS 13"], "category": "Laptops"}
        ),
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["MacBook Air"], "category": "Laptops"}
        ),
    ]
    expected = [
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["MacBook Air"], "category": "Laptops"}
        ),
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["Dell XPS 13"], "category": "Laptops"}
        ),
    ]

    result_any = grader.grade(actual=actual, expected=expected, match_type=MatchType.ANY_ORDER)
    assert result_any.passed is True
    assert result_any.score == 1.0

    # In strict EXACT order, reverse sequence fails
    result_exact = grader.grade(actual=actual, expected=expected, match_type=MatchType.EXACT)
    assert result_exact.passed is False


def test_fuzzy_semantic_keyword_matching():
    """Verify fuzzy semantic match passes when keywords overlap semantically (brands, models)."""
    grader = TrajectoryGrader()
    actual = [
        ToolCallRecord(
            name="query_catalog",
            args={
                "keywords": ["Apple MacBook Air 13.6-inch M3 chip", "Dell XPS 13 Core Ultra"],
                "category": "laptops",
            },
        )
    ]
    expected = [
        ToolCallRecord(
            name="query_catalog",
            args={
                "keywords": ["MacBook Air", "Dell XPS 13"],
                "category": "Laptops",
            },
        )
    ]

    result = grader.grade(actual=actual, expected=expected, match_type=MatchType.FUZZY_SEMANTIC)
    assert result.passed is True
    assert result.score >= 0.95


def test_missing_tool_call_detection():
    """Verify diagnosis captures missing tool calls when agent omits a required step."""
    grader = TrajectoryGrader()
    actual = [
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["MacBook Air"], "category": "Laptops"}
        )
    ]
    expected = [
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["MacBook Air"], "category": "Laptops"}
        ),
        ToolCallRecord(
            name="query_catalog", args={"keywords": ["Dell XPS 13"], "category": "Laptops"}
        ),
    ]

    result = grader.grade(actual=actual, expected=expected, match_type=MatchType.IN_ORDER)
    assert result.passed is False
    assert result.score < 1.0
    assert len(result.diagnosis.unmatched_expected) == 1


def test_zero_tool_calls_behavior():
    """Verify behavior when 0 tool calls are expected vs made."""
    grader = TrajectoryGrader()

    # Both empty: perfect match
    res_both_empty = grader.grade(actual=[], expected=[], match_type=MatchType.EXACT)
    assert res_both_empty.passed is True
    assert res_both_empty.score == 1.0

    # Expected empty, but agent called tools: unexpected calls
    res_spurious = grader.grade(
        actual=[ToolCallRecord(name="query_catalog", args={})],
        expected=[],
        match_type=MatchType.EXACT,
    )
    assert res_spurious.passed is False
    assert res_spurious.score == 0.0
    assert len(res_spurious.diagnosis.unexpected_calls) == 1

    # Expected tools, but agent called none: total failure
    res_missing = grader.grade(
        actual=[],
        expected=[ToolCallRecord(name="query_catalog", args={})],
        match_type=MatchType.EXACT,
    )
    assert res_missing.passed is False
    assert res_missing.score == 0.0
    assert len(res_missing.diagnosis.unmatched_expected) == 1


def test_adk_invocation_adapter_and_dict_adapter():
    """Verify adapters that parse ADK Invocation and dict eval cases into ToolCallRecords."""
    grader = TrajectoryGrader()

    sample_dict_case = {
        "eval_id": "case-01",
        "conversation": [
            {
                "intermediate_data": {
                    "tool_uses": [
                        {
                            "name": "query_catalog",
                            "args": {
                                "keywords": ["MacBook Air", "Dell XPS 13"],
                                "category": "Laptops",
                            },
                        }
                    ]
                }
            }
        ],
    }

    records = grader.extract_expected_from_eval_case(sample_dict_case)
    assert len(records) == 1
    assert records[0].name == "query_catalog"
    assert records[0].args["category"] == "Laptops"


def test_trajectory_recorder_context_manager():
    """Verify TrajectoryRecorder tracks tool executions dynamically."""
    recorder = TrajectoryRecorder()

    with recorder:
        recorder.record_call(
            name="query_catalog", args={"keywords": ["Sony WH-1000XM5"], "category": "Headphones"}
        )
        recorder.record_call(
            name="query_catalog",
            args={"keywords": ["Bose QuietComfort Ultra"], "category": "Headphones"},
        )

    records = recorder.get_records()
    assert len(records) == 2
    assert records[0].name == "query_catalog"
    assert records[0].args["category"] == "Headphones"
    assert records[1].args["keywords"] == ["Bose QuietComfort Ultra"]


def test_benchmark_dataset_evalset_trajectories_extractable():
    """Verify that all 80 benchmark queries from the canonical evalset have valid expected tool trajectories."""
    import json

    dataset_path = (
        Path(__file__).resolve().parent.parent.parent
        / "evals"
        / "dataset"
        / "benchmark_catalog.evalset.json"
    )
    assert dataset_path.exists(), f"Benchmark evalset not found at {dataset_path}"

    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    grader = TrajectoryGrader()
    cases = data.get("eval_cases", [])
    assert len(cases) == 80

    for c in cases:
        expected_records = grader.extract_expected_from_eval_case(c)
        assert len(expected_records) >= 1
        assert expected_records[0].name == "query_catalog"
        assert "keywords" in expected_records[0].args
