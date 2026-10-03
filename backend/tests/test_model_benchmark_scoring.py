"""Unit tests for model execution, ThinkingConfig, hermetic Vertex AI isolation, Model Armor region routing, and benchmark scoring."""

from __future__ import annotations

import asyncio
import inspect
import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from evals.benchmark_models import STAGE_MODELS
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from app.agent import hermetic_adapter as ha
from app.agent import orchestrator as orch
from app.agent.hermetic_adapter import (
    CatalogAdkLlm,
    HermeticModelAdapter,
    _call_real_vertex_gemini,
    create_hermetic_genai_client,
)
from app.agent.orchestrator import (
    ComparisonOrchestrator,
    _build_thinking_config,
)


class TestThinkingConfigAcrossAllStageModels:
    """Verify _build_thinking_config and all LLM call sites across all 9 STAGE_MODELS."""

    def test_build_thinking_config_across_all_9_stage_models(self) -> None:
        assert len(STAGE_MODELS) == 9
        for model in STAGE_MODELS:
            cfg = _build_thinking_config(model)
            if model == "gemini-2.5-flash":
                assert cfg is not None
                assert cfg.thinking_budget == 0
            elif model == "gemini-2.5-pro":
                assert cfg is not None
                assert cfg.thinking_budget == 128
            else:
                # Gemini 3.x (3.5-flash, 3.6-flash, 3.7-flash, 3.8-flash)
                # and Flash-Lite (2.5-flash-lite, 3.1-flash-lite, 3.5-flash-lite)
                # MUST NOT receive thinking_budget=0
                assert cfg is None, f"Expected None for {model}, got {cfg}"

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
            hermetic=False,
        )
        orchestrator.classify_intent_with_llm(
            query="Compare MacBook Air vs Dell XPS laptops",
            model=model_id,
        )
        assert mock_client.models.generate_content.called
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config: types.GenerateContentConfig = call_kwargs["config"]
        assert config.thinking_config is None, (
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
            assert config.thinking_config is None, (
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
        monkeypatch.delenv("HERMETIC_EVAL", raising=False)
        monkeypatch.setenv("BENCHMARK_ACTUAL_MODEL", "1")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.candidates = []
        mock_resp.text = '{"summary": "Great laptop"}'
        mock_resp.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_resp

        llm = CatalogAdkLlm(model=model_id, genai_client=mock_client, hermetic=False)
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
        assert config.thinking_config is None, (
            f"CatalogAdkLlm.generate_content_async passed thinking_config={config.thinking_config} "
            f"for model {model_id}"
        )


class TestHermeticSkipVertexCallAndIsolation:
    """Verify skip_vertex_call=True prevents live Vertex AI leaks in hermetic clients."""

    def test_classify_and_rerank_signatures_have_skip_vertex_call(self) -> None:
        sig_classify = inspect.signature(HermeticModelAdapter.classify_intent_response)
        assert "skip_vertex_call" in sig_classify.parameters
        assert sig_classify.parameters["skip_vertex_call"].default is False

        sig_rerank = inspect.signature(HermeticModelAdapter.rerank_response)
        assert "skip_vertex_call" in sig_rerank.parameters
        assert sig_rerank.parameters["skip_vertex_call"].default is False

    def test_classify_and_rerank_skip_vertex_call_never_calls_real_vertex(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vertex_calls: list[str] = []

        def _forbidden_vertex(*args: Any, **kwargs: Any) -> Any:
            vertex_calls.append("called")
            raise AssertionError("_call_real_vertex_gemini must not be called")

        monkeypatch.setattr(ha, "_call_real_vertex_gemini", _forbidden_vertex)

        res_intent = HermeticModelAdapter.classify_intent_response(
            "Compare MacBook Air vs Dell XPS",
            model="gemini-3.5-flash-lite",
            skip_vertex_call=True,
        )
        assert res_intent.detected_category == "Laptops"

        res_rerank = HermeticModelAdapter.rerank_response(
            'Query: "laptops"\nCandidate SKU: 6001 | Name: MacBook Air M3',
            model="gemini-2.5-flash-lite",
            skip_vertex_call=True,
        )
        assert "6001" in res_rerank
        assert vertex_calls == []

    def test_create_hermetic_genai_client_passes_skip_vertex_call_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, bool, str | None]] = []

        orig_classify = HermeticModelAdapter.classify_intent_response
        orig_rerank = HermeticModelAdapter.rerank_response
        orig_synth = HermeticModelAdapter.synthesis_response

        def spy_classify(
            query: str, model: str | None = None, skip_vertex_call: bool = False
        ) -> Any:
            calls.append(("classify", skip_vertex_call, model))
            return orig_classify(query, model=model, skip_vertex_call=skip_vertex_call)

        def spy_rerank(
            prompt: str, model: str | None = None, skip_vertex_call: bool = False
        ) -> str:
            calls.append(("rerank", skip_vertex_call, model))
            return orig_rerank(prompt, model=model, skip_vertex_call=skip_vertex_call)

        def spy_synth(prompt: str, skip_vertex_call: bool = False, model: str | None = None) -> str:
            calls.append(("synthesis", skip_vertex_call, model))
            return orig_synth(prompt, skip_vertex_call=skip_vertex_call, model=model)

        monkeypatch.setattr(
            HermeticModelAdapter, "classify_intent_response", staticmethod(spy_classify)
        )
        monkeypatch.setattr(HermeticModelAdapter, "rerank_response", staticmethod(spy_rerank))
        monkeypatch.setattr(HermeticModelAdapter, "synthesis_response", staticmethod(spy_synth))

        client = create_hermetic_genai_client()

        # 1. Intent classification call
        client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents="You are the Query Intent Specialist. Extract from: <user_query>Compare MacBook vs Dell</user_query>",
        )
        # 2. Rerank call
        client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents="You are a relevance judge.\nCandidates:\n- SKU: 6001 | Name: MacBook Air",
        )
        # 3. Synthesis call
        client.models.generate_content(
            model="gemini-2.5-pro",
            contents="You are the Comparison Specialist. Synthesize comparison.",
        )

        assert ("classify", True, "gemini-3.5-flash-lite") in calls
        assert ("rerank", True, "gemini-2.5-flash-lite") in calls
        assert ("synthesis", True, "gemini-2.5-pro") in calls

    def test_catalog_adk_llm_generate_hermetic_passes_skip_vertex_call_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, bool]] = []
        orig_classify = HermeticModelAdapter.classify_intent_response

        def spy_classify(
            query: str, model: str | None = None, skip_vertex_call: bool = False
        ) -> Any:
            calls.append(("classify", skip_vertex_call))
            return orig_classify(query, model=model, skip_vertex_call=skip_vertex_call)

        monkeypatch.setattr(
            HermeticModelAdapter, "classify_intent_response", staticmethod(spy_classify)
        )

        llm = CatalogAdkLlm(model="gemini-3.5-flash-lite", hermetic=True)
        req = LlmRequest(
            model="gemini-3.5-flash-lite",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text='User Query: "Compare laptops"')],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction="You are the Query Intent Specialist. classify its intent"
            ),
        )
        llm._generate_hermetic_llm_response(req)
        assert ("classify", True) in calls

    def test_orchestrator_invoke_specialist_via_adk_runner_passes_hermetic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_hermetic: list[bool] = []

        orig_init = CatalogAdkLlm.__init__

        def spy_init(self_llm: Any, *args: Any, **kwargs: Any) -> None:
            captured_hermetic.append(bool(kwargs.get("hermetic", False)))
            orig_init(self_llm, *args, **kwargs)

        monkeypatch.setattr(CatalogAdkLlm, "__init__", spy_init)

        orchestrator = ComparisonOrchestrator(
            repository=MagicMock(),
            genai_client=create_hermetic_genai_client(),
            hermetic=True,
        )
        assert hasattr(orchestrator, "_invoke_specialist_via_adk_runner")
        resp = orchestrator._invoke_specialist_via_adk_runner(
            agent_name="query_intent_specialist",
            instruction="You are the Query Intent Specialist. classify its intent.",
            prompt="<user_query>Compare MacBook Air vs Dell XPS</user_query>",
            model="gemini-3.5-flash-lite",
        )
        assert resp
        assert True in captured_hermetic


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
        monkeypatch.delenv("HERMETIC_EVAL", raising=False)
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
        llm_regional = CatalogAdkLlm(
            model="gemini-2.5-flash", genai_client=mock_client, hermetic=False
        )
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
        llm_global = CatalogAdkLlm(
            model="gemini-3.5-flash", genai_client=mock_client, hermetic=False
        )
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
    """Verify evals/benchmark_models.py sets BENCHMARK_ACTUAL_MODEL='1' when live=True and HERMETIC_EVAL='true' when live=False."""

    def test_benchmark_models_sets_env_vars_for_hermetic_and_live(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from evals import benchmark_models as bm

        from app.agent.orchestrator import QueryIntentAnalysis

        recorded_envs: list[tuple[str | None, str | None]] = []

        def spy_classify(self_orch: Any, query: str, *args: Any, **kwargs: Any) -> Any:
            recorded_envs.append(
                (
                    os.environ.get("BENCHMARK_ACTUAL_MODEL"),
                    os.environ.get("HERMETIC_EVAL"),
                )
            )
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
            lambda self_o, prods, matrix, *args, **kwargs: (
                "Grounded [SKU: 6534606] vs [SKU: 6543210]",
                "Pick [SKU: 6534606]",
            ),
        )

        mock_bq = MagicMock()
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
            assert recorded_envs[-1] == (None, "true")

            bm.run_per_stage_benchmarks(
                cases=sample_cases,
                bq_client=mock_bq,
                live=True,
                log_vertex=False,
            )
            assert recorded_envs[-1] == ("1", None)
        finally:
            os.environ.pop("BENCHMARK_ACTUAL_MODEL", None)
            os.environ.pop("HERMETIC_EVAL", None)
