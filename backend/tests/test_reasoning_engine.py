"""Unit tests for Vertex AI Reasoning Engine integration and Cloud Run gateway delegation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agent.reasoning_engine import CatalogComparisonReasoningEngine
from app.models.requests import ComparisonRequest
from app.models.responses import CompareResponse
from app.routes.compare import _execute_comparison_sync


def test_reasoning_engine_initialization_and_setup() -> None:
    """Verify CatalogComparisonReasoningEngine sets up MultiAgentCoordinator correctly."""
    engine = CatalogComparisonReasoningEngine(
        project_id="test-project",
        region="us-central1",
        model="gemini-2.5-flash",
    )
    assert engine._coordinator is None
    engine.set_up()
    assert engine._coordinator is not None
    assert engine._coordinator.model == "gemini-2.5-flash"


def test_reasoning_engine_query_execution() -> None:
    """Verify ReasoningEngine.query returns valid dictionary matching CompareResponse schema."""
    engine = CatalogComparisonReasoningEngine(model="gemini-2.5-flash")
    result = engine.query(query="MacBook Air vs Dell XPS 13")

    assert isinstance(result, dict)
    assert "summary" in result
    assert "products" in result
    assert "comparison_matrix" in result

    # Validate that result can be parsed by ComparisonResponse
    parsed = CompareResponse.model_validate(result)
    assert parsed.summary is not None
    assert len(parsed.products) == 2


def test_reasoning_engine_stream_query() -> None:
    """Verify ReasoningEngine.stream_query yields turn events."""
    engine = CatalogComparisonReasoningEngine(model="gemini-2.5-flash")
    events = list(engine.stream_query(query="MacBook Air vs Dell XPS 13"))

    assert len(events) >= 1
    assert events[0]["event_type"] == "comparison_completed"
    assert "data" in events[0]
    assert "summary" in events[0]["data"]


def test_route_delegates_to_agent_runtime_when_configured() -> None:
    """Verify _execute_comparison_sync delegates to ReasoningEngine when resource name configured."""
    mock_remote_agent = MagicMock()
    mock_remote_agent.query.return_value = {
        "summary": "Remote comparison summary from Vertex AI Agent Runtime",
        "products": [
            {
                "sku": "6534606",
                "name": "MacBook Air",
                "brand": "Apple",
                "category": "Laptops",
                "price": 1099.0,
                "url": "https://www.techbuy.com/site/sku/6534606.p",
            },
            {
                "sku": "6575132",
                "name": "Dell XPS 13",
                "brand": "Dell",
                "category": "Laptops",
                "price": 1199.0,
                "url": "https://www.techbuy.com/site/sku/6575132.p",
            },
        ],
        "comparison_matrix": [],
        "citations": [],
        "agent_version": "1.0.0",
        "model_version": "gemini-2.5-pro@001",
        "synthesis_model": "gemini-2.5-pro",
    }

    mock_re_module = MagicMock()
    mock_re_module.ReasoningEngine.return_value = mock_remote_agent

    test_request = ComparisonRequest(query="MacBook Air vs Dell XPS 13")

    with (
        patch(
            "app.config.settings.agent_runtime_resource_name",
            "projects/123/locations/us-central1/reasoningEngines/456",
        ),
        patch.dict("os.environ", {"PYTEST_CURRENT_TEST": ""}),
        patch.dict("sys.modules", {"vertexai.preview.reasoning_engines": mock_re_module}),
    ):
        response = _execute_comparison_sync(test_request)
        assert response.summary == "Remote comparison summary from Vertex AI Agent Runtime"
        mock_remote_agent.query.assert_called_once()


def test_adk_app_registers_query_method() -> None:
    """Verify app.agent.agent attaches structured .query() onto AdkApp and allowlists it."""
    import google.adk.cli.fast_api as adk_fast_api
    from vertexai.agent_engines import AdkApp

    import app.agent.agent  # noqa: F401

    assert hasattr(AdkApp, "query")
    assert "query" in adk_fast_api._ALLOWED_AGENT_ENGINE_CLASS_METHODS


def test_invoke_remote_reasoning_engine_rest_endpoint() -> None:
    """Verify _invoke_remote_reasoning_engine posts to Vertex AI :streamQuery via pooled session."""
    import json

    from app.routes import compare as compare_module

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = json.dumps(
        {
            "summary": "REST ReasoningEngine summary",
            "products": [
                {
                    "sku": "6534606",
                    "name": "MacBook Air",
                    "brand": "Apple",
                    "category": "Laptops",
                    "price": 1099.0,
                    "url": "https://www.techbuy.com/site/sku/6534606.p",
                },
                {
                    "sku": "6575132",
                    "name": "Dell XPS 13",
                    "brand": "Dell",
                    "category": "Laptops",
                    "price": 1199.0,
                    "url": "https://www.techbuy.com/site/sku/6575132.p",
                },
            ],
            "comparison_matrix": [],
            "citations": [],
            "agent_version": "1.2.0-tiered",
            "model_version": "tiered-hybrid(gemini-2.5-flash+gemini-2.5-pro)@001",
            "synthesis_model": "gemini-2.5-pro",
        }
    )
    mock_session.post.return_value = mock_resp

    mock_creds = MagicMock()
    mock_creds.valid = True
    mock_creds.expired = False
    mock_creds.token = "fake-token"

    with (
        patch.object(compare_module, "_REMOTE_ENGINE_SESSION", mock_session),
        patch.object(compare_module, "_REMOTE_ENGINE_CREDS", mock_creds),
    ):
        req = ComparisonRequest(query="MacBook Air vs Dell XPS 13", category="Laptops")
        resp = compare_module._invoke_remote_reasoning_engine(
            resource_name="projects/499572810092/locations/us-central1/reasoningEngines/2445220951441276928",
            request=req,
            effective_model="tiered-hybrid",
            effective_synthesis=None,
        )
        assert resp.summary == "REST ReasoningEngine summary"
        mock_session.post.assert_called_once()
        called_url = mock_session.post.call_args[0][0]
        assert called_url.endswith(
            "projects/499572810092/locations/us-central1/reasoningEngines/2445220951441276928:streamQuery"
        )
