"""Unit tests for CatalogRetrievalAgent LLM tool-calling execution and benchmark trajectory evaluation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agent.multi_agent import (
    CatalogRetrievalAgent,
    ComparisonAgentState,
    MultiAgentCoordinator,
)


def test_catalog_retrieval_agent_default_mode():
    """Verify default CatalogRetrievalAgent uses deterministic SQL path without LLM tool calling."""
    agent = CatalogRetrievalAgent()
    assert agent.use_llm_tool_call is False


@patch("app.agent.multi_agent.query_catalog")
def test_catalog_retrieval_agent_deterministic_sql(mock_query_catalog):
    """Verify standard deterministic path calls query_catalog directly."""
    mock_query_catalog.return_value = [
        {
            "sku": "6534606",
            "name": "Apple MacBook Air 15",
            "price": 1299.0,
            "brand": "Apple",
            "category": "Laptops",
            "specifications": {"ram_gb": 16, "battery_life_hours": 18.0},
        }
    ]
    agent = CatalogRetrievalAgent(use_llm_tool_call=False)
    state = ComparisonAgentState(
        raw_query="MacBook Air vs Dell XPS",
        target_keywords=["MacBook Air", "Dell XPS"],
        detected_category="Laptops",
        is_comparison_eligible=True,
    )
    result = agent.process(state)
    assert len(result.retrieved_products) == 1
    assert result.retrieved_products[0].sku == "6534606"
    assert result.step_history[-1]["status"] == "COMPLETED"
    assert result.step_history[-1].get("execution_mode") != "llm_tool_call"


def test_catalog_retrieval_agent_skipped_for_non_comparison():
    """Verify retrieval is skipped when query is non-comparison regardless of tool call mode."""
    agent = CatalogRetrievalAgent(use_llm_tool_call=True)
    state = ComparisonAgentState(
        raw_query="These laptops suck",
        is_comparison_eligible=False,
    )
    result = agent.process(state)
    assert len(result.retrieved_products) == 0
    assert result.step_history[-1]["status"] == "SKIPPED"


@patch("app.agent.multi_agent.query_catalog")
def test_catalog_retrieval_agent_process_with_llm_tool_call(mock_query_catalog):
    """Verify process_with_llm_tool_call invokes LLM with tools=[query_catalog] and parses function call."""
    mock_query_catalog.return_value = [
        {
            "sku": "6534606",
            "name": "Apple MacBook Air 15",
            "price": 1299.0,
            "brand": "Apple",
            "category": "Laptops",
            "specifications": {"ram_gb": 16, "battery_life_hours": 18.0},
        },
        {
            "sku": "6575132",
            "name": "Dell XPS 13",
            "price": 1199.0,
            "brand": "Dell",
            "category": "Laptops",
            "specifications": {"ram_gb": 16, "battery_life_hours": 14.0},
        },
    ]

    agent = CatalogRetrievalAgent(use_llm_tool_call=True)

    # Mock the LLM client generate_content response with function_call
    mock_func_call = MagicMock()
    mock_func_call.name = "query_catalog"
    mock_func_call.args = {
        "keywords": ["MacBook Air", "Dell XPS 13"],
        "category": "Laptops",
    }
    mock_part = MagicMock()
    mock_part.function_call = mock_func_call

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part]

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.function_calls = [mock_func_call]
    mock_response.usage_metadata.prompt_token_count = 145
    mock_response.usage_metadata.candidates_token_count = 35

    state = ComparisonAgentState(
        raw_query="Compare Apple MacBook Air and Dell XPS 13",
        sanitized_query="Compare Apple MacBook Air and Dell XPS 13",
        target_keywords=["MacBook Air", "Dell XPS 13"],
        detected_category="Laptops",
        is_comparison_eligible=True,
    )

    with patch.object(agent, "_get_genai_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = agent.process_with_llm_tool_call(state)

        assert len(result.retrieved_products) == 2
        assert {p.sku for p in result.retrieved_products} == {"6534606", "6575132"}
        step = result.step_history[-1]
        assert step["agent"] == "CatalogRetrievalAgent"
        assert step["status"] == "COMPLETED"
        assert step["execution_mode"] == "llm_tool_call"
        assert step["tool_call_name"] == "query_catalog"
        assert step["argument_compliance"] is True
        assert step["tool_call_latency_ms"] >= 0.0
        assert step["input_tokens"] == 145
        assert step["output_tokens"] == 35


@patch("app.agent.multi_agent.query_catalog")
def test_catalog_retrieval_agent_llm_tool_call_fallback_on_error(mock_query_catalog):
    """Verify tool calling falls back gracefully to deterministic keywords on LLM error."""
    mock_query_catalog.return_value = [
        {
            "sku": "6534606",
            "name": "Apple MacBook Air 15",
            "price": 1299.0,
            "brand": "Apple",
            "category": "Laptops",
            "specifications": {"ram_gb": 16},
        }
    ]

    agent = CatalogRetrievalAgent(use_llm_tool_call=True)
    state = ComparisonAgentState(
        raw_query="MacBook Air vs Dell XPS",
        target_keywords=["MacBook Air", "Dell XPS"],
        detected_category="Laptops",
        is_comparison_eligible=True,
    )

    with patch.object(agent, "_get_genai_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("Vertex timeout")
        mock_get_client.return_value = mock_client

        result = agent.process(state)
        # Should gracefully fallback to deterministic retrieval
        assert len(result.retrieved_products) == 1
        assert result.retrieved_products[0].sku == "6534606"
        step = result.step_history[-1]
        assert step["status"] == "COMPLETED"
        assert step.get("fallback_used") is True


def test_multi_agent_coordinator_use_llm_tool_call_flag():
    """Verify MultiAgentCoordinator passes use_llm_tool_call correctly."""
    coordinator = MultiAgentCoordinator()
    assert coordinator.retrieval_agent.use_llm_tool_call is False

    with (
        patch.object(coordinator.intent_agent, "process", side_effect=lambda s: s),
        patch.object(coordinator.retrieval_agent, "process") as mock_retrieval,
        patch.object(coordinator.relevance_agent, "process", side_effect=lambda s: s),
        patch.object(coordinator.comparison_agent, "process", side_effect=lambda s: s),
    ):
        mock_retrieval.side_effect = lambda s, **kwargs: s

        # Default execute should pass use_llm_tool_call=False
        coordinator.execute("Compare MacBook and XPS")
        assert mock_retrieval.call_args[1].get("use_llm_tool_call", False) is False

        # Explicit execute with use_llm_tool_call=True
        coordinator.execute("Compare MacBook and XPS", use_llm_tool_call=True)
        assert mock_retrieval.call_args[1].get("use_llm_tool_call") is True
