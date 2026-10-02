"""Comprehensive test suite for the 3-Tier Lazy Context Compaction Pipeline.

Verifies:
- Tier 1: Deterministic stale tool-output pruning (protects last 3 user turns, protect_token_budget=8000,
  protects preload_memory, prunes bulky query_catalog function_response while retaining {sku, name, price} stub).
- Tier 2: Pre-compaction Vertex AI Memory Bank flush (best-effort add_events_to_memory).
- Tier 3: CatalogAnchoredEventSummarizer (deterministic SKU & price extraction, 5-section Markdown template,
  rolling <previous-summary> merge, and SUMMARY_BANNER_PREFIX).
- App & Runner integration: EventsCompactionConfig with token_threshold=32000, compaction_interval=None, overlap_size=None.
- Orchestrator integration: before_model_callback wired into create_adk_agent, and _persist_chat_session_and_memory.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps.app import EventsCompactionConfig
from google.adk.events import Event
from google.adk.events.event_actions import EventActions, EventCompaction
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from google.genai import types

from app.agent.compaction import (
    SUMMARY_BANNER_PREFIX,
    CatalogAnchoredEventSummarizer,
    flush_events_to_memory_before_compaction,
    prune_tool_outputs,
    prune_tool_outputs_callback,
)
from app.agent.hermetic_adapter import CatalogAdkLlm
from app.agent.orchestrator import create_adk_agent
from app.agent.runner import CatalogVertexAiMemoryBankService, create_catalog_app


def _make_user_event(text: str) -> Event:
    return Event(
        author="user",
        content=types.Content(
            role="user",
            parts=[types.Part.from_text(text=text)],
        ),
    )


def _make_model_event(text: str) -> Event:
    return Event(
        author="catalog_comparison_orchestrator",
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=text)],
        ),
    )


def _make_tool_call_event(tool_name: str, args: dict[str, Any]) -> Event:
    return Event(
        author="catalog_comparison_orchestrator",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name=tool_name,
                        args=args,
                    )
                )
            ],
        ),
    )


def _make_tool_response_event(tool_name: str, response: dict[str, Any]) -> Event:
    return Event(
        author="user",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_name,
                        response=response,
                    )
                )
            ],
        ),
    )


class TestTier1DeterministicPruning:
    """Tests for Tier 1: Deterministic stale tool-output pruning."""

    def test_prune_tool_outputs_protects_recent_three_user_turns(self):
        """Recent 3 user turns must NEVER be pruned regardless of size."""
        session = Session(
            id="test-session-1",
            app_name="app",
            user_id="user-1",
            state={},
            events=[],
        )

        bulky_catalog_payload = {
            "products": [
                {
                    "sku": "6534606",
                    "name": "MacBook Air 13.6 - M3",
                    "price": 1099.0,
                    "description": "A very long detailed product description" * 50,
                    "specs": {"ram": "16GB", "storage": "512GB", "screen": "13.6 Retina"},
                }
            ]
        }

        # Build 3 user turns with tool calls and bulky responses
        for i in range(1, 4):
            session.events.append(_make_user_event(f"User turn {i}"))
            session.events.append(_make_tool_call_event("query_catalog", {"query": f"laptop {i}"}))
            session.events.append(_make_tool_response_event("query_catalog", bulky_catalog_payload))
            session.events.append(_make_model_event(f"Model reply {i}"))

        # Prune with protect_user_turns=3
        pruned_count = prune_tool_outputs(session, protect_user_turns=3, protect_token_budget=0)
        assert pruned_count == 0

        # Verify all tool responses remain completely unpruned
        for event in session.events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_response and part.function_response.name == "query_catalog":
                        assert "products" in part.function_response.response
                        assert "description" in part.function_response.response["products"][0]

    def test_prune_tool_outputs_prunes_older_catalog_responses_with_stub(self):
        """Older turns beyond the protected 3 user turns must have bulky catalog payloads pruned to {sku, name, price}."""
        session = Session(
            id="test-session-2",
            app_name="app",
            user_id="user-1",
            state={},
            events=[],
        )

        bulky_catalog_payload_old = {
            "products": [
                {
                    "sku": "6534606",
                    "name": "MacBook Air 13.6 - M3",
                    "price": 1099.0,
                    "description": "Bulky older description" * 50,
                    "features": ["Feature A", "Feature B", "Feature C"],
                },
                {
                    "sku": "6575132",
                    "name": "Dell XPS 13",
                    "price": 1199.0,
                    "description": "Another bulky description" * 50,
                },
            ]
        }

        # Turn 1 (Oldest, will be outside the protected 3-turn window)
        session.events.append(_make_user_event("Old turn: Compare MacBook Air and Dell XPS"))
        session.events.append(_make_tool_call_event("query_catalog", {"query": "MacBook Dell"}))
        session.events.append(_make_tool_response_event("query_catalog", bulky_catalog_payload_old))
        session.events.append(_make_model_event("Model reply: Comparison 1"))

        # Turns 2, 3, 4 (Recent 3 turns)
        for i in range(2, 5):
            session.events.append(_make_user_event(f"Recent turn {i}"))
            session.events.append(_make_tool_call_event("query_catalog", {"query": f"spec {i}"}))
            session.events.append(
                _make_tool_response_event(
                    "query_catalog",
                    {"products": [{"sku": f"SKU-{i}", "name": f"Product {i}", "price": 99.0}]},
                )
            )
            session.events.append(_make_model_event(f"Model reply {i}"))

        # Prune with protect_user_turns=3
        pruned_count = prune_tool_outputs(session, protect_user_turns=3, protect_token_budget=0)
        assert pruned_count == 1

        # Check turn 1 tool response was pruned to retained_skus stub
        old_tool_resp = session.events[2].content.parts[0].function_response
        assert old_tool_resp.response.get("pruned") is True
        assert "retained_skus" in old_tool_resp.response
        retained = old_tool_resp.response["retained_skus"]
        assert len(retained) == 2
        assert retained[0] == {"sku": "6534606", "name": "MacBook Air 13.6 - M3", "price": 1099.0}
        assert retained[1] == {"sku": "6575132", "name": "Dell XPS 13", "price": 1199.0}
        # Heavy keys removed
        assert "description" not in old_tool_resp.response
        assert "features" not in old_tool_resp.response

    def test_prune_tool_outputs_protects_preload_memory(self):
        """preload_memory tool outputs must NEVER be pruned even if older than 3 turns."""
        session = Session(
            id="test-session-3",
            app_name="app",
            user_id="user-1",
            state={},
            events=[],
        )

        memory_payload = {
            "memories": [
                {"fact": "Customer prefers Apple laptops under $1200", "timestamp": "2026-09-01"}
            ]
        }

        # Turn 1: Preload memory call & response
        session.events.append(_make_user_event("Turn 1"))
        session.events.append(_make_tool_call_event("preload_memory", {}))
        session.events.append(_make_tool_response_event("preload_memory", memory_payload))
        session.events.append(_make_model_event("Model reply 1"))

        # Turns 2, 3, 4, 5: More user turns
        for i in range(2, 6):
            session.events.append(_make_user_event(f"Turn {i}"))
            session.events.append(_make_model_event(f"Reply {i}"))

        pruned_count = prune_tool_outputs(session, protect_user_turns=3, protect_token_budget=0)
        assert pruned_count == 0

        preload_resp = session.events[2].content.parts[0].function_response
        assert preload_resp.name == "preload_memory"
        assert preload_resp.response == memory_payload
        assert preload_resp.response.get("pruned") is not True

    def test_prune_tool_outputs_protect_token_budget(self):
        """Events within protect_token_budget are preserved even if turn count exceeds protect_user_turns."""
        session = Session(
            id="test-session-4",
            app_name="app",
            user_id="user-1",
            state={},
            events=[],
        )

        # 5 short turns, total chars ~ 500 chars (well under 8000 token budget)
        for i in range(1, 6):
            session.events.append(_make_user_event(f"Short query {i}"))
            session.events.append(
                _make_tool_response_event(
                    "query_catalog",
                    {"products": [{"sku": f"90000{i}", "name": f"Item {i}", "price": 10.0}]},
                )
            )

        # protect_token_budget=8000 should protect all events because total token count < 8000
        pruned_count = prune_tool_outputs(session, protect_user_turns=1, protect_token_budget=8000)
        assert pruned_count == 0

    @pytest.mark.asyncio
    async def test_prune_tool_outputs_callback_integrates_with_adk(self):
        """prune_tool_outputs_callback executes smoothly before model invocation."""
        session = Session(
            id="test-session-callback",
            app_name="app",
            user_id="user-1",
            state={},
            events=[],
        )
        # Turn 1 (Old)
        session.events.append(_make_user_event("Old turn"))
        session.events.append(
            _make_tool_response_event(
                "query_catalog",
                {
                    "products": [
                        {
                            "sku": "111111",
                            "name": "Old Phone",
                            "price": 499.0,
                            "details": "x" * 40000,
                        }
                    ]
                },
            )
        )
        # Turns 2, 3, 4 (Recent 3 turns with substantial dialogue exceeding 8000 token budget)
        for i in range(2, 5):
            session.events.append(_make_user_event(f"Turn {i} " + "query context " * 2000))
            session.events.append(_make_model_event(f"Reply {i} " + "comparison details " * 2000))

        mock_invocation_ctx = MagicMock()
        mock_invocation_ctx.session = session
        mock_invocation_ctx.user_content = types.Content(
            role="user", parts=[types.Part.from_text(text="current")]
        )
        mock_invocation_ctx.invocation_id = "inv-1"
        mock_invocation_ctx.agent = MagicMock(name="test_agent")
        mock_invocation_ctx.user_id = "user-1"
        mock_invocation_ctx.run_config = None
        mock_invocation_ctx._custom_metadata = {}
        mock_invocation_ctx.credential_by_key = {}

        callback_context = CallbackContext(mock_invocation_ctx)
        llm_request = LlmRequest(model="gemini-2.5-flash", contents=[])

        res = prune_tool_outputs_callback(callback_context, llm_request)
        if asyncio.iscoroutine(res):
            res = await res

        # Returns None to allow normal LLM generation
        assert res is None

        # Verify old tool response was pruned
        old_resp = session.events[1].content.parts[0].function_response.response
        assert old_resp.get("pruned") is True
        assert old_resp["retained_skus"] == [{"sku": "111111", "name": "Old Phone", "price": 499.0}]


class TestTier2PreCompactionMemoryBankFlush:
    """Tests for Tier 2: Pre-compaction Vertex AI Memory Bank flush."""

    @pytest.mark.asyncio
    async def test_flush_events_to_memory_success(self):
        """Flushes events to memory bank service before summarization."""
        mock_memory_service = MagicMock(spec=CatalogVertexAiMemoryBankService)
        mock_memory_service.add_events_to_memory = AsyncMock()

        events = [_make_user_event("I need a gaming laptop with 32GB RAM under $2000")]

        success = await flush_events_to_memory_before_compaction(
            events=events,
            memory_service=mock_memory_service,
            app_name="catalog_app",
            user_id="user_123",
        )

        assert success is True
        mock_memory_service.add_events_to_memory.assert_awaited_once_with(
            app_name="catalog_app",
            user_id="user_123",
            events=events,
        )

    @pytest.mark.asyncio
    async def test_flush_events_to_memory_resilient_to_exception(self):
        """Memory bank failure must not crash compaction (best-effort resilience)."""
        mock_memory_service = MagicMock(spec=CatalogVertexAiMemoryBankService)
        mock_memory_service.add_events_to_memory = AsyncMock(
            side_effect=RuntimeError("Memory bank offline")
        )

        events = [_make_user_event("Test query")]

        success = await flush_events_to_memory_before_compaction(
            events=events,
            memory_service=mock_memory_service,
            app_name="catalog_app",
            user_id="user_123",
        )

        # Returns False on handled exception without raising
        assert success is False


class TestTier3CatalogAnchoredEventSummarizer:
    """Tests for Tier 3: CatalogAnchoredEventSummarizer."""

    @pytest.mark.asyncio
    async def test_summarizer_extracts_skus_and_prices_and_produces_5_sections(self):
        """Verifies deterministic SKU extraction, 5-section Markdown output, and SUMMARY_BANNER_PREFIX."""
        llm = CatalogAdkLlm(model="gemini-2.5-flash")
        summarizer = CatalogAnchoredEventSummarizer(llm=llm)

        events = [
            _make_user_event(
                "Compare MacBook Air 13.6 [SKU: 6534606] ($1099.00) and Dell XPS 13 [SKU: 6575132] ($1199.00)"
            ),
            _make_model_event(
                "MacBook Air has better battery life, while Dell XPS has more ports."
            ),
        ]

        compaction_event = await summarizer.maybe_summarize_events(events=events)
        assert compaction_event is not None
        assert compaction_event.actions is not None
        assert compaction_event.actions.compaction is not None

        compacted_text = compaction_event.actions.compaction.compacted_content.parts[0].text
        assert compacted_text.startswith(SUMMARY_BANNER_PREFIX)

        # 5 required sections
        assert "### 1. Active Products & SKUs" in compacted_text
        assert "### 2. Customer Constraints & Preferences" in compacted_text
        assert "### 3. Key Spec Trade-offs & Winners" in compacted_text
        assert "### 4. Recommendations Given" in compacted_text
        assert "### 5. Open Follow-up Questions" in compacted_text

        # Grounded SKU and price preservation
        assert "6534606" in compacted_text
        assert "6575132" in compacted_text
        assert "1099" in compacted_text
        assert "1199" in compacted_text

    @pytest.mark.asyncio
    async def test_summarizer_rolling_previous_summary_merge(self):
        """Verifies previous compaction events are extracted and merged via <previous-summary> tags."""
        llm = CatalogAdkLlm(model="gemini-2.5-flash")
        summarizer = CatalogAnchoredEventSummarizer(llm=llm)

        prior_compaction_content = types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=f"{SUMMARY_BANNER_PREFIX}\n### 1. Active Products & SKUs\n- Prior Laptop [SKU: 6400001] ($899.00)"
                )
            ],
        )
        prior_event = Event(
            author="user",
            actions=EventActions(
                compaction=EventCompaction(
                    start_timestamp=100.0,
                    end_timestamp=200.0,
                    compacted_content=prior_compaction_content,
                )
            ),
        )

        new_events = [
            prior_event,
            _make_user_event("Now also compare with MacBook Air [SKU: 6534606] ($1099.00)"),
            _make_model_event("Here is the updated comparison."),
        ]

        compaction_event = await summarizer.maybe_summarize_events(events=new_events)
        assert compaction_event is not None
        compacted_text = compaction_event.actions.compaction.compacted_content.parts[0].text

        assert "6534606" in compacted_text
        assert "6400001" in compacted_text


class TestRunnerAndOrchestratorIntegration:
    """Tests for runner configuration and orchestrator wiring."""

    def test_create_catalog_app_compaction_configuration(self):
        """create_catalog_app must configure token_threshold=32000, event_retention_size=5, compaction_interval=None, overlap_size=None."""
        app = create_catalog_app()
        cfg = app.events_compaction_config

        assert cfg is not None
        assert isinstance(cfg, EventsCompactionConfig)
        assert cfg.token_threshold == 32000
        assert cfg.event_retention_size == 5
        assert cfg.compaction_interval is None
        assert cfg.overlap_size is None
        assert isinstance(cfg.summarizer, CatalogAnchoredEventSummarizer)

    def test_create_adk_agent_wires_before_model_callback(self):
        """create_adk_agent wires before_model_callback=prune_tool_outputs_callback by default."""
        agent = create_adk_agent(model="gemini-2.5-flash")
        assert agent.before_model_callback is not None
        assert agent.before_model_callback == prune_tool_outputs_callback

    def test_persist_chat_session_triggers_tier1_pruning_and_token_threshold_check(self):
        """_persist_chat_session_and_memory executes Tier 1 pruning and token-threshold compaction check."""
        from app.agent.orchestrator import _persist_chat_session_and_memory

        session_id = "test-session-persist"
        user_msg = "Compare Dell XPS and MacBook Air"
        model_msg = "Here are the comparisons with [SKU: 6534606]."

        with patch("app.agent.compaction.prune_tool_outputs") as mock_prune:
            _persist_chat_session_and_memory(
                session_id=session_id,
                user_message=user_msg,
                model_reply=model_msg,
            )
            mock_prune.assert_called_once()
