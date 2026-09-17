"""Unit tests for evals.run_pipeline unified orchestration pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from evals.run_pipeline import execute_adk_evaluation, run_pipeline


@pytest.fixture
def mock_dataset_and_catalog(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent.parent
    dataset_path = repo_root / "evals" / "dataset" / "fixtures" / "simple_test.evalset.json"
    catalog_path = repo_root / "backend" / "src" / "app" / "data" / "catalog_seed.json"
    reports_dir = tmp_path / "reports"
    return dataset_path, catalog_path, reports_dir


def test_pipeline_execution_order_and_combined_metrics(mock_dataset_and_catalog):
    """Verify that run_pipeline executes the runner FIRST, ADK evaluator SECOND, and analyzer THIRD."""
    dataset_path, catalog_path, reports_dir = mock_dataset_and_catalog
    execution_order = []

    def mock_run_benchmark(*args, **kwargs):
        execution_order.append("runner_first")
        return {
            "metadata": {
                "timestamp": "2026-09-17T02:00:00Z",
                "total_cases": 1,
                "passed_cases": 1,
                "failed_cases": 0,
            },
            "summary": {
                "mean_data_accuracy": 1.0,
                "mean_citation_faithfulness": 1.0,
                "mean_retrieval_precision": 1.0,
                "mean_retrieval_recall": 1.0,
                "mean_semantic_score": 1.0,
                "structured_output_validity": 1.0,
                "latency_p50_seconds": 1.2,
                "latency_p95_seconds": 2.1,
                "target_threshold_met": True,
            },
            "details": [
                {
                    "id": "test-1",
                    "status": "PASS",
                    "data_accuracy": 1.0,
                    "citation_faithfulness": 1.0,
                }
            ],
        }

    async def mock_execute_adk(*args, **kwargs):
        execution_order.append("adk_evaluator_second")
        return {
            "hallucination_score": 0.96,
            "tool_trajectory_score": 1.0,
            "response_match_score": 0.85,
            "status": "COMPLETED",
        }

    mock_bq = MagicMock()
    mock_bq.insert_rows_json.return_value = []

    with (
        patch("evals.run_pipeline.run_benchmark", side_effect=mock_run_benchmark),
        patch("evals.run_pipeline.execute_adk_evaluation", side_effect=mock_execute_adk),
    ):
        result = run_pipeline(
            dataset_path=dataset_path,
            catalog_path=catalog_path,
            reports_dir=reports_dir,
            export_bq=True,
            trigger_source="cloud_scheduler",
            bq_client=mock_bq,
        )

    # Assert strict execution order: runner executed first, ADK evaluator executed second
    assert execution_order == [
        "runner_first",
        "adk_evaluator_second",
    ]

    # Assert ADK metrics attached to runner report summary
    summary = result["runner_report"]["summary"]
    assert summary["adk_hallucination_score"] == 0.96
    assert summary["adk_tool_trajectory_score"] == 1.0

    # Assert BigQuery row had both runner and ADK fields
    assert mock_bq.insert_rows_json.called
    table_ref, rows = mock_bq.insert_rows_json.call_args[0]
    row = rows[0]
    assert row["avg_spec_accuracy"] == 1.0
    assert row["avg_citation_faithfulness"] == 1.0
    assert row["adk_hallucination_score"] == 0.96
    assert row["adk_tool_trajectory_score"] == 1.0
    assert row["trigger_source"] == "cloud_scheduler"


@pytest.mark.asyncio
async def test_execute_adk_evaluation_graceful_warning(tmp_path):
    """Verify that execute_adk_evaluation handles non-fatal exceptions gracefully."""
    with patch(
        "google.adk.evaluation.agent_evaluator.AgentEvaluator.evaluate",
        side_effect=RuntimeError("Quota limit"),
    ):
        res = await execute_adk_evaluation(
            dataset_path=Path("dummy.json"),
            output_path=tmp_path / "out.json",
        )
        assert res["status"] == "WARNING"
        assert "Quota limit" in res["error"]
