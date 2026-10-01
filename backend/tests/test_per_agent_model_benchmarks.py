"""Unit tests for Per-Agent Gemini 2.5 through 3.8 Benchmarks and 4-Stage Specialist Harness."""

from __future__ import annotations

from pathlib import Path

import pytest
from evals.benchmark_models import (
    CANDIDATE_MODELS,
    MODEL_PRICING_DEFAULTS,
    STAGE_MODELS,
    generate_benchmark_markdown,
    run_per_stage_benchmarks,
)
from evals.generate_model_matrix import (
    ModelDecisionMatrixReport,
    build_model_decision_matrix,
)
from evals.runner import create_hermetic_bq_client

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = REPO_ROOT / "backend" / "src" / "app" / "data" / "catalog_seed.json"


@pytest.fixture
def hermetic_bq():
    return create_hermetic_bq_client(str(CATALOG_PATH))


@pytest.fixture
def sample_benchmark_cases():
    return [
        {
            "id": "case_1",
            "category": "Laptops",
            "query": "Compare Apple MacBook Air M3 and Dell XPS 13",
            "expected_skus": ["6534606", "6543210"],
            "ground_truth_specs": {
                "6534606": {"ram_gb": 16, "battery_life_hours": 18.0},
                "6543210": {"ram_gb": 32, "battery_life_hours": 12.0},
            },
        },
        {
            "id": "case_2",
            "category": "Headphones",
            "query": "Compare Sony WH-1000XM5 and Bose QuietComfort Ultra",
            "expected_skus": ["6505727", "6554461"],
            "ground_truth_specs": {
                "6505727": {"battery_life_hours": 30.0},
                "6554461": {"battery_life_hours": 24.0},
            },
        },
    ]


def test_stage_models_coverage_and_pricing():
    """Verify STAGE_MODELS and MODEL_PRICING_DEFAULTS contain all 13 target Gemini 2.5-3.8 models."""
    expected_models = [
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-2.5-pro",
        "gemini-3-pro-preview",
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview-customtools",
    ]
    for model_id in expected_models:
        assert model_id in STAGE_MODELS
        assert model_id in MODEL_PRICING_DEFAULTS
        in_cost, out_cost = MODEL_PRICING_DEFAULTS[model_id]
        assert in_cost > 0.0
        assert out_cost > 0.0

    # Ensure CandidateModelSpec list also contains all 13 models
    candidate_ids = {c.model_id for c in CANDIDATE_MODELS}
    for model_id in expected_models:
        assert model_id in candidate_ids


def test_run_per_stage_benchmarks_all_4_specialists(hermetic_bq, sample_benchmark_cases):
    """Verify run_per_stage_benchmarks executes all 4 specialist agent stages without clamping."""
    res = run_per_stage_benchmarks(
        cases=sample_benchmark_cases,
        bq_client=hermetic_bq,
        live=False,
        log_vertex=False,
    )

    stages = res["stages"]
    # 4 specialist stages
    assert "stage1_intent" in stages
    assert "stage2_retrieval" in stages
    assert "stage3_relevance" in stages
    assert "stage4_synthesis" in stages

    # Backward compatibility aliases
    assert "stage2_rerank" in stages
    assert "stage3_synthesis" in stages

    # Check Stage 2 CatalogRetrievalSpecialist tool-calling evaluation metrics
    s2_results = stages["stage2_retrieval"]
    assert len(s2_results) == len(STAGE_MODELS)
    for entry in s2_results:
        assert entry["specialist"] == "CatalogRetrievalSpecialist"
        assert "mean_trajectory_accuracy" in entry
        assert "mean_argument_compliance" in entry
        assert "mean_sku_recall" in entry
        assert entry["latency_p50_ms"] >= 0.0
        assert entry["latency_p95_ms"] >= 0.0
        assert entry["cost_per_1k_usd"] >= 0.0

    # Check winning combination is dynamically computed
    win = res["winning_combination"]
    assert win["stage1_intent"] in STAGE_MODELS
    assert win["stage2_retrieval"] in STAGE_MODELS
    assert win["stage3_relevance"] in STAGE_MODELS
    assert win["stage4_synthesis"] in STAGE_MODELS
    assert win["total_pipeline_p95_ms"] > 0.0
    assert win["tool_call_pipeline_p95_ms"] > 0.0
    assert isinstance(win["sla_p95_3000ms_passed"], bool)


def test_generate_benchmark_markdown_structure(hermetic_bq, sample_benchmark_cases):
    """Verify generate_benchmark_markdown formats all 4 stages into readable tables."""
    res = run_per_stage_benchmarks(
        cases=sample_benchmark_cases,
        bq_client=hermetic_bq,
        live=False,
        log_vertex=False,
    )

    report_mock = {
        "metadata": {
            "experiment_name": "test-experiment",
            "project_id": "test-project",
            "location": "us-central1",
            "cases_evaluated": 2,
            "mode": "hermetic",
            "rubrics": {
                "data_accuracy": {
                    "file_name": "data_accuracy.md",
                    "target_score": 0.98,
                    "critical_threshold": 0.95,
                },
                "citation_faithfulness": {
                    "file_name": "citation_faithfulness.md",
                    "target_score": 0.95,
                    "critical_threshold": 0.90,
                },
            },
        },
        "recommended_model": "tiered-hybrid",
        "candidates": [
            {
                "model_id": "tiered-hybrid",
                "routing_model": "gemini-2.5-flash",
                "synthesis_model": "gemini-2.5-pro",
                "metrics": {
                    "mean_data_accuracy": 0.995,
                    "mean_citation_faithfulness": 0.988,
                    "latency_p50_ms": 1180.0,
                    "latency_p95_ms": 2180.0,
                    "estimated_cost_per_1k_queries_usd": 0.85,
                    "composite_utility_score": 0.92,
                },
                "architecture_notes": "Dynamic ADK routing.",
            }
        ],
        "per_stage_benchmarks": res,
    }

    md = generate_benchmark_markdown(report_mock)
    assert "2.1 Stage 1: QueryIntentSpecialist" in md
    assert "2.2 Stage 2: CatalogRetrievalSpecialist (LLM Tool Calling & Retrieval Accuracy)" in md
    assert "2.3 Stage 3: RelevanceDetectorSpecialist" in md
    assert "2.4 Stage 4: SpecComparisonSpecialist" in md
    assert "Trajectory Accuracy" in md
    assert "Argument Compliance" in md
    assert "Summed Pipeline Latency & Strict SLA Verification" in md


def test_build_model_decision_matrix_all_13_models(tmp_path):
    """Verify build_model_decision_matrix covers all 13 models + tiered-hybrid + gemini-1.5-flash."""
    json_path = tmp_path / "matrix.json"
    md_path = tmp_path / "scorecard.md"

    report = build_model_decision_matrix(
        output_json_path=json_path,
        output_md_path=md_path,
    )

    assert isinstance(report, ModelDecisionMatrixReport)
    assert report.selected_winner == "tiered-hybrid"
    assert json_path.exists()
    assert md_path.exists()

    candidate_ids = {c.model_id for c in report.candidates}
    expected_all = [
        "tiered-hybrid",
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-2.5-pro",
        "gemini-3-pro-preview",
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview-customtools",
        "gemini-1.5-flash",
    ]
    for cid in expected_all:
        assert cid in candidate_ids

    # Verify string representation
    rendered = str(report)
    assert "# Empirical Foundation Model Decision Scorecard (ADR-004)" in rendered
    assert "tiered-hybrid" in rendered
    assert "gemini-3.8-flash" in rendered


def test_build_model_decision_matrix_from_dict_report(tmp_path):
    """Verify build_model_decision_matrix accepts a dict report as its first argument."""
    dict_report = {
        "candidates": [
            {
                "model_id": "gemini-3.8-flash",
                "metrics": {
                    "mean_data_accuracy": 0.992,
                    "mean_citation_faithfulness": 0.980,
                    "latency_p50_ms": 600.0,
                    "latency_p95_ms": 1100.0,
                    "estimated_cost_per_1k_queries_usd": 0.20,
                },
            }
        ]
    }
    report = build_model_decision_matrix(
        output_json_path=dict_report,
        output_md_path=tmp_path / "scorecard2.md",
    )
    assert isinstance(report, ModelDecisionMatrixReport)
    cand_38 = next(c for c in report.candidates if c.model_id == "gemini-3.8-flash")
    assert cand_38.data_accuracy == 0.992
    assert cand_38.citation_faithfulness == 0.980
