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
