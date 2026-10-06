"""Unit tests for model execution, ThinkingConfig, Model Armor region routing, and benchmark scoring."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from evals.benchmark_models import (
    STAGE_MODELS,
    compute_stage3_semantic_quality,
    run_per_stage_benchmarks,
)
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from app.agent import adk_llm as ha
from app.agent import orchestrator as orch
from app.agent.adk_llm import (
    CatalogAdkLlm,
    _call_real_vertex_gemini,
)
from app.agent.multi_agent import MultiAgentCoordinator
from app.agent.orchestrator import (
    STAGE_OPTIMAL_MODELS,
    ComparisonOrchestrator,
    _build_thinking_config,
    resolve_model_pair,
    resolve_stage_models,
)
from app.config import settings
from app.models.comparison import ComparisonSynthesis


@pytest.fixture
def sample_benchmark_cases() -> list[dict[str, Any]]:
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
    bq.query_and_wait.return_value = rows
    return bq


class TestThinkingConfigAcrossAllStageModels:
    """Verify _build_thinking_config and all LLM call sites across all 9 STAGE_MODELS."""

    def test_build_thinking_config_across_all_9_stage_models(self) -> None:
        assert len(STAGE_MODELS) == 9
        for model in STAGE_MODELS:
            cfg = _build_thinking_config(model)
            assert cfg is not None, f"Expected ThinkingConfig for {model}, got None"
            if model == "gemini-2.5-pro":
                assert cfg.thinking_budget == 128
            else:
                assert cfg.thinking_budget == 0, (
                    f"Expected thinking_budget=0 for {model}, got {cfg.thinking_budget}"
                )

    @pytest.mark.parametrize(
        "model_id",
        [
            "gemini-2.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
        ],
    )
    def test_classify_intent_with_llm_uses_build_thinking_config(self, model_id: str) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = (
            '{"intent_type": "COMPARISON", "is_comparison_eligible": true,'
            ' "detected_category": "Laptops", "target_keywords": ["MacBook Air"],'
            ' "reasoning": "Comparison query"}'
        )
        mock_client.models.generate_content.return_value = mock_resp

        orchestrator = ComparisonOrchestrator(
            repository=MagicMock(),
            genai_client=mock_client,
        )
        orchestrator.classify_intent_with_llm(
            query="Compare MacBook Air vs Dell XPS laptops",
            model=model_id,
        )
        assert mock_client.models.generate_content.called
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config: types.GenerateContentConfig = call_kwargs["config"]
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_budget == 0, (
            f"classify_intent_with_llm passed thinking_config={config.thinking_config} "
            f"for model {model_id}"
        )

    @pytest.mark.parametrize(
        "model_id",
        [
            "gemini-2.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
        ],
    )
    def test_call_real_vertex_gemini_uses_build_thinking_config(
        self, monkeypatch: pytest.MonkeyPatch, model_id: str
    ) -> None:
        monkeypatch.setenv("BENCHMARK_ACTUAL_MODEL", "1")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"category": "laptops"}'
        mock_resp.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_resp

        monkeypatch.setattr(ha, "_get_shared_vertex_client", MagicMock(return_value=mock_client))
        monkeypatch.setattr(ha, "_get_vertex_client_for_model", lambda m, **kw: mock_client)
        res = _call_real_vertex_gemini(
            prompt="Classify query",
            system_instruction="Classify",
            model=model_id,
        )
        assert res[0] == '{"category": "laptops"}'
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config: types.GenerateContentConfig = call_kwargs.get("config")
        if config is not None:
            assert config.thinking_config is not None
            assert config.thinking_config.thinking_budget == 0, (
                f"_call_real_vertex_gemini passed thinking_config={config.thinking_config} "
                f"for model {model_id}"
            )

    @pytest.mark.parametrize(
        "model_id",
        [
            "gemini-2.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
        ],
    )
    def test_catalog_adk_llm_generate_content_async_uses_build_thinking_config(
        self, monkeypatch: pytest.MonkeyPatch, model_id: str
    ) -> None:
        monkeypatch.setenv("BENCHMARK_ACTUAL_MODEL", "1")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.candidates = []
        mock_resp.text = '{"summary": "Great laptop"}'
        mock_resp.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_resp

        llm = CatalogAdkLlm(model=model_id, genai_client=mock_client)
        req = LlmRequest(
            model=model_id,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Compare MacBook vs Dell")],
                )
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )

        async def _run() -> list[Any]:
            return [r async for r in llm.generate_content_async(req)]

        responses = asyncio.run(_run())
        assert len(responses) >= 1
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config: types.GenerateContentConfig = call_kwargs["config"]
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_budget == 0, (
            f"CatalogAdkLlm.generate_content_async passed thinking_config={config.thinking_config} "
            f"for model {model_id}"
        )


class TestModelArmorRegionalRouting:
    """Verify regional Model Armor template paths are preserved and omitted on global endpoints."""

    def test_call_real_vertex_gemini_preserves_regional_model_armor_and_omits_on_global(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("BENCHMARK_ACTUAL_MODEL", "1")
        monkeypatch.setattr(
            ha.settings,
            "model_armor_prompt_template",
            "projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/templates/catalog-prompt-guard",
        )
        monkeypatch.setattr(
            orch.settings,
            "model_armor_prompt_template",
            "projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/templates/catalog-prompt-guard",
        )

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"category": "laptops"}'
        mock_resp.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client = MagicMock(return_value=mock_client)
        monkeypatch.setattr(ha, "_get_shared_vertex_client", mock_get_client)
        monkeypatch.setattr(ha, "_get_vertex_client_for_model", lambda m, **kw: mock_client)

        # 1. Regional 2.5-pro model -> preserves /locations/us-central1/ template path
        _call_real_vertex_gemini(
            prompt="Compare laptops",
            system_instruction="Synthesize",
            model="gemini-2.5-pro",
        )
        cfg_25_pro: types.GenerateContentConfig = (
            mock_client.models.generate_content.call_args.kwargs["config"]
        )
        assert cfg_25_pro.model_armor_config is not None
        assert "/locations/us-central1/" in cfg_25_pro.model_armor_config.prompt_template_name
        assert "/locations/global/" not in cfg_25_pro.model_armor_config.prompt_template_name

        # 2. Global 3.x model (gemini-3.5-flash) -> omits model_armor_config on global endpoint
        mock_client.models.generate_content.reset_mock()
        _call_real_vertex_gemini(
            prompt="Compare laptops",
            system_instruction="Synthesize",
            model="gemini-3.5-flash",
        )
        cfg_35_flash: types.GenerateContentConfig = (
            mock_client.models.generate_content.call_args.kwargs["config"]
        )
        assert cfg_35_flash.model_armor_config is None

    def test_catalog_adk_llm_preserves_regional_model_armor_and_omits_on_global(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("BENCHMARK_ACTUAL_MODEL", "1")
        monkeypatch.setattr(
            ha.settings,
            "model_armor_prompt_template",
            "projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/templates/catalog-prompt-guard",
        )
        monkeypatch.setattr(
            orch.settings,
            "model_armor_prompt_template",
            "projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/templates/catalog-prompt-guard",
        )

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.candidates = []
        mock_resp.text = '{"summary": "Great laptop"}'
        mock_resp.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_resp

        # 1. Regional 2.5-flash model -> preserves /locations/us-central1/
        llm_regional = CatalogAdkLlm(model="gemini-2.5-flash", genai_client=mock_client)
        req_regional = LlmRequest(
            model="gemini-2.5-flash",
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(text="Compare laptops")])
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        asyncio.run(self._collect_async(llm_regional.generate_content_async(req_regional)))
        cfg_regional: types.GenerateContentConfig = (
            mock_client.models.generate_content.call_args.kwargs["config"]
        )
        assert cfg_regional.model_armor_config is not None
        assert "/locations/us-central1/" in cfg_regional.model_armor_config.prompt_template_name
        assert "/locations/global/" not in cfg_regional.model_armor_config.prompt_template_name

        # 2. Global 3.x model (gemini-3.5-flash) -> omits model_armor_config on global endpoint
        mock_client.models.generate_content.reset_mock()
        llm_global = CatalogAdkLlm(model="gemini-3.5-flash", genai_client=mock_client)
        req_global = LlmRequest(
            model="gemini-3.5-flash",
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(text="Compare laptops")])
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        asyncio.run(self._collect_async(llm_global.generate_content_async(req_global)))
        cfg_global: types.GenerateContentConfig = (
            mock_client.models.generate_content.call_args.kwargs["config"]
        )
        assert cfg_global.model_armor_config is None

    @staticmethod
    async def _collect_async(agen: Any) -> list[Any]:
        return [item async for item in agen]


class TestBenchmarkModelsEnvFlags:
    """Verify evals/benchmark_models.py sets BENCHMARK_ACTUAL_MODEL='1' when live=True."""

    def test_benchmark_models_sets_env_vars_for_live(
        self, monkeypatch: pytest.MonkeyPatch, mock_bq: MagicMock
    ) -> None:
        from evals import benchmark_models as bm

        from app.agent.orchestrator import QueryIntentAnalysis

        recorded_envs: list[str | None] = []

        def spy_classify(self_orch: Any, query: str, *args: Any, **kwargs: Any) -> Any:
            recorded_envs.append(os.environ.get("BENCHMARK_ACTUAL_MODEL"))
            return QueryIntentAnalysis(
                intent_type="COMPARISON",
                is_comparison_eligible=True,
                detected_category="Laptops",
                target_keywords=["MacBook Air", "Dell XPS"],
                reasoning="Comparison query",
            )

        monkeypatch.setattr(ComparisonOrchestrator, "classify_intent_with_llm", spy_classify)
        monkeypatch.setattr(
            ComparisonOrchestrator,
            "rank_and_select_products",
            lambda self_o, cands, *args, **kwargs: cands[:2],
        )
        monkeypatch.setattr(
            ComparisonOrchestrator,
            "synthesize_comparison_with_llm",
            lambda self_o, prods, matrix=None, *args, **kwargs: ComparisonSynthesis(
                summary="Grounded [SKU: 6534606] vs [SKU: 6543210]",
                recommendations="Pick [SKU: 6534606]",
                spec_winners={"ram_gb": "6543210", "battery_life_hours": "6534606"},
            ),
        )

        sample_cases = [
            {
                "id": "eval-001",
                "category": "Laptops",
                "query": "Compare MacBook Air and Dell XPS",
                "expected_skus": ["6534606", "6543210"],
                "ground_truth_specs": {},
            }
        ]

        try:
            bm.run_per_stage_benchmarks(
                cases=sample_cases,
                bq_client=mock_bq,
                live=False,
                log_vertex=False,
            )
            assert recorded_envs[-1] is None

            bm.run_per_stage_benchmarks(
                cases=sample_cases,
                bq_client=mock_bq,
                live=True,
                log_vertex=False,
            )
            assert recorded_envs[-1] == "1"
        finally:
            os.environ.pop("BENCHMARK_ACTUAL_MODEL", None)


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

    # 1. Rich multi-attribute synthesis citing all SKUs, quantitative deltas, and persona recommendations
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

    # 2. Shallow price-only summary omitting hardware spec trade-offs
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

    # 3. Contradictory summary (inverting cheapest winner + hallucinating SKU 9999999)
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


def test_run_per_stage_benchmarks_stage3_semantic_quality(
    monkeypatch: pytest.MonkeyPatch,
    mock_bq: MagicMock,
    sample_benchmark_cases: list[dict[str, Any]],
) -> None:
    """Verify run_per_stage_benchmarks includes semantic coherence and records winners."""
    from app.agent.orchestrator import QueryIntentAnalysis

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

    def _mock_synth(
        self_o: Any, prods: list[Any], matrix: Any = None, query: str = "", model: str | None = None
    ) -> ComparisonSynthesis:
        sku_str = " and ".join(f"{p.name} [SKU: {p.sku}] (${p.price:,.2f})" for p in prods)
        spec_str = (
            "leads in RAM (32GB vs 16GB) and Battery Life (18 hours vs 12 hours)"
            if model == "gemini-2.5-pro"
            else "compares specs"
        )
        return ComparisonSynthesis(
            summary=f"Comparing {sku_str}: {prods[0].name} [SKU: {prods[0].sku}] is the lowest price option and {spec_str}.",
            recommendations=f"Best Value: {prods[0].name} [SKU: {prods[0].sku}]. Power Choice: {prods[-1].name} [SKU: {prods[-1].sku}].",
            spec_winners={"ram_gb": prods[-1].sku, "battery_life_hours": prods[0].sku},
        )

    monkeypatch.setattr(ComparisonOrchestrator, "synthesize_comparison_with_llm", _mock_synth)

    res = run_per_stage_benchmarks(
        cases=sample_benchmark_cases,
        bq_client=mock_bq,
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
    assert win.get("stage3_synthesis_quality_winner") in STAGE_MODELS
    assert win.get("stage3_synthesis_latency_winner") in STAGE_MODELS


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


def test_multi_agent_coordinator_stage_optimal_routing(mock_bq: MagicMock) -> None:
    """Verify MultiAgentCoordinator supports stage-optimal routing across specialists."""
    coord = MultiAgentCoordinator(bq_client=mock_bq, model="stage-optimal")
    assert coord.intent_agent.model == "gemini-3.5-flash-lite"
    assert coord.relevance_agent.model == "gemini-2.5-flash-lite"
    assert coord.comparison_agent.synthesis_model == "gemini-2.5-pro"
