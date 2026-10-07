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
    assert 2 <= len(parsed.products) <= 5


def test_reasoning_engine_stream_query() -> None:
    """Verify ReasoningEngine.stream_query yields turn events."""
    engine = CatalogComparisonReasoningEngine(model="gemini-2.5-flash")
    events = list(engine.stream_query(query="MacBook Air vs Dell XPS 13"))

    assert len(events) >= 1
    completed_event = [e for e in events if e.get("event_type") == "comparison_completed"][-1]
    assert completed_event["event_type"] == "comparison_completed"
    assert "data" in completed_event
    assert "summary" in completed_event["data"]
    assert any(e.get("event") == "matrix_ready" for e in events)


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


def test_reasoning_engine_query_and_stream_query_forward_user_id() -> None:
    """Verify ReasoningEngine.query and stream_query forward user_id to coordinator."""
    engine = CatalogComparisonReasoningEngine(model="gemini-2.5-flash")
    mock_coord = MagicMock()
    mock_coord.execute.return_value = CompareResponse(
        summary="Test summary",
        products=[],
        comparison_matrix=[],
        citations=[],
        session_id="sess_uid_1",
    )
    mock_coord.execute_stream.return_value = [
        {"event": "complete", "data": {"summary": "Test summary", "products": []}}
    ]
    engine._coordinator = mock_coord

    res = engine.query(query="test", session_id="sess_uid_1", user_id="custom_user_123")
    assert res["summary"] == "Test summary"
    mock_coord.execute.assert_called_with(
        raw_query="test",
        category=None,
        session_id="sess_uid_1",
        agent_version=None,
        model="gemini-2.5-flash",
        synthesis_model=None,
        stage1_model=None,
        stage2_model=None,
        stage3_model=None,
        user_id="custom_user_123",
    )

    events = list(
        engine.stream_query(query="test", session_id="sess_uid_1", user_id="custom_user_123")
    )
    assert len(events) >= 1
    mock_coord.execute_stream.assert_called_with(
        raw_query="test",
        category=None,
        session_id="sess_uid_1",
        agent_version=None,
        model="gemini-2.5-flash",
        synthesis_model=None,
        stage1_model=None,
        stage2_model=None,
        stage3_model=None,
        user_id="custom_user_123",
    )


def test_agent_wrapped_stream_queries_forward_user_id() -> None:
    """Verify _adk_query, _wrapped_stream_query and _wrapped_async_stream_query forward user_id."""
    import asyncio
    import json

    from vertexai.agent_engines import AdkApp

    import app.agent.agent  # noqa: F401 (ensures wraps are registered)

    with patch("app.agent.reasoning_engine.reasoning_engine.query") as mock_re_query:
        mock_re_query.return_value = {"summary": "Compare OK", "products": []}
        mock_self = MagicMock()

        # 0. _adk_query forwards user_id
        AdkApp.query(mock_self, query="Compare Laptops", user_id="enterprise_user_0")
        assert mock_re_query.call_args[1].get("user_id") == "enterprise_user_0"

        # 1. stream_query with dict message containing user_id
        mock_re_query.reset_mock()
        msg_dict = {
            "__compare_request__": True,
            "query": "Laptop A vs B",
            "user_id": "enterprise_user_1",
        }
        list(AdkApp.stream_query(mock_self, message=json.dumps(msg_dict), user_id="fallback_uid"))
        assert mock_re_query.call_args[1].get("user_id") == "enterprise_user_1"

        # 2. stream_query with conversational text message
        mock_re_query.reset_mock()
        list(
            AdkApp.stream_query(
                mock_self,
                message="Which has better battery?",
                user_id="enterprise_user_2",
            )
        )
        assert mock_re_query.call_args[1].get("user_id") == "enterprise_user_2"

        # 3. async_stream_query with compare request and conversational text
        mock_re_query.reset_mock()

        async def _test_async() -> None:
            res1 = []
            async for ev in AdkApp.async_stream_query(
                mock_self, message=json.dumps(msg_dict), user_id="fallback_uid"
            ):
                res1.append(ev)
            assert mock_re_query.call_args[1].get("user_id") == "enterprise_user_1"

            mock_re_query.reset_mock()
            res2 = []
            async for ev in AdkApp.async_stream_query(
                mock_self, message="What about RAM?", user_id="enterprise_user_3"
            ):
                res2.append(ev)
            assert mock_re_query.call_args[1].get("user_id") == "enterprise_user_3"

        asyncio.run(_test_async())
