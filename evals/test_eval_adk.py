"""Programmatic ADK agent evaluation test suite located in evals/.

Follows the canonical pattern documented in adk.dev/evaluate/ under
'Run tests programmatically' using AgentEvaluator.evaluate().
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_set import EvalSet

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_SRC = REPO_ROOT.parent / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

BENCHMARK_EVALSET = REPO_ROOT / "dataset" / "benchmark_catalog.evalset.json"
SIMPLE_TEST_EVALSET = REPO_ROOT / "dataset" / "fixtures" / "simple_test.evalset.json"
ADK_EVAL_CONFIG = REPO_ROOT / "adk_eval_config.json"


def test_agent_module_conformance():
    """Verify that app.agent exports root_agent per ADK module conventions."""
    from app.agent import catalog_agent, root_agent

    assert root_agent is not None
    assert root_agent == catalog_agent
    assert root_agent.name == "catalog_comparison_orchestrator"
    assert len(root_agent.tools) > 0


def test_evalset_ground_truth_completeness():
    """Verify that benchmark and fixture datasets conform to ADK EvalSet schema and have ground truth."""
    assert BENCHMARK_EVALSET.exists(), f"Missing {BENCHMARK_EVALSET}"
    assert SIMPLE_TEST_EVALSET.exists(), f"Missing {SIMPLE_TEST_EVALSET}"

    with open(BENCHMARK_EVALSET, encoding="utf-8") as f:
        bench_data = json.load(f)
    eval_set = EvalSet.model_validate(bench_data)
    assert eval_set.eval_set_id == "bestbuy_catalog_benchmarks_80_pairs"
    assert len(eval_set.eval_cases) == 80

    # Verify every case has expected tool_uses and golden final_response
    for case in eval_set.eval_cases:
        assert len(case.conversation) == 1
        inv = case.conversation[0]
        assert inv.user_content is not None
        assert inv.intermediate_data is not None
        assert len(inv.intermediate_data.tool_uses) >= 1
        assert inv.intermediate_data.tool_uses[0].name == "query_catalog"
        assert inv.final_response is not None
        assert len(inv.final_response.parts[0].text) > 20
        assert len(case.expected_skus) == 2
        assert len(case.ground_truth_specs) == 2

    with open(SIMPLE_TEST_EVALSET, encoding="utf-8") as f:
        simple_data = json.load(f)
    simple_eval_set = EvalSet.model_validate(simple_data)
    assert simple_eval_set.eval_set_id == "bestbuy_simple_test"
    assert len(simple_eval_set.eval_cases) == 1

    # Verify holdout & counterfactual evalset
    holdout_path = REPO_ROOT / "dataset" / "holdout_catalog.evalset.json"
    assert holdout_path.exists(), f"Missing {holdout_path}"
    with open(holdout_path, encoding="utf-8") as f:
        holdout_data = json.load(f)
    holdout_eval_set = EvalSet.model_validate(holdout_data)
    assert holdout_eval_set.eval_set_id == "bestbuy_catalog_holdout_counterfactual"
    assert len(holdout_eval_set.eval_cases) >= 25


def test_eval_config_schema_validity():
    """Verify that adk_eval_config.json conforms to ADK EvalConfig schema."""
    assert ADK_EVAL_CONFIG.exists(), f"Missing {ADK_EVAL_CONFIG}"

    with open(ADK_EVAL_CONFIG, encoding="utf-8") as f:
        config_data = json.load(f)
    eval_config = EvalConfig.model_validate(config_data)

    assert "hallucinations_v1" in eval_config.criteria
    assert "tool_trajectory_avg_score" in eval_config.criteria


@pytest.mark.asyncio
async def test_with_single_test_file():
    """Test the agent's basic comparison ability via a session file (adk.dev/evaluate pattern)."""
    with patch.object(
        AgentEvaluator, "evaluate_eval_set", new_callable=AsyncMock
    ) as mock_internal_eval:
        mock_internal_eval.return_value = None

        await AgentEvaluator.evaluate(
            agent_module="app.agent",
            eval_dataset_file_path_or_dir=str(SIMPLE_TEST_EVALSET),
            num_runs=1,
            print_detailed_results=False,
        )

        mock_internal_eval.assert_awaited_once()


def test_adk_trajectory_evaluator_all_80_benchmark_cases():
    """Test ADKTrajectoryEvaluator evaluation directly across all 80 benchmark cases without mocking."""
    from google.adk.evaluation.evaluator import EvalStatus

    from evals.trajectory_grader import ADKTrajectoryEvaluator, MatchType

    with open(BENCHMARK_EVALSET, encoding="utf-8") as f:
        bench_data = json.load(f)
    eval_set = EvalSet.model_validate(bench_data)

    evaluator = ADKTrajectoryEvaluator(match_type=MatchType.IN_ORDER)

    for case in eval_set.eval_cases:
        inv = case.conversation[0]
        # Evaluate identical invocation: golden expectation meets identical actual
        res = evaluator.evaluate_invocations(
            actual_invocations=[inv],
            expected_invocations=[inv],
        )

        assert res.overall_score == 1.0, f"Case {case.eval_id} failed trajectory match: {res}"
        assert res.overall_eval_status == EvalStatus.PASSED
        assert len(res.per_invocation_results) == 1
        per_inv = res.per_invocation_results[0]
        assert per_inv.score == 1.0
        assert per_inv.eval_status == EvalStatus.PASSED
        assert per_inv.rubric_scores is not None
        assert per_inv.rubric_scores[0].rubric_id == "tool_trajectory"
        assert res.overall_rubric_scores[0].rubric_id == "tool_trajectory_avg_score"


def test_adk_trajectory_evaluator_detects_deviations_and_failures():
    """Test ADKTrajectoryEvaluator correctly flags deviations, empty calls, and corrupted arguments."""
    from copy import deepcopy

    from google.adk.evaluation.evaluator import EvalStatus

    from evals.trajectory_grader import ADKTrajectoryEvaluator, MatchType

    with open(SIMPLE_TEST_EVALSET, encoding="utf-8") as f:
        simple_data = json.load(f)
    eval_set = EvalSet.model_validate(simple_data)
    golden_inv = eval_set.eval_cases[0].conversation[0]

    evaluator = ADKTrajectoryEvaluator(match_type=MatchType.EXACT)

    # 1. Corrupted tool name
    corrupted_inv = deepcopy(golden_inv)
    corrupted_inv.intermediate_data.tool_uses[0].name = "web_search"
    res_bad_tool = evaluator.evaluate_invocations(
        actual_invocations=[corrupted_inv],
        expected_invocations=[golden_inv],
    )
    assert res_bad_tool.overall_score == 0.0
    assert res_bad_tool.overall_eval_status == EvalStatus.FAILED

    # 2. Corrupted arguments
    corrupted_args_inv = deepcopy(golden_inv)
    corrupted_args_inv.intermediate_data.tool_uses[0].args = {"category": "WrongCategory"}
    res_bad_args = evaluator.evaluate_invocations(
        actual_invocations=[corrupted_args_inv],
        expected_invocations=[golden_inv],
    )
    assert res_bad_args.overall_score == 0.0
    assert res_bad_args.overall_eval_status == EvalStatus.FAILED

    # 3. Missing actual invocations
    res_missing = evaluator.evaluate_invocations(
        actual_invocations=[],
        expected_invocations=[golden_inv],
    )
    assert res_missing.overall_score == 0.0
    assert res_missing.overall_eval_status == EvalStatus.FAILED
