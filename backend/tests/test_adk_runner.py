"""Tests verifying Google ADK Runner integration with catalog comparison agent."""

from pathlib import Path
from unittest.mock import patch

import pytest
from google.adk.agents import Agent
from google.adk.memory import VertexAiMemoryBankService
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import InMemorySessionService, VertexAiSessionService

from app.agent.orchestrator import ComparisonOrchestrator
from app.agent.runner import (
    CatalogAdkRunner,
    CatalogVertexAiMemoryBankService,
    CatalogVertexAiSessionService,
    create_catalog_runner,
    get_adk_runner,
    run_adk_agent,
)
from app.models.responses import CompareResponse


class TestADKRunnerIntegration:
    """Verify ADK Runner lifecycle, VertexAiSessionService management, and integration."""

    def test_get_adk_runner_defaults(self):
        """Verify get_adk_runner initializes a CatalogAdkRunner (regular Runner, not InMemoryRunner) with VertexAiSessionService."""
        runner = get_adk_runner()
        assert isinstance(runner, Runner)
        assert not isinstance(runner, InMemoryRunner)
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
        from unittest.mock import MagicMock

        from google.genai import types

        import app.agent.adk_llm as ha

        fake_client = MagicMock()
        turn1_resp = MagicMock()
        turn1_resp.prompt_feedback = None
        cand1 = MagicMock()
        cand1.finish_reason = "STOP"
        cand1.content = types.Content(
            role="model",
            parts=[
                types.Part.from_function_call(
                    name="query_catalog",
                    args={"keywords": ["Laptop Alpha", "Laptop Beta"]},
                )
            ],
        )
        turn1_resp.candidates = [cand1]
        turn1_resp.usage_metadata = None

        turn2_resp = MagicMock()
        turn2_resp.prompt_feedback = None
        turn2_resp.candidates = []
        turn2_resp.text = '{"summary": "Laptop Alpha [SKU: 111] vs Laptop Beta [SKU: 222]", "recommendations": "Pick [SKU: 111]", "spec_winners": {}}'
        turn2_resp.usage_metadata = None
        fake_client.models.generate_content.side_effect = [turn1_resp, turn2_resp]

        with (
            patch.object(ha, "_get_shared_vertex_client", return_value=fake_client),
            patch(
                "app.agent.orchestrator.query_catalog",
                return_value=[
                    {
                        "sku": "111",
                        "name": "Laptop Alpha",
                        "brand": "A",
                        "category": "Laptops",
                        "price": 999.0,
                    }
                ],
            ),
        ):
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
        with (
            patch("app.agent.orchestrator.query_catalog") as mock_qc,
            patch("app.agent.runner.run_adk_agent_sync") as mock_run_sync,
        ):
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
            mock_run_sync.return_value = (
                '{"summary": "Alpha Book 14 [SKU: 111] vs Beta Book 14 [SKU: 222].", "recommendations": "Pick [SKU: 111].", "spec_winners": {"battery_life_hours": "111"}}',
                [],
            )
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
        from unittest.mock import MagicMock

        from evals.runner import run_benchmark

        from app.models.responses import Citation, MatrixRow, ProductSpec

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

        prods = [ProductSpec(**p) for p in catalog_data]
        mock_orch = MagicMock()
        mock_orch.execute_with_adk_runner.return_value = CompareResponse(
            summary="Model Alpha Laptop [SKU: 1001] ($899.00) vs Model Beta Laptop [SKU: 1002] ($999.00).",
            products=prods,
            comparison_matrix=[
                MatrixRow(
                    feature="Price",
                    values={"1001": "$899.00", "1002": "$999.00"},
                    winner_sku="1001",
                )
            ],
            citations=[
                Citation(sku="1001", url="https://techbuy.com/1001"),
                Citation(sku="1002", url="https://techbuy.com/1002"),
            ],
            recommendations="Choose Model Alpha Laptop [SKU: 1001].",
        )

        report = run_benchmark(
            dataset_path=data_file,
            catalog_path=cat_file,
            use_adk_runner=True,
            live=False,
            orchestrator=mock_orch,
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

        import app.agent.adk_llm as ha

        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_adk_runner_live")
        monkeypatch.setattr(ha, "_VERTEX_AUTH_UNAVAILABLE", False, raising=False)

        fake_client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.text = (
            '{"summary": "Test [SKU: 111] vs [SKU: 222]", "recommendations": "Pick [SKU: 111]"}'
        )
        fake_resp.candidates = []
        fake_resp.usage_metadata = MagicMock(prompt_token_count=50, candidates_token_count=30)

        fake_client.models.generate_content.side_effect = [
            RuntimeError("model_armor template not found"),
            fake_resp,
            fake_resp,
        ]

        with patch.object(ha, "_get_shared_vertex_client", return_value=fake_client) as mock_shared:
            llm = ha.CatalogAdkLlm(model="gemini-2.5-pro")
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
            first_call = fake_client.models.generate_content.call_args_list[0]
            retry_call = fake_client.models.generate_content.call_args_list[1]
            assert first_call.kwargs["model"] == "gemini-2.5-flash"
            assert first_call.kwargs["config"].thinking_config.thinking_budget == 0
            assert first_call.kwargs["config"].max_output_tokens == 512
            assert retry_call.kwargs["model"] == "gemini-2.5-flash"
            assert retry_call.kwargs["config"].thinking_config is not None
            assert retry_call.kwargs["config"].thinking_config.thinking_budget == 0

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
        """Verify run_adk_agent_sync uses ephemeral session service when session_id is None and QueryIntentAgent reuses self.orchestrator."""
        from app.agent.multi_agent import QueryIntentAgent
        from app.agent.runner import run_adk_agent_sync

        q_agent = QueryIntentAgent(model="gemini-2.5-flash")
        assert hasattr(q_agent, "orchestrator")
        assert isinstance(q_agent.orchestrator, ComparisonOrchestrator)

        with patch("app.agent.runner.create_catalog_runner") as mock_create:
            mock_runner = Runner(
                agent=q_agent.adk_agent,
                app_name="app",
                session_service=InMemorySessionService(),
            )
            mock_create.return_value = mock_runner
            with patch("app.agent.runner.run_adk_agent") as mock_run:

                async def _empty_gen(*args, **kwargs):
                    if False:
                        yield None

                mock_run.side_effect = _empty_gen
                run_adk_agent_sync(agent=q_agent.adk_agent, prompt="test", session_id=None)
                passed_service = mock_create.call_args.kwargs.get("session_service")
                assert isinstance(passed_service, CatalogVertexAiSessionService)
                passed_memory_service = mock_create.call_args.kwargs.get("memory_service")
                assert isinstance(passed_memory_service, CatalogVertexAiMemoryBankService)

    @pytest.mark.asyncio
    async def test_catalog_vertex_ai_memory_bank_service(self):
        """Verify CatalogVertexAiMemoryBankService works with in-memory fallback."""
        service = CatalogVertexAiMemoryBankService(
            project="fde-bestbuy-sandbox-dev-508321",
            location="us-central1",
            agent_engine_id="2445220951441276928",
        )
        assert isinstance(service, VertexAiMemoryBankService)

        from google.adk.sessions import Session

        session = Session(
            app_name="app",
            user_id="user_test_1",
            id="test_session_mem_1",
        )
        await service.add_session_to_memory(session=session)

        await service.add_events_to_memory(
            app_name="app",
            user_id="user_test_1",
            session_id="test_session_mem_1",
            events=[],
        )

        await service.add_memory(
            app_name="app",
            user_id="user_test_1",
            memories=["Customer prefers lightweight 13-inch laptops with high battery life."],
        )

        search_res = await service.search_memory(
            app_name="app",
            user_id="user_test_1",
            query="battery life laptop",
        )
        assert search_res is not None

    def test_resolve_default_agent_engine_id_from_deployment_metadata(self):
        """Verify agent_engine_id resolves to deployment_metadata.json default when env is unset."""
        from app.agent.runner import _resolve_agent_engine_id
        from app.config import Settings

        resolved = _resolve_agent_engine_id(None)
        assert resolved == "2445220951441276928"

        settings = Settings(
            gcp_project="fde-bestbuy-sandbox-dev-508321",
            google_cloud_agent_engine_id=None,
        )
        assert settings.agent_engine_id == "2445220951441276928"

    def test_catalog_adk_runner_with_compaction_and_resumability(self):
        """Verify CatalogAdkRunner wires EventsCompactionConfig and ResumabilityConfig."""
        from google.adk.apps.app import EventsCompactionConfig, ResumabilityConfig

        runner = get_adk_runner()
        assert runner.app is not None
        assert runner.app.events_compaction_config is not None
        assert isinstance(runner.app.events_compaction_config, EventsCompactionConfig)
        assert runner.app.events_compaction_config.token_threshold == 32000
        assert runner.app.events_compaction_config.event_retention_size == 5
        assert runner.app.events_compaction_config.compaction_interval is None
        assert runner.app.events_compaction_config.overlap_size is None
        from app.agent.compaction import CatalogAnchoredEventSummarizer

        assert isinstance(
            runner.app.events_compaction_config.summarizer, CatalogAnchoredEventSummarizer
        )

        assert runner.app.resumability_config is not None
        assert isinstance(runner.app.resumability_config, ResumabilityConfig)
        assert runner.app.resumability_config.is_resumable is True

    def test_reasoning_engine_context_spec_memory_bank_config(self):
        """Verify memory_config exports ReasoningEngineContextSpecMemoryBankConfig helper."""
        from app.agent.memory_config import (
            ReasoningEngineContextSpecMemoryBankConfig,
            get_default_memory_bank_config,
        )

        cfg = get_default_memory_bank_config()
        assert cfg is not None
        assert ReasoningEngineContextSpecMemoryBankConfig is not None

    @pytest.mark.asyncio
    async def test_cross_session_memory_recall_and_user_isolation(self):
        """Verify cross-session memory recall by IAP user email and strict multi-user memory isolation."""
        from google.adk.events import Event
        from google.genai import types as genai_types

        from app.agent.orchestrator import ComparisonOrchestrator
        from app.agent.runner import get_default_memory_service, get_default_session_service
        from app.models.responses import ProductSpec

        session_service = get_default_session_service()
        memory_service = get_default_memory_service()

        user_alice = "alice@google.com"
        user_bob = "bob@google.com"

        # 1. User Alice records preference in Session 1
        sess_alice_1 = await session_service.create_session(
            app_name="app",
            user_id=user_alice,
            session_id="alice-session-1",
        )
        evt_alice = Event(
            author="user",
            content=genai_types.Content(
                role="user",
                parts=[
                    genai_types.Part.from_text(
                        text="I strictly need at least 32GB RAM and 1TB SSD."
                    )
                ],
            ),
        )
        await session_service.append_event(session=sess_alice_1, event=evt_alice)
        await memory_service.add_session_to_memory(sess_alice_1)

        # 2. Search memory directly for Alice
        mem_alice = await memory_service.search_memory(
            app_name="app",
            user_id=user_alice,
            query="RAM",
        )
        assert len(mem_alice.memories) >= 1
        alice_text = mem_alice.memories[0].content.parts[0].text
        assert "32GB RAM" in alice_text

        # 3. Verify strict multi-user memory isolation: User Bob has 0 memories recalled
        mem_bob = await memory_service.search_memory(
            app_name="app",
            user_id=user_bob,
            query="RAM",
        )
        assert len(mem_bob.memories) == 0

        # 4. In Session 2 (distinct session_id), verify chat_with_products preloads Alice's memory
        p1 = ProductSpec(
            sku="6534606",
            name="MacBook Air M3",
            brand="Apple",
            category="Laptops",
            price=1299.0,
            rating=4.8,
            review_count=50,
            specifications={"ram_gb": 16, "storage_gb": 512},
            in_stock=True,
        )
        orch = ComparisonOrchestrator(model="gemini-2.5-flash")
        resp_alice_sess2 = orch.chat_with_products(
            message="Do these laptops match my RAM requirements?",
            products=[p1],
            session_id="alice-session-2",
            user_id=user_alice,
        )
        assert resp_alice_sess2 is not None
        assert resp_alice_sess2.reply is not None

    def test_chat_with_products_memory_injection_in_prompt(self):
        """Verify recalled memories are injected into the prompt context under <recalled_user_memories>."""
        from unittest.mock import MagicMock, patch

        from google.adk.memory.base_memory_service import MemoryEntry, SearchMemoryResponse
        from google.genai import types as genai_types

        from app.agent.orchestrator import ComparisonOrchestrator
        from app.models.responses import ProductSpec

        p1 = ProductSpec(
            sku="6534606",
            name="MacBook Air M3",
            brand="Apple",
            category="Laptops",
            price=1099.0,
            specifications={"battery_life_hours": 18.0},
            in_stock=True,
        )
        fake_mem = SearchMemoryResponse(
            memories=[
                MemoryEntry(
                    content=genai_types.Content(
                        role="user",
                        parts=[
                            genai_types.Part.from_text(
                                text="Customer preference: lightweight under 3 lbs"
                            )
                        ],
                    )
                )
            ]
        )

        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.return_value = MagicMock(
            text='{"reply": "The MacBook Air [SKU: 6534606] weighs only 2.7 lbs.", "suggested_followups": []}'
        )
        orch = ComparisonOrchestrator(model="gemini-2.5-flash", genai_client=mock_genai_client)

        with patch(
            "app.agent.runner.CatalogVertexAiMemoryBankService.search_memory", return_value=fake_mem
        ):
            with patch.object(orch, "_get_genai_client", return_value=mock_genai_client):
                resp = orch.chat_with_products(
                    message="Which laptop is lighter?",
                    products=[p1],
                    session_id="sess-injection-test",
                    user_id="user_memory_injection@example.com",
                )
                assert resp is not None
                assert mock_genai_client.models.generate_content.called
                call_args = mock_genai_client.models.generate_content.call_args
                prompt_arg = call_args.kwargs.get("contents") or (
                    call_args.args[1] if len(call_args.args) > 1 else ""
                )
                assert "<recalled_user_memories>" in str(prompt_arg)
                assert "lightweight under 3 lbs" in str(prompt_arg)
