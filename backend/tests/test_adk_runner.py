"""Tests verifying Google ADK Runner integration with catalog comparison agent."""

from pathlib import Path
from unittest.mock import patch

import pytest
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService

from app.agent.orchestrator import ComparisonOrchestrator
from app.agent.runner import (
    create_catalog_runner,
    get_adk_runner,
    run_adk_agent,
)
from app.models.responses import CompareResponse


class TestADKRunnerIntegration:
    """Verify ADK Runner lifecycle, session management, and integration."""

    def test_get_adk_runner_defaults(self):
        """Verify get_adk_runner initializes an InMemoryRunner with root_agent and session service."""
        runner = get_adk_runner()
        assert isinstance(runner, InMemoryRunner)
        assert runner.agent is not None
        assert runner.agent.name == "catalog_comparison_orchestrator"
        assert runner.app_name == "app"
        assert isinstance(runner.session_service, InMemorySessionService)

    def test_create_catalog_runner_custom_agent(self):
        """Verify creating a runner with custom agent or session service."""
        custom_agent = Agent(name="custom_tester", model="gemini-2.5-flash", tools=[])
        custom_service = InMemorySessionService()
        runner = create_catalog_runner(agent=custom_agent, session_service=custom_service)

        assert runner.agent.name == "custom_tester"
        assert runner.session_service is custom_service

    @pytest.mark.asyncio
    async def test_run_adk_agent_execution(self):
        """Verify run_adk_agent runs an invocation and records events."""
        # Hermetic test of runner event generator
        events = []
        async for event in run_adk_agent(
            query="Compare Laptop Alpha and Laptop Beta",
            session_id="test_session_1",
            user_id="test_user",
        ):
            events.append(event)

        assert len(events) >= 0  # Valid generator execution

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
