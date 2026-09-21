"""Tests verifying Google ADK Runner integration with catalog comparison agent."""

from pathlib import Path
from unittest.mock import patch

import pytest
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService

from app.agent.orchestrator import ComparisonOrchestrator
from app.agent.runner import (
    CatalogAdkRunner,
    FirestoreSessionService,
    create_catalog_runner,
    get_adk_runner,
    run_adk_agent,
)
from app.models.responses import CompareResponse


class TestADKRunnerIntegration:
    """Verify ADK Runner lifecycle, session management, and integration."""

    def test_get_adk_runner_defaults(self):
        """Verify get_adk_runner initializes a CatalogAdkRunner with FirestoreSessionService."""
        runner = get_adk_runner()
        assert isinstance(runner, InMemoryRunner)
        assert isinstance(runner, CatalogAdkRunner)
        assert runner.agent is not None
        assert runner.agent.name == "catalog_comparison_orchestrator"
        assert runner.app_name == "app"
        assert isinstance(runner.session_service, InMemorySessionService)
        assert isinstance(runner.session_service, FirestoreSessionService)

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
    async def test_firestore_session_service_write_through_and_read_through(self):
        """Verify FirestoreSessionService persists sessions to Cloud Firestore and hydrates on L1 cache miss."""
        from unittest.mock import MagicMock

        mock_fs_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_snapshot = MagicMock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = {
            "session_id": "cloud_run_sess_42",
            "app_name": "app",
            "user_id": "enterprise_user",
            "state": {"category": "Laptops"},
            "last_update_time": 1700000000.0,
        }
        mock_doc_ref.get.return_value = mock_doc_snapshot
        mock_fs_client.collection.return_value.document.return_value = mock_doc_ref

        service = FirestoreSessionService(firestore_client=mock_fs_client)
        created = await service.create_session(
            app_name="app",
            user_id="enterprise_user",
            state={"category": "Laptops"},
            session_id="cloud_run_sess_42",
        )
        assert created.id == "cloud_run_sess_42"
        mock_doc_ref.set.assert_called_once()

        # Simulate stateless Cloud Run instance restart by clearing L1 RAM cache
        service.sessions.clear()
        hydrated = await service.get_session(
            app_name="app",
            user_id="enterprise_user",
            session_id="cloud_run_sess_42",
        )
        assert hydrated is not None
        assert hydrated.id == "cloud_run_sess_42"
        assert hydrated.state.get("category") == "Laptops"

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
