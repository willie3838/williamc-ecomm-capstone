"""Unit tests for Per-Agent Gemini 2.5 through 3.8 Benchmarks and 3-Stage Specialist Harness."""

from __future__ import annotations

from pathlib import Path

import pytest
from evals.benchmark_models import (
    CANDIDATE_MODELS,
    MODEL_PRICING_DEFAULTS,
    STAGE_MODELS,
    compute_stage3_semantic_quality,
    generate_benchmark_markdown,
    run_per_stage_benchmarks,
)
from evals.generate_model_matrix import (
    ModelDecisionMatrixReport,
    build_model_decision_matrix,
)
from evals.runner import create_hermetic_bq_client

from app.agent.multi_agent import MultiAgentCoordinator
from app.agent.orchestrator import (
    STAGE_OPTIMAL_MODELS,
    resolve_model_pair,
    resolve_stage_models,
)
from app.config import settings

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
    """Verify STAGE_MODELS contains ONLY the 9 production-safe GA Gemini 2.5-3.8 models, excluding all -preview models."""
    expected_models = [
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-2.5-pro",
    ]
    assert len(STAGE_MODELS) == 9, (
        f"Expected exactly 9 GA models, got {len(STAGE_MODELS)}: {STAGE_MODELS}"
    )
    for model_id in expected_models:
        assert model_id in STAGE_MODELS
        assert not model_id.endswith("-preview"), f"Model {model_id} must not be a preview model"
        assert model_id in MODEL_PRICING_DEFAULTS
        in_cost, out_cost = MODEL_PRICING_DEFAULTS[model_id]
        assert in_cost > 0.0
        assert out_cost > 0.0

    # Ensure no preview models exist in STAGE_MODELS
    for m in STAGE_MODELS:
        assert "-preview" not in m, f"Found preview model in STAGE_MODELS: {m}"


def test_candidate_models_fleet():
    """Verify CANDIDATE_MODELS contains the 9 GA models + tiered-hybrid + gemini-1.5-flash baseline, with zero previews."""
    expected_candidates = {
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-2.5-pro",
        "tiered-hybrid",
        "gemini-1.5-flash",
    }
    candidate_ids = {c.model_id for c in CANDIDATE_MODELS}
    assert candidate_ids == expected_candidates, (
        f"Mismatch in candidate IDs: {candidate_ids ^ expected_candidates}"
    )
    for cid in candidate_ids:
        assert "-preview" not in cid, f"Candidate {cid} must not be a preview model"


def test_run_per_stage_benchmarks_three_llm_specialists(hermetic_bq, sample_benchmark_cases):
    """Verify run_per_stage_benchmarks executes the 3 LLM specialist agent stages across the 9 GA models."""
    res = run_per_stage_benchmarks(
        cases=sample_benchmark_cases,
        bq_client=hermetic_bq,
        live=False,
        log_vertex=False,
    )

    stages = res["stages"]
    # 3 specialist LLM stages
    assert "stage1_intent" in stages
    assert "stage2_relevance" in stages or "stage3_relevance" in stages
    assert "stage3_synthesis" in stages or "stage4_synthesis" in stages

    # Check Stage 1 QueryIntentSpecialist
    s1_results = stages["stage1_intent"]
    assert len(s1_results) == 9
    for entry in s1_results:
        assert entry["specialist"] == "QueryIntentSpecialist"
        assert entry["model_id"] in STAGE_MODELS
        assert entry["latency_p95_ms"] >= 0.0

    # Check RelevanceDetectorSpecialist
    rel_results = stages.get("stage2_relevance") or stages.get("stage3_relevance")
    assert len(rel_results) == 9
    for entry in rel_results:
        assert entry["specialist"] == "RelevanceDetectorSpecialist"
        assert entry["model_id"] in STAGE_MODELS
        assert "mean_f1" in entry

    # Check SpecComparisonSpecialist
    syn_results = stages.get("stage3_synthesis") or stages.get("stage4_synthesis")
    assert len(syn_results) == 9
    for entry in syn_results:
        assert entry["specialist"] == "SpecComparisonSpecialist"
        assert entry["model_id"] in STAGE_MODELS
        assert "mean_accuracy" in entry
        assert "mean_citation_faithfulness" in entry

    # Check winning combination is dynamically computed
    win = res["winning_combination"]
    assert win["stage1_intent"] in STAGE_MODELS
    assert (win.get("stage2_relevance") or win.get("stage3_relevance")) in STAGE_MODELS
    assert (win.get("stage3_synthesis") or win.get("stage4_synthesis")) in STAGE_MODELS
    assert win["total_pipeline_p95_ms"] > 0.0
    assert isinstance(win["sla_p95_3000ms_passed"], bool)


def test_generate_benchmark_markdown_structure(hermetic_bq, sample_benchmark_cases):
    """Verify generate_benchmark_markdown formats the 3 specialist stages into readable tables."""
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
                "routing_model": "gemini-3.5-flash",
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
    assert "Stage 1: QueryIntentSpecialist" in md
    assert "RelevanceDetectorSpecialist" in md
    assert "SpecComparisonSpecialist" in md
    assert "Summed Pipeline Latency & Strict SLA Verification" in md


def test_build_model_decision_matrix_eleven_models(tmp_path):
    """Verify build_model_decision_matrix covers all 9 GA models + tiered-hybrid + gemini-1.5-flash."""
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
    expected_all = {
        "tiered-hybrid",
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
    }
    assert candidate_ids == expected_all, (
        f"Mismatch in candidate IDs: {candidate_ids ^ expected_all}"
    )

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
    assert report is not None


def test_stage3_semantic_synthesis_quality_scores() -> None:
    """Verify compute_stage3_semantic_quality returns exact 0.0-1.0 and 1.0-5.0 normalized scores."""
    expected_scores = {
        "gemini-2.5-pro": (0.9760, 4.88),
        "gemini-3.8-flash": (0.9160, 4.58),
        "gemini-3.7-flash": (0.9100, 4.55),
        "gemini-3.6-flash": (0.9040, 4.52),
        "gemini-3.5-flash": (0.8960, 4.48),
        "gemini-2.5-flash": (0.8700, 4.35),
        "gemini-3.5-flash-lite": (0.8440, 4.22),
        "gemini-3.1-flash-lite": (0.8360, 4.18),
        "gemini-2.5-flash-lite": (0.8200, 4.10),
    }
    for model_id, (expected_coherence, expected_5pt) in expected_scores.items():
        coherence, score_5pt = compute_stage3_semantic_quality(model_id)
        assert coherence == expected_coherence, f"{model_id} coherence mismatch"
        assert score_5pt == expected_5pt, f"{model_id} 5pt score mismatch"


def test_run_per_stage_benchmarks_stage3_semantic_quality(
    hermetic_bq, sample_benchmark_cases
) -> None:
    """Verify run_per_stage_benchmarks includes semantic coherence and records winners."""
    res = run_per_stage_benchmarks(
        cases=sample_benchmark_cases,
        bq_client=hermetic_bq,
        live=False,
        log_vertex=False,
    )
    stages = res["stages"]
    syn_results = stages.get("stage3_synthesis")
    assert syn_results is not None
    assert len(syn_results) == 9

    for entry in syn_results:
        assert "mean_semantic_coherence" in entry
        assert "synthesis_quality_5pt" in entry
        assert 0.0 <= entry["mean_semantic_coherence"] <= 1.0
        assert 1.0 <= entry["synthesis_quality_5pt"] <= 5.0

    win = res["winning_combination"]
    assert win.get("stage3_synthesis_quality_winner") == "gemini-2.5-pro"
    assert win.get("stage3_synthesis_latency_winner") == "gemini-2.5-flash-lite"


def test_per_stage_optimal_models_configuration() -> None:
    """Verify settings and orchestrator expose per-stage optimal models."""
    assert settings.stage1_intent_model == "gemini-3.5-flash-lite"
    assert settings.stage2_relevance_model == "gemini-2.5-flash-lite"
    assert settings.stage3_synthesis_model == "gemini-2.5-pro"
    assert settings.stage3_fast_synthesis_model == "gemini-2.5-flash-lite"

    assert STAGE_OPTIMAL_MODELS["stage1_intent"] == "gemini-3.5-flash-lite"
    assert STAGE_OPTIMAL_MODELS["stage2_relevance"] == "gemini-2.5-flash-lite"
    assert STAGE_OPTIMAL_MODELS["stage3_synthesis"] == "gemini-2.5-pro"
    assert STAGE_OPTIMAL_MODELS["stage3_fast_synthesis"] == "gemini-2.5-flash-lite"

    resolved_default = resolve_stage_models(fast_synthesis=False)
    assert resolved_default["stage1_intent"] == "gemini-3.5-flash-lite"
    assert resolved_default["stage2_relevance"] == "gemini-2.5-flash-lite"
    assert resolved_default["stage3_synthesis"] == "gemini-2.5-pro"

    resolved_fast = resolve_stage_models(fast_synthesis=True)
    assert resolved_fast["stage3_synthesis"] == "gemini-2.5-flash-lite"

    routing, syn, is_hybrid = resolve_model_pair("stage-optimal", None)
    assert routing == "gemini-3.5-flash-lite"
    assert syn == "gemini-2.5-pro"
    assert is_hybrid is True


def test_multi_agent_coordinator_stage_optimal_routing(hermetic_bq) -> None:
    """Verify MultiAgentCoordinator supports stage-optimal routing across specialists."""
    coord = MultiAgentCoordinator(bq_client=hermetic_bq, model="stage-optimal")
    assert coord.intent_agent.model == "gemini-3.5-flash-lite"
    assert coord.relevance_agent.model == "gemini-2.5-flash-lite"
    assert coord.comparison_agent.synthesis_model == "gemini-2.5-pro"
