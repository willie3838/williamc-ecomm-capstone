"""Unit tests for agent entrypoint functions: _extract_message_text, _format_playground_event, and Reasoning Engine wrapping."""

from unittest.mock import MagicMock, patch

import pytest

from app.agent.agent import (
    _extract_message_text,
    _format_playground_event,
    _register_reasoning_engine_query_method,
)


class TestAgentEntrypoint:
    """Test suite for agent.py helper functions and Reasoning Engine registration."""

    def test_extract_message_text_string(self):
        """Verify extracting query text from raw string input."""
        assert (
            _extract_message_text("  Compare MacBook Air and Dell XPS  ")
            == "Compare MacBook Air and Dell XPS"
        )
        assert _extract_message_text("") == ""

    def test_extract_message_text_dict_with_parts(self):
        """Verify extracting text from ADK Content dict format."""
        msg = {
            "parts": [
                {"text": "Compare iPad Pro"},
                {"text": "vs Galaxy Tab"},
            ]
        }
        assert _extract_message_text(msg) == "Compare iPad Pro vs Galaxy Tab"

    def test_extract_message_text_edge_cases(self):
        """Verify non-string/non-dict inputs or invalid part structures return None."""
        assert _extract_message_text(None) is None
        assert _extract_message_text(12345) is None
        assert _extract_message_text([]) is None
        assert _extract_message_text({}) is None
        assert _extract_message_text({"parts": "not_a_list"}) is None
        assert _extract_message_text({"parts": [{"other_key": "val"}]}) is None
        assert _extract_message_text({"parts": []}) is None

    def test_format_playground_event_full(self):
        """Verify formatting a full CompareResponse dictionary into an ADK event dict."""
        sample_response = {
            "summary": "MacBook Air has better battery life, while Dell XPS has higher refresh rate.",
            "recommendations": "Buy MacBook Air for travel; buy Dell XPS for productivity.",
            "comparison_matrix": [
                {
                    "feature": "Battery Life",
                    "values": {"6534606": "18.0h", "6575132": "14.0h"},
                    "winner_sku": "6534606",
                },
                {
                    "feature": "RAM",
                    "values": {"6534606": "16GB", "6575132": "16GB"},
                    "winner_sku": None,
                },
            ],
        }
        event_dict = _format_playground_event(sample_response)
        assert event_dict["author"] == "catalog_comparison_orchestrator"
        content = event_dict.get("content")
        assert content is not None
        # Check text in parts
        parts = (
            content.get("parts") if isinstance(content, dict) else getattr(content, "parts", None)
        )
        assert parts is not None
        first_part = parts[0]
        text = (
            first_part.get("text")
            if isinstance(first_part, dict)
            else getattr(first_part, "text", "")
        )
        assert "MacBook Air has better battery life" in text
        assert "Specification Comparison" in text
        assert "Battery Life" in text
        assert "[SKU: 6534606]" in text
        assert "Winner: [SKU: 6534606]" in text
        assert "Recommendations:" in text

    def test_format_playground_event_fallback_on_import_error(self):
        """Verify fallback formatting when ADK Event or types cannot be constructed."""
        sample_response = {
            "summary": "Simple summary",
            "recommendations": "",
            "comparison_matrix": [],
        }
        with patch.dict("sys.modules", {"google.adk.events.event": None}):
            event_dict = _format_playground_event(sample_response)
            assert event_dict["author"] == "catalog_comparison_orchestrator"
            assert event_dict["content"]["role"] == "model"
            assert event_dict["content"]["parts"][0]["text"] == "Simple summary"

    def test_register_reasoning_engine_query_method_execution(self):
        """Verify _register_reasoning_engine_query_method attaches query and wraps stream methods on AdkApp."""
        from vertexai.agent_engines import AdkApp

        _register_reasoning_engine_query_method()

        # AdkApp should have query method
        assert hasattr(AdkApp, "query")
        assert hasattr(AdkApp, "register_operations")
        assert hasattr(AdkApp, "stream_query")
        assert hasattr(AdkApp, "async_stream_query")

        # Test operations dictionary wrapping
        mock_instance = MagicMock()
        ops = AdkApp.register_operations(mock_instance)
        assert "query" in ops.get("", [])

    def test_adk_app_query_delegation(self):
        """Verify AdkApp.query calls reasoning_engine.query."""
        from vertexai.agent_engines import AdkApp

        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Grounded comparison result"}
            res = AdkApp.query(
                None,
                query="Compare MacBook and Dell",
                category="Laptops",
                session_id="sess-456",
            )
            assert res == {"summary": "Grounded comparison result"}
            mock_re_query.assert_called_once_with(
                query="Compare MacBook and Dell",
                category="Laptops",
                session_id="sess-456",
                agent_version=None,
                model=None,
                synthesis_model=None,
            )

    def test_stream_query_wrapper_compare_request_and_text(self):
        """Verify AdkApp.stream_query wrapper routes compare requests and raw user text."""
        from vertexai.agent_engines import AdkApp

        # Case 1: string with __compare_request__
        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Success compare"}
            compare_json = '{"__compare_request__": true, "query": "MacBook vs Surface", "category": "Laptops"}'
            gen = AdkApp.stream_query(
                MagicMock(),
                message=compare_json,
                user_id="test_user",
                session_id="test_session",
            )
            results = list(gen)
            assert len(results) == 1
            assert results[0] == {"summary": "Success compare"}

        # Case 2: invalid JSON string containing __compare_request__
        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Success text"}
            malformed_json = '{"__compare_request__": true, invalid}'
            gen = AdkApp.stream_query(
                MagicMock(),
                message=malformed_json,
                user_id="test_user",
                session_id="test_session",
            )
            results = list(gen)
            assert len(results) == 1

        # Case 3: dictionary with __compare_request__
        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Dict compare"}
            compare_dict = {
                "__compare_request__": True,
                "query": "iPad vs Galaxy",
                "category": "Tablets",
            }
            gen = AdkApp.stream_query(
                MagicMock(),
                message=compare_dict,
                user_id="test_user",
                session_id="test_session",
            )
            results = list(gen)
            assert len(results) == 1
            assert results[0] == {"summary": "Dict compare"}

        # Case 4: Plain user text (Playground event)
        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Playground summary", "comparison_matrix": []}
            gen = AdkApp.stream_query(
                MagicMock(),
                message="Compare headphones",
                user_id="test_user",
                session_id="test_session",
            )
            results = list(gen)
            assert len(results) == 1
            assert results[0]["author"] == "catalog_comparison_orchestrator"

    @pytest.mark.asyncio
    async def test_async_stream_query_wrapper_variants(self):
        """Verify AdkApp.async_stream_query wrapper routes compare requests and raw user text."""
        from vertexai.agent_engines import AdkApp

        # Case 1: Dict with __compare_request__
        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Async compare"}
            compare_dict = {
                "__compare_request__": True,
                "query": "Sony vs Bose",
                "category": "Headphones",
            }
            gen = AdkApp.async_stream_query(
                MagicMock(),
                message=compare_dict,
                user_id="test_user",
                session_id="test_session",
            )
            results = []
            async for ev in gen:
                results.append(ev)
            assert len(results) == 1
            assert results[0] == {"summary": "Async compare"}

        # Case 2: String with __compare_request__
        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Async string compare"}
            compare_json = (
                '{"__compare_request__": true, "query": "LG vs Samsung", "category": "TVs"}'
            )
            gen = AdkApp.async_stream_query(
                MagicMock(),
                message=compare_json,
                user_id="test_user",
                session_id="test_session",
            )
            results = []
            async for ev in gen:
                results.append(ev)
            assert len(results) == 1
            assert results[0] == {"summary": "Async string compare"}

        # Case 3: Plain user text
        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Async playground summary"}
            gen = AdkApp.async_stream_query(
                MagicMock(),
                message="LG OLED vs Samsung Neo",
                user_id="test_user",
                session_id="test_session",
            )
            results = []
            async for ev in gen:
                results.append(ev)
            assert len(results) == 1
            assert results[0]["author"] == "catalog_comparison_orchestrator"

        # Case 4: Malformed json in async_stream_query
        with patch("app.agent.agent.reasoning_engine.query") as mock_re_query:
            mock_re_query.return_value = {"summary": "Async fallback"}
            malformed_json = '{"__compare_request__": true, invalid}'
            gen = AdkApp.async_stream_query(
                MagicMock(),
                message=malformed_json,
                user_id="test_user",
                session_id="test_session",
            )
            results = []
            async for ev in gen:
                results.append(ev)
            assert len(results) == 1

    def test_agent_exports_app_and_compaction_and_resumability(self):
        """Verify agent.py exports app and adk_app with EventsCompactionConfig and ResumabilityConfig."""
        from google.adk.apps.app import App, EventsCompactionConfig, ResumabilityConfig

        from app.agent.agent import adk_app, app

        assert app is not None
        assert isinstance(app, App)
        assert adk_app is app

        assert app.events_compaction_config is not None
        assert isinstance(app.events_compaction_config, EventsCompactionConfig)
        assert app.events_compaction_config.token_threshold == 32000
        assert app.events_compaction_config.event_retention_size == 5
        assert app.events_compaction_config.compaction_interval == 8
        assert app.events_compaction_config.overlap_size == 2

        assert app.resumability_config is not None
        assert isinstance(app.resumability_config, ResumabilityConfig)
        assert app.resumability_config.is_resumable is True

    @pytest.mark.asyncio
    async def test_create_adk_agent_memory_tool_and_callback(self):
        """Verify create_adk_agent equips PreloadMemoryTool and after_agent_callback."""
        from unittest.mock import AsyncMock

        from google.adk.tools.preload_memory_tool import PreloadMemoryTool

        from app.agent.orchestrator import create_adk_agent, generate_memories_callback

        agent = create_adk_agent()
        tool_types = [type(t) for t in agent.tools]
        assert PreloadMemoryTool in tool_types
        assert agent.after_agent_callback is generate_memories_callback

        # Verify generate_memories_callback calls add_session_to_memory
        mock_ctx = AsyncMock()
        mock_ctx.add_session_to_memory = AsyncMock(return_value=None)
        await generate_memories_callback(mock_ctx)
        mock_ctx.add_session_to_memory.assert_awaited_once()
