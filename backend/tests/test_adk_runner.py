"""Tests verifying Google ADK Runner integration with catalog comparison agent."""

from pathlib import Path
from unittest.mock import patch

import pytest
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService, VertexAiSessionService

from app.agent.orchestrator import ComparisonOrchestrator
from app.agent.runner import (
    CatalogAdkRunner,
    CatalogVertexAiSessionService,
    create_catalog_runner,
    get_adk_runner,
    run_adk_agent,
)
from app.models.responses import CompareResponse


class TestADKRunnerIntegration:
    """Verify ADK Runner lifecycle, VertexAiSessionService management, and integration."""

    def test_get_adk_runner_defaults(self):
        """Verify get_adk_runner initializes a CatalogAdkRunner with VertexAiSessionService."""
        runner = get_adk_runner()
        assert isinstance(runner, InMemoryRunner)
        assert isinstance(runner, CatalogAdkRunner)
        assert runner.agent is not None
        assert runner.agent.name == "catalog_comparison_orchestrator"
        assert runner.app_name == "app"
        assert isinstance(runner.session_service, VertexAiSessionService)
        assert isinstance(runner.session_service, CatalogVertexAiSessionService)

    def test_create_catalog_runner_custom_agent(self):
        """Verify creating a runner with custom agent or session service."""
        custom_agent = Agent(name="custom_tester", model="gemini-2.5-flash", tools=[])
        custom_service = InMemorySessionService()
        runner = create_catalog_runner(agent=custom_agent, session_service=custom_service)

        assert runner.agent.name == "custom_tester"
        assert runner.session_service is custom_service

    @pytest.mark.asyncio
    async def test_run_adk_agent_execution(self):
        """Verify run_adk_agent runs a real multi-turn ADK invocation (FunctionCall -> FunctionResponse -> synthesis)."""
        events = []
        async for event in run_adk_agent(
            query="Compare Laptop Alpha and Laptop Beta",
            session_id="test_session_1",
            user_id="test_user",
        ):
            events.append(event)

        # Should emit FunctionCall(query_catalog), FunctionResponse, and final synthesis LlmResponse
        assert len(events) >= 2
        has_tool_call = any(
            getattr(p, "function_call", None) is not None
            for ev in events
            if getattr(ev, "content", None) and getattr(ev.content, "parts", None)
            for p in ev.content.parts
        )
        assert has_tool_call, "Expected ADK Runner to emit FunctionCall(query_catalog) event"

    @pytest.mark.asyncio
    async def test_vertex_ai_session_service_with_agent_engine_id(self, monkeypatch):
        """Verify CatalogVertexAiSessionService resolves GOOGLE_CLOUD_AGENT_ENGINE_ID and delegates to VertexAiSessionService."""
        from unittest.mock import AsyncMock, MagicMock

        monkeypatch.delenv("HERMETIC_EVAL", raising=False)
        monkeypatch.setenv(
            "GOOGLE_CLOUD_AGENT_ENGINE_ID",
            "projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/reasoningEngines/9876543210",
        )
        service = CatalogVertexAiSessionService()
        assert isinstance(service, VertexAiSessionService)
        assert service.agent_engine_id == "9876543210"
        assert service._should_use_vertex_remote() is True

        mock_api_client = MagicMock()
        mock_create_resp = MagicMock()
        mock_create_resp.response.name = (
            "projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/"
            "reasoningEngines/9876543210/sessions/agent_runtime_sess_1"
        )
        mock_create_resp.response.session_state = {"category": "Laptops"}
        mock_api_client.agent_engines.sessions.create = AsyncMock(return_value=mock_create_resp)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_api_client)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch.object(service, "_get_api_client", return_value=mock_cm):
            created = await service.create_session(
                app_name="app",
                user_id="enterprise_user",
                state={"category": "Laptops"},
                session_id="agent_runtime_sess_1",
            )
            assert created.id == "agent_runtime_sess_1"
            assert created.state.get("category") == "Laptops"
            mock_api_client.agent_engines.sessions.create.assert_awaited_once_with(
                name="reasoningEngines/9876543210",
                user_id="enterprise_user",
                config={
                    "session_state": {"category": "Laptops"},
                    "session_id": "agent_runtime_sess_1",
                },
            )

    def test_orchestrator_execute_with_adk_runner(self):
        """Verify ComparisonOrchestrator can execute queries via ADK runner path."""
        orchestrator = ComparisonOrchestrator()
        # Mock the underlying catalog tool and synthesis to run hermetically
        with patch("app.agent.orchestrator.query_catalog") as mock_qc:
            mock_qc.return_value = [
                {
                    "sku": "111",
                    "name": "Alpha Book 14",
                    "brand": "Alpha",
                    "category": "Laptops",
                    "price": 999.0,
                    "specifications": {"ram_gb": 16, "battery_life_hours": 12},
                },
                {
                    "sku": "222",
                    "name": "Beta Book 14",
                    "brand": "Beta",
                    "category": "Laptops",
                    "price": 1099.0,
                    "specifications": {"ram_gb": 16, "battery_life_hours": 10},
                },
            ]
            response = orchestrator.execute_with_adk_runner(
                query="Compare Alpha Book 14 vs Beta Book 14",
                category="Laptops",
                session_id="adk_session_123",
            )
            assert isinstance(response, CompareResponse)
            assert len(response.products) == 2
            assert len(response.comparison_matrix) > 0
            assert response.session_id == "adk_session_123"

    def test_eval_runner_with_adk_runner_flag(self, tmp_path: Path):
        """Verify evals.runner.run_benchmark works with use_adk_runner=True."""
        from evals.runner import run_benchmark

        catalog_data = [
            {
                "sku": "1001",
                "name": "Model Alpha Laptop",
                "brand": "AlphaBrand",
                "category": "Laptops",
                "price": 899.0,
                "specifications": {"ram_gb": 16},
            },
            {
                "sku": "1002",
                "name": "Model Beta Laptop",
                "brand": "BetaBrand",
                "category": "Laptops",
                "price": 999.0,
                "specifications": {"ram_gb": 16},
            },
        ]
        cat_file = tmp_path / "catalog.json"
        cat_file.write_text(__import__("json").dumps(catalog_data), encoding="utf-8")

        dataset = [
            {
                "id": "case-01",
                "category": "Laptops",
                "query": "Compare Model Alpha Laptop and Model Beta Laptop",
                "expected_skus": ["1001", "1002"],
                "ground_truth_specs": {
                    "1001": {"name": "Model Alpha Laptop", "price": 899.0},
                    "1002": {"name": "Model Beta Laptop", "price": 999.0},
                },
            }
        ]
        data_file = tmp_path / "evalset.json"
        data_file.write_text(__import__("json").dumps(dataset), encoding="utf-8")

        report = run_benchmark(
            dataset_path=data_file,
            catalog_path=cat_file,
            use_adk_runner=True,
            live=False,
        )
        assert report is not None
        assert report["metadata"]["total_cases"] == 1
        assert report["details"][0]["errors"] == [], f"Errors: {report['details'][0]['errors']}"
        assert report["summary"]["structured_output_validity"] == 1.0

    @pytest.mark.asyncio
    async def test_catalog_adk_llm_flash_zero_thinking_and_shared_client(self, monkeypatch):
        """Verify CatalogAdkLlm reuses _get_shared_vertex_client, maps gemini-2.5-pro to gemini-2.5-flash, sets thinking_budget=0, and right-sizes max_output_tokens."""
        from unittest.mock import MagicMock

        from google.adk.models import LlmRequest
        from google.genai import types

        import app.agent.hermetic_adapter as ha

        monkeypatch.delenv("HERMETIC_EVAL", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_adk_runner_live")
        monkeypatch.setattr(ha, "_VERTEX_AUTH_UNAVAILABLE", False, raising=False)

        fake_client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.text = (
            '{"summary": "Test [SKU: 111] vs [SKU: 222]", "recommendations": "Pick [SKU: 111]"}'
        )
        fake_resp.candidates = []
        fake_resp.usage_metadata = MagicMock(prompt_token_count=50, candidates_token_count=30)

        # First call raises model_armor error to test fallback_cfg preserving thinking_config; second succeeds
        fake_client.models.generate_content.side_effect = [
            RuntimeError("model_armor template not found"),
            fake_resp,
            fake_resp,
        ]

        with patch.object(ha, "_get_shared_vertex_client", return_value=fake_client) as mock_shared:
            llm = ha.CatalogAdkLlm(model="gemini-2.5-pro", hermetic=False)
            req_synth = LlmRequest(
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text="Retrieved Catalog Products:\n- SKU: 111")
                        ],
                    )
                ]
            )
            outputs = [r async for r in llm.generate_content_async(req_synth)]
            assert len(outputs) == 1
            assert mock_shared.call_count >= 1
            # Both initial and fallback retry calls must use gemini-2.5-flash, thinking_budget=0, max_output_tokens=512
            first_call = fake_client.models.generate_content.call_args_list[0]
            retry_call = fake_client.models.generate_content.call_args_list[1]
            assert first_call.kwargs["model"] == "gemini-2.5-flash"
            assert first_call.kwargs["config"].thinking_config.thinking_budget == 0
            assert first_call.kwargs["config"].max_output_tokens == 512
            assert retry_call.kwargs["model"] == "gemini-2.5-flash"
            assert retry_call.kwargs["config"].thinking_config is not None
            assert retry_call.kwargs["config"].thinking_config.thinking_budget == 0

            # Also verify tool-calling / schema-less request gets thinking_budget=0
            req_plain = LlmRequest(
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text="Hello general assistant")],
                    )
                ]
            )
            _ = [r async for r in llm.generate_content_async(req_plain)]
            plain_call = fake_client.models.generate_content.call_args_list[2]
            assert plain_call.kwargs["config"].thinking_config.thinking_budget == 0

    def test_shared_bq_client_and_reauth_fast_fail(self, monkeypatch):
        """Verify query_catalog breaks retry loop immediately on reauthentication error."""
        from unittest.mock import MagicMock

        from app.tools import catalog

        catalog.catalog_cache.clear()
        catalog.catalog_circuit_breaker.reset()
        failing_client = MagicMock()
        failing_client.query.side_effect = RuntimeError(
            "Reauthentication is needed. Please run `gcloud auth application-default login`."
        )
        with pytest.raises(RuntimeError, match="Reauthentication"):
            catalog.query_catalog(
                keywords=["MacBook Air"],
                client=failing_client,
                use_cache=False,
            )
        assert failing_client.query.call_count == 1

    def test_ephemeral_runner_and_reused_query_intent_orchestrator(self):
        """Verify run_adk_agent_sync uses ephemeral InMemorySessionService when session_id is None and QueryIntentAgent reuses self.orchestrator."""
        from app.agent.multi_agent import QueryIntentAgent
        from app.agent.runner import run_adk_agent_sync

        q_agent = QueryIntentAgent(model="gemini-2.5-flash")
        assert hasattr(q_agent, "orchestrator")
        assert isinstance(q_agent.orchestrator, ComparisonOrchestrator)

        with patch("app.agent.runner.create_catalog_runner") as mock_create:
            mock_runner = InMemoryRunner(agent=q_agent.adk_agent, app_name="app")
            mock_create.return_value = mock_runner
            with patch("app.agent.runner.run_adk_agent") as mock_run:

                async def _empty_gen(*args, **kwargs):
                    if False:
                        yield None

                mock_run.side_effect = _empty_gen
                run_adk_agent_sync(
                    agent=q_agent.adk_agent, prompt="test", session_id=None, hermetic=True
                )
                passed_service = mock_create.call_args.kwargs.get("session_service")
                assert isinstance(passed_service, InMemorySessionService)
                assert not isinstance(passed_service, CatalogVertexAiSessionService)

    def test_category_disambiguation_and_category_specific_synthesis(self, monkeypatch):
        """Verify tablet-004/011 category priority and rich synthesis for Headphones, TVs, and Smart Home."""
        import json

        import app.agent.hermetic_adapter as ha

        monkeypatch.setattr(ha, "_VERTEX_AUTH_UNAVAILABLE", True, raising=False)
        with patch.object(ha, "_call_real_vertex_gemini", side_effect=RuntimeError("offline")):
            intent_t4 = ha.HermeticModelAdapter.classify_intent_response(
                "iPad Pro 11 M4 OLED versus Samsung Galaxy Tab S9 AMOLED screen comparison"
            )
            assert intent_t4.detected_category == "Tablets"

            intent_t11 = ha.HermeticModelAdapter.classify_intent_response(
                "Compare Google Pixel Tablet and iPad Pro 11 M4 for smart home and multimedia"
            )
            assert intent_t11.detected_category == "Tablets"

            # TV synthesis enrichment check
            tv_prompt = (
                '- Product: LG C3 65" [SKU: 6535929] | Brand: LG | Price: $1,499.99 | '
                'Specs: {"screen_size_in": 65, "display_technology": "OLED evo", "resolution": "4K (3840 x 2160)", "refresh_rate_hz": 120, "hdr_support": "Dolby Vision, HDR10, HLG", "smart_platform": "webOS 23"}\n'
                '- Product: Samsung S90C 65" [SKU: 6536965] | Brand: Samsung | Price: $1,599.99 | '
                'Specs: {"screen_size_in": 65, "display_technology": "QD-OLED", "resolution": "4K (3840 x 2160)", "refresh_rate_hz": 144, "hdr_support": "HDR10+, HLG", "smart_platform": "Tizen OS"}\n'
            )
            tv_synth = json.loads(ha.HermeticModelAdapter.synthesis_response(tv_prompt))
            assert "144Hz" in tv_synth["summary"] and "120Hz" in tv_synth["summary"]
            assert "QD-OLED" in tv_synth["summary"] and "OLED evo" in tv_synth["summary"]
            assert "[SKU: 6536965]" in (tv_synth["recommendations"] or "")

            # Headphones synthesis enrichment check
            hp_prompt = (
                "- Product: Sony WH-1000XM5 [SKU: 6505727] | Brand: Sony | Price: $399.99 | "
                'Specs: {"battery_life_hours": 30.0, "noise_cancellation": "Active Noise Canceling", "weight_oz": 8.8, "driver_size_mm": 30, "bluetooth_version": "5.2"}\n'
                "- Product: Bose QC Ultra [SKU: 6553823] | Brand: Bose | Price: $429.00 | "
                'Specs: {"battery_life_hours": 24.0, "noise_cancellation": "CustomTune ANC", "weight_oz": 8.9, "driver_size_mm": 35, "bluetooth_version": "5.3"}\n'
            )
            hp_synth = json.loads(ha.HermeticModelAdapter.synthesis_response(hp_prompt))
            assert "8.8 oz" in hp_synth["summary"] and "8.9 oz" in hp_synth["summary"]
            assert "30mm" in hp_synth["summary"] and "35mm" in hp_synth["summary"]

            # Smart Home synthesis enrichment check
            sh_prompt = (
                "- Product: Google Nest 4th Gen [SKU: 6584201] | Brand: Google | Price: $279.99 | "
                'Specs: {"connectivity": "Matter, Thread, Wi-Fi", "display": "Dynamic Farsight", "voice_assistant": "Google Assistant", "power_source": "C-wire"}\n'
                "- Product: ecobee Premium [SKU: 6502275] | Brand: ecobee | Price: $249.99 | "
                'Specs: {"connectivity": "Matter, Wi-Fi", "display": "Touchscreen", "voice_assistant": "Alexa, Siri", "power_source": "Hardwired 24VAC"}\n'
            )
            sh_synth = json.loads(ha.HermeticModelAdapter.synthesis_response(sh_prompt))
            assert "Google Assistant" in sh_synth["summary"]
            assert "Matter" in sh_synth["summary"]
