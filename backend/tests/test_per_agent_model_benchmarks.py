"""Unit tests for Per-Agent Gemini 2.5 through 3.8 Benchmarks and 3-Stage Specialist Harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

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

from app.agent.multi_agent import MultiAgentCoordinator
from app.agent.orchestrator import (
    STAGE_OPTIMAL_MODELS,
    ComparisonOrchestrator,
    QueryIntentAnalysis,
    resolve_model_pair,
    resolve_stage_models,
)
from app.config import settings
from app.models.comparison import ComparisonSynthesis

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = REPO_ROOT / "backend" / "src" / "app" / "data" / "catalog_seed.json"


@pytest.fixture
def mock_bq() -> MagicMock:
    bq = MagicMock()
    rows = [
        {
            "sku": "6534606",
            "name": "Apple MacBook Air 13-inch M3",
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "rating": 4.8,
            "review_count": 120,
            "specifications": json.dumps({"ram_gb": 16, "battery_life_hours": 18.0}),
            "url": "https://www.techbuy.com/site/sku/6534606.p",
            "in_stock": True,
        },
        {
            "sku": "6543210",
            "name": "Dell XPS 13 Laptop",
            "brand": "Dell",
            "category": "Laptops",
            "price": 1299.0,
            "rating": 4.6,
            "review_count": 90,
            "specifications": json.dumps({"ram_gb": 32, "battery_life_hours": 12.0}),
            "url": "https://www.techbuy.com/site/sku/6543210.p",
            "in_stock": True,
        },
        {
            "sku": "6505727",
            "name": "Sony WH-1000XM5 Headphones",
            "brand": "Sony",
            "category": "Headphones",
            "price": 399.99,
            "rating": 4.8,
            "review_count": 300,
            "specifications": json.dumps({"battery_life_hours": 30.0}),
            "url": "https://www.techbuy.com/site/sku/6505727.p",
            "in_stock": True,
        },
        {
            "sku": "6554461",
            "name": "Bose QuietComfort Ultra Headphones",
            "brand": "Bose",
            "category": "Headphones",
            "price": 429.0,
            "rating": 4.7,
            "review_count": 210,
            "specifications": json.dumps({"battery_life_hours": 24.0}),
            "url": "https://www.techbuy.com/site/sku/6554461.p",
            "in_stock": True,
        },
    ]
    bq.query.return_value.result.return_value = rows
    return bq


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


def _patch_orchestrator_for_benchmarks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ComparisonOrchestrator,
        "classify_intent_with_llm",
        lambda self_o, q, *a, **kw: QueryIntentAnalysis(
            intent_type="COMPARISON",
            is_comparison_eligible=True,
            detected_category="Laptops" if "MacBook" in q else "Headphones",
            target_keywords=["MacBook Air", "Dell XPS"]
            if "MacBook" in q
            else ["Sony WH-1000XM5", "Bose QuietComfort Ultra"],
            reasoning="Comparison query",
        ),
    )
    monkeypatch.setattr(
        ComparisonOrchestrator,
        "_rerank_with_llm",
        lambda self_o, cands, *a, **kw: list(cands),
    )

    def _mock_synth(
        self_o: Any, prods: list[Any], matrix: Any = None, query: str = "", model: str | None = None
    ) -> ComparisonSynthesis:
        sku_str = " and ".join(f"{p.name} [SKU: {p.sku}] (${p.price:,.2f})" for p in prods)
        return ComparisonSynthesis(
            summary=f"Comparing {sku_str}: {prods[0].name} [SKU: {prods[0].sku}] is the lowest price option and leads in Battery Life.",
            recommendations=f"Best Value: {prods[0].name} [SKU: {prods[0].sku}]. Power Choice: {prods[-1].name} [SKU: {prods[-1].sku}].",
            spec_winners={"ram_gb": prods[-1].sku, "battery_life_hours": prods[0].sku},
        )

    monkeypatch.setattr(ComparisonOrchestrator, "synthesize_comparison_with_llm", _mock_synth)


def test_run_per_stage_benchmarks_three_llm_specialists(
    monkeypatch: pytest.MonkeyPatch, mock_bq: MagicMock, sample_benchmark_cases
):
    """Verify run_per_stage_benchmarks executes the 3 LLM specialist agent stages across the 9 GA models."""
    _patch_orchestrator_for_benchmarks(monkeypatch)
    res = run_per_stage_benchmarks(
        cases=sample_benchmark_cases,
        bq_client=mock_bq,
        live=False,
        log_vertex=False,
    )

    stages = res["stages"]
    assert "stage1_intent" in stages
    assert "stage2_relevance" in stages or "stage3_relevance" in stages
    assert "stage3_synthesis" in stages or "stage4_synthesis" in stages

    s1_results = stages["stage1_intent"]
    assert len(s1_results) == 9
    for entry in s1_results:
        assert entry["specialist"] == "QueryIntentSpecialist"
        assert entry["model_id"] in STAGE_MODELS
        assert entry["latency_p95_ms"] >= 0.0

    rel_results = stages.get("stage2_relevance") or stages.get("stage3_relevance")
    assert len(rel_results) == 9
    for entry in rel_results:
        assert entry["specialist"] == "RelevanceDetectorSpecialist"
        assert entry["model_id"] in STAGE_MODELS
        assert "mean_f1" in entry

    syn_results = stages.get("stage3_synthesis") or stages.get("stage4_synthesis")
    assert len(syn_results) == 9
    for entry in syn_results:
        assert entry["specialist"] == "SpecComparisonSpecialist"
        assert entry["model_id"] in STAGE_MODELS
        assert "mean_accuracy" in entry
        assert "mean_citation_faithfulness" in entry

    win = res["winning_combination"]
    assert win["stage1_intent"] in STAGE_MODELS
    assert (win.get("stage2_relevance") or win.get("stage3_relevance")) in STAGE_MODELS
    assert (win.get("stage3_synthesis") or win.get("stage4_synthesis")) in STAGE_MODELS
    assert win["total_pipeline_p95_ms"] > 0.0
    assert isinstance(win["sla_p95_3000ms_passed"], bool)


def test_generate_benchmark_markdown_structure(
    monkeypatch: pytest.MonkeyPatch, mock_bq: MagicMock, sample_benchmark_cases
):
    """Verify generate_benchmark_markdown formats the 3 specialist stages into readable tables."""
    _patch_orchestrator_for_benchmarks(monkeypatch)
    res = run_per_stage_benchmarks(
        cases=sample_benchmark_cases,
        bq_client=mock_bq,
        live=False,
        log_vertex=False,
    )

    report_mock = {
        "metadata": {
            "experiment_name": "test-experiment",
            "project_id": "test-project",
            "location": "us-central1",
            "cases_evaluated": 2,
            "mode": "live",
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
    """Verify compute_stage3_semantic_quality evaluates actual generated text across 4 content dimensions."""
    sample_items = [
        {
            "sku": "6534606",
            "name": "Apple MacBook Air 13-inch M3",
            "price": 1099.00,
            "rating": 4.8,
            "Specs": {
                "RAM": "16GB",
                "Storage": "512GB SSD",
                "Battery_Life": "18 hours",
                "Display_Type": "Liquid Retina",
            },
        },
        {
            "sku": "6543210",
            "name": "Dell XPS 13 Laptop",
            "price": 1299.00,
            "rating": 4.6,
            "Specs": {
                "RAM": "32GB",
                "Storage": "1TB SSD",
                "Battery_Life": "12 hours",
                "Display_Type": "OLED Touch",
            },
        },
    ]

    rich_summary = (
        "Comparing Apple MacBook Air 13-inch M3 [SKU: 6534606] ($1099.00, 4.8★) and "
        "Dell XPS 13 Laptop [SKU: 6543210] ($1299.00, 4.6★): Apple MacBook Air 13-inch M3 [SKU: 6534606] "
        "is the lowest price option at $1099.00 (saving $200.00) and leads in Battery Life (18 hours vs 12 hours) "
        "with a Liquid Retina display. Conversely, Dell XPS 13 Laptop [SKU: 6543210] leads in RAM (32GB vs 16GB) "
        "and Storage (1TB SSD vs 512GB SSD) with an OLED Touch display for heavier multitasking."
    )
    rich_recs = [
        {
            "best_for": "Best Value & All-Day Battery Mobility",
            "sku": "6534606",
            "product_name": "Apple MacBook Air 13-inch M3",
            "reason": (
                "Delivers 18 hours of battery life and a 4.8★ rating at $1099.00 ($200.00 less than Dell XPS 13) "
                "with 16GB RAM and 512GB SSD [SKU: 6534606]."
            ),
        },
        {
            "best_for": "Power Multitasking & High-Capacity Storage",
            "sku": "6543210",
            "product_name": "Dell XPS 13 Laptop",
            "reason": (
                "Upgrades memory to 32GB RAM and 1TB SSD storage with an OLED Touch display at $1299.00 "
                "for intensive workloads [SKU: 6543210]."
            ),
        },
    ]
    rich_coherence, rich_5pt = compute_stage3_semantic_quality(
        summary=rich_summary,
        recommendations=rich_recs,
        items=sample_items,
        query="Compare Apple MacBook Air M3 and Dell XPS 13",
    )
    assert rich_coherence >= 0.85, f"Expected rich synthesis >= 0.85, got {rich_coherence}"
    assert rich_5pt >= 4.4, f"Expected rich 5pt score >= 4.4, got {rich_5pt}"

    shallow_summary = (
        "Apple MacBook Air 13-inch M3 [SKU: 6534606] costs $1099.00 with a 4.8★ rating, while "
        "Dell XPS 13 Laptop [SKU: 6543210] costs $1299.00 with a 4.6★ rating."
    )
    shallow_recs = [
        {
            "best_for": "Budget Shoppers",
            "sku": "6534606",
            "product_name": "Apple MacBook Air 13-inch M3",
            "reason": "Lower price at $1099.00 [SKU: 6534606].",
        }
    ]
    shallow_coherence, shallow_5pt = compute_stage3_semantic_quality(
        summary=shallow_summary,
        recommendations=shallow_recs,
        items=sample_items,
        query="Compare Apple MacBook Air M3 and Dell XPS 13",
    )
    assert 0.45 <= shallow_coherence < 0.85, (
        f"Expected shallow synthesis in [0.45, 0.85), got {shallow_coherence}"
    )
    assert shallow_5pt < rich_5pt

    contradictory_summary = (
        "Dell XPS 13 Laptop [SKU: 6543210] is the cheapest and lowest price laptop at $1299.00, "
        "whereas [SKU: 9999999] is more expensive."
    )
    bad_coherence, _ = compute_stage3_semantic_quality(
        summary=contradictory_summary,
        recommendations=[],
        items=sample_items,
        query="Compare Apple MacBook Air M3 and Dell XPS 13",
    )
    assert bad_coherence < 0.50, f"Expected contradictory synthesis < 0.50, got {bad_coherence}"


def test_no_hardcoded_model_bonuses_or_lookup_tables() -> None:
    """Verify benchmark_models.py and generate_model_matrix.py contain no hardcoded score tables or model bonuses."""
    import evals.benchmark_models as bm
    import evals.generate_model_matrix as gmm

    assert not hasattr(bm, "STAGE3_SEMANTIC_SYNTHESIS_QUALITY"), (
        "STAGE3_SEMANTIC_SYNTHESIS_QUALITY static lookup table must be removed"
    )

    bm_source = Path(bm.__file__).read_text(encoding="utf-8")
    assert "pro_bonus" not in bm_source, "pro_bonus must be removed from _s3_score"
    assert 'c["model_id"] == "tiered-hybrid"' not in bm_source, (
        "Hardcoded tiered-hybrid tiebreaker must be removed from sorted_candidates"
    )

    gmm_source = Path(gmm.__file__).read_text(encoding="utf-8")
    assert "avg_input_tokens=890" not in gmm_source, (
        "Hardcoded candidate literals must be removed from generate_model_matrix.py"
    )


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


def test_multi_agent_coordinator_stage_optimal_routing(
    mock_bq: MagicMock, monkeypatch: Any
) -> None:
    """Verify MultiAgentCoordinator uses stage-optimal models by default and honors env var overrides."""
    # 1. Default MultiAgentCoordinator() (no arguments) uses stage-optimal models
    default_coord = MultiAgentCoordinator(bq_client=mock_bq)
    assert default_coord.use_stage_optimal_models is True
    assert default_coord.intent_agent.model == "gemini-3.5-flash-lite"
    assert default_coord.relevance_agent.model == "gemini-2.5-flash-lite"
    assert default_coord.comparison_agent.synthesis_model == "gemini-2.5-pro"

    # 2. Explicit model="stage-optimal"
    coord = MultiAgentCoordinator(bq_client=mock_bq, model="stage-optimal")
    assert coord.intent_agent.model == "gemini-3.5-flash-lite"
    assert coord.relevance_agent.model == "gemini-2.5-flash-lite"
    assert coord.comparison_agent.synthesis_model == "gemini-2.5-pro"

    # 3. Environment variable overrides (README / Rollback Playbook)
    monkeypatch.setenv("STAGE1_INTENT_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("STAGE2_RELEVANCE_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("STAGE3_SYNTHESIS_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.setenv("STAGE4_MATRIX_WINNERS_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    env_resolved = resolve_stage_models()
    assert env_resolved["stage1_intent"] == "gemini-2.5-flash"
    assert env_resolved["stage2_relevance"] == "gemini-3.5-flash-lite"
    assert env_resolved["stage3_synthesis"] == "gemini-2.5-flash-lite"
    assert env_resolved["stage4_matrix_winners"] == "gemini-2.5-flash-lite"
    assert env_resolved["stage5_chat"] == "gemini-2.5-flash-lite"

    env_coord = MultiAgentCoordinator(bq_client=mock_bq)
    assert env_coord.intent_agent.model == "gemini-2.5-flash"
    assert env_coord.relevance_agent.model == "gemini-3.5-flash-lite"
    assert env_coord.comparison_agent.synthesis_model == "gemini-2.5-flash-lite"
