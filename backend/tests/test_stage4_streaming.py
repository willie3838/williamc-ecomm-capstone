"""Unit and integration tests for Stage 4 LLM streaming and instant matrix progressive rendering."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent.multi_agent import MultiAgentCoordinator
from app.agent.orchestrator import (
    ComparisonOrchestrator,
    SecurityViolationError,
    _extract_partial_synthesis_fields,
    _strip_trailing_incomplete_sku_tag,
    _unescape_json_fragment,
)
from app.agent.reasoning_engine import CatalogComparisonReasoningEngine
from app.main import app
from app.models.responses import ProductSpec


def _sample_products() -> list[ProductSpec]:
    return [
        ProductSpec(
            sku="6534606",
            name='Apple - MacBook Air 13.6" Laptop - M3',
            brand="Apple",
            category="Laptops",
            price=1099.0,
            specifications={"ram_gb": 16, "battery_life_hours": 18},
            in_stock=True,
        ),
        ProductSpec(
            sku="6575132",
            name='Dell - XPS 13" Laptop - Intel Core Ultra 7',
            brand="Dell",
            category="Laptops",
            price=1199.0,
            specifications={"ram_gb": 16, "battery_life_hours": 14},
            in_stock=True,
        ),
    ]


# ---------------------------------------------------------------------------
# 1. Partial JSON Token Extractor & Tag Stripping Tests
# ---------------------------------------------------------------------------


def test_strip_trailing_incomplete_sku_tag():
    # Complete SKU tag remains untouched
    assert (
        _strip_trailing_incomplete_sku_tag("MacBook Air [SKU: 6534606]")
        == "MacBook Air [SKU: 6534606]"
    )
    # Incomplete SKU tag suffix is stripped
    assert _strip_trailing_incomplete_sku_tag("MacBook Air [SKU: 653") == "MacBook Air"
    assert _strip_trailing_incomplete_sku_tag("MacBook Air [SKU:") == "MacBook Air"
    assert _strip_trailing_incomplete_sku_tag("MacBook Air [SK") == "MacBook Air"
    assert _strip_trailing_incomplete_sku_tag("MacBook Air [") == "MacBook Air"
    # Empty string or no bracket
    assert _strip_trailing_incomplete_sku_tag("") == ""
    assert _strip_trailing_incomplete_sku_tag("MacBook Air") == "MacBook Air"


def test_unescape_json_fragment():
    assert _unescape_json_fragment('hello \\"world\\"') == 'hello "world"'
    assert _unescape_json_fragment("line 1\\nline 2") == "line 1\nline 2"
    assert _unescape_json_fragment("tab\\there") == "tab\there"
    assert _unescape_json_fragment("path\\\\to") == "path\\to"
    # Lone trailing backslash should be safely trimmed
    assert _unescape_json_fragment("incomplete escape\\") == "incomplete escape"


def test_extract_partial_synthesis_fields_handles_incomplete_json_and_partial_sku():
    buf1 = '{"summary": "Apple MacBook Air [SKU: 6534606] leads with 18h battery [SKU: 657'
    summary1, recs1 = _extract_partial_synthesis_fields(buf1)
    assert "Apple MacBook Air [SKU: 6534606] leads with 18h battery" in summary1
    assert "[SKU: 657" not in summary1
    assert recs1 is None

    buf2 = (
        '{"summary": "Apple MacBook Air [SKU: 6534606] leads with 18h battery [SKU: 6575132].", '
        '"recommendations": "Best for Travel: Apple MacBook Air [SKU: 6534606]'
    )
    summary2, recs2 = _extract_partial_synthesis_fields(buf2)
    assert summary2.endswith("[SKU: 6575132].")
    assert recs2 == "Best for Travel: Apple MacBook Air [SKU: 6534606]"


# ---------------------------------------------------------------------------
# 2. ComparisonOrchestrator Stage 4 Streaming Generator Tests
# ---------------------------------------------------------------------------


def test_stream_synthesize_comparison_with_llm_emits_chunks_and_final():
    products = _sample_products()
    mock_client = MagicMock()
    chunks = [
        SimpleNamespace(
            text='{"summary": "- Apple MacBook Air [SKU: 6534606] ($1,099.00) ',
            usage_metadata=None,
            candidates=[],
            prompt_feedback=None,
        ),
        SimpleNamespace(
            text='beats Dell XPS 13 [SKU: 6575132] ($1,199.00) on battery (18h vs 14h).", ',
            usage_metadata=None,
            candidates=[],
            prompt_feedback=None,
        ),
        SimpleNamespace(
            text='"recommendations": "Best for Portability: Apple MacBook Air [SKU: 6534606] — 18h battery"}',
            usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=45),
            candidates=[SimpleNamespace(finish_reason="STOP")],
            prompt_feedback=None,
        ),
    ]
    mock_client.models.generate_content_stream.return_value = iter(chunks)

    orch = ComparisonOrchestrator(genai_client=mock_client, model="gemini-3.5-flash-lite")
    matrix = []
    events = list(
        orch.stream_synthesize_comparison_with_llm(
            products, matrix, query="Compare MacBook Air and Dell XPS 13"
        )
    )

    chunk_events = [e for e in events if e["event"] == "synthesis_chunk"]
    complete_events = [e for e in events if e["event"] == "synthesis_complete"]
    assert len(chunk_events) >= 2
    assert len(complete_events) == 1
    assert "[SKU: 6534606]" in complete_events[0]["summary"]
    assert "[SKU: 6534606]" in complete_events[0]["recommendations"]
    assert len(matrix) > 0
    assert orch.last_input_tokens == 120
    assert orch.last_output_tokens == 45


def test_stream_synthesize_comparison_fallback_when_generate_content_stream_missing():
    """Verify fallback to client.models.generate_content if stream method is not present."""
    products = _sample_products()
    mock_client = MagicMock(spec=["models"])
    mock_client.models = MagicMock(spec=["generate_content"])
    mock_client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps(
            {
                "summary": "Apple MacBook Air [SKU: 6534606] vs Dell XPS 13 [SKU: 6575132].",
                "recommendations": "Best value: Apple MacBook Air [SKU: 6534606].",
            }
        ),
        usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=40),
        candidates=[SimpleNamespace(finish_reason="STOP")],
        prompt_feedback=None,
    )

    orch = ComparisonOrchestrator(genai_client=mock_client, model="gemini-3.5-flash-lite")
    matrix = []
    events = list(
        orch.stream_synthesize_comparison_with_llm(
            products, matrix, query="Compare MacBook and XPS"
        )
    )

    assert any(e["event"] == "synthesis_chunk" for e in events)
    complete = [e for e in events if e["event"] == "synthesis_complete"][0]
    assert "[SKU: 6534606]" in complete["summary"]


def test_stream_synthesize_comparison_with_parallel_matrix_winners():
    """Verify matrix_updated event is emitted when speculative preference winner LLM resolves."""
    products = _sample_products()
    mock_client = MagicMock()
    chunks = [
        SimpleNamespace(
            text='{"summary": "MacBook Air [SKU: 6534606] for battery.", ',
            usage_metadata=None,
            candidates=[],
            prompt_feedback=None,
        ),
        SimpleNamespace(
            text='"recommendations": "Best for travel: MacBook Air [SKU: 6534606]"}',
            usage_metadata=SimpleNamespace(prompt_token_count=110, candidates_token_count=35),
            candidates=[SimpleNamespace(finish_reason="STOP")],
            prompt_feedback=None,
        ),
    ]
    mock_client.models.generate_content_stream.return_value = iter(chunks)
    mock_client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps({"spec_winners": {"battery_life_hours": "6534606"}}),
        usage_metadata=SimpleNamespace(prompt_token_count=50, candidates_token_count=15),
        candidates=[SimpleNamespace(finish_reason="STOP")],
        prompt_feedback=None,
    )

    orch = ComparisonOrchestrator(genai_client=mock_client, model="gemini-3.5-flash-lite")
    matrix = []
    # Query with preference keyword "for travel"
    events = list(
        orch.stream_synthesize_comparison_with_llm(
            products, matrix, query="Compare MacBook Air and Dell XPS 13 for travel"
        )
    )

    event_types = [e["event"] for e in events]
    assert "synthesis_chunk" in event_types
    assert "matrix_updated" in event_types
    assert "synthesis_complete" in event_types
    matrix_update = [e for e in events if e["event"] == "matrix_updated"][0]
    assert len(matrix_update["comparison_matrix"]) > 0


def test_stream_synthesize_comparison_model_armor_security_violation():
    """Verify SecurityViolationError is raised when Model Armor blocks output during streaming."""
    products = _sample_products()
    mock_client = MagicMock()
    chunks = [
        SimpleNamespace(
            text='{"summary": "Suspicious payload',
            usage_metadata=None,
            candidates=[SimpleNamespace(finish_reason="MODEL_ARMOR")],
            prompt_feedback=None,
        )
    ]
    mock_client.models.generate_content_stream.return_value = iter(chunks)

    orch = ComparisonOrchestrator(genai_client=mock_client, model="gemini-3.5-flash-lite")
    matrix = []
    with pytest.raises(SecurityViolationError):
        list(orch.stream_synthesize_comparison_with_llm(products, matrix, query="Malicious attack"))


# ---------------------------------------------------------------------------
# 3. MultiAgentCoordinator & ReasoningEngine Streaming Tests
# ---------------------------------------------------------------------------

_MOCK_RETRIEVED_RECORDS = [
    {
        "sku": "6534606",
        "name": 'Apple - MacBook Air 13.6" Laptop - M3',
        "price": 1099.0,
        "brand": "Apple",
        "category": "Laptops",
        "specifications": {"ram_gb": 16, "battery_life_hours": 18.0},
    },
    {
        "sku": "6575132",
        "name": 'Dell - XPS 13" Laptop - Intel Core Ultra 7',
        "price": 1199.0,
        "brand": "Dell",
        "category": "Laptops",
        "specifications": {"ram_gb": 16, "battery_life_hours": 14.0},
    },
]


@patch("app.agent.multi_agent.query_catalog")
def test_multi_agent_coordinator_execute_stream_yields_matrix_ready_then_chunks(
    mock_qc,
):
    mock_qc.return_value = _MOCK_RETRIEVED_RECORDS
    coord = MultiAgentCoordinator(model="stage-optimal")
    events = list(
        coord.execute_stream(
            raw_query="Compare Apple MacBook Air M3 [SKU: 6534606] and Dell XPS 13 [SKU: 6575132]",
            category="Laptops",
            session_id="test-stream-sess",
        )
    )
    event_types = [e["event"] for e in events]
    assert event_types[0] == "matrix_ready"
    assert "complete" in event_types
    matrix_event = events[0]
    assert len(matrix_event["products"]) >= 2
    assert len(matrix_event["comparison_matrix"]) > 0
    complete_event = [e for e in events if e["event"] == "complete"][0]
    assert complete_event["data"]["summary"]
    assert complete_event["data"]["comparison_matrix"]


@patch("app.agent.multi_agent.query_catalog")
def test_reasoning_engine_stream_query_yields_live_events(mock_qc):
    mock_qc.return_value = _MOCK_RETRIEVED_RECORDS
    engine = CatalogComparisonReasoningEngine()
    engine._coordinator = MultiAgentCoordinator(model="stage-optimal")
    events = list(
        engine.stream_query(
            query="Compare Apple MacBook Air M3 [SKU: 6534606] and Dell XPS 13 [SKU: 6575132]",
            category="Laptops",
        )
    )
    assert len(events) >= 2
    # Verify backward compatibility event_type: comparison_completed is emitted at end
    last_event = events[-1]
    assert (
        last_event.get("event") == "complete"
        or last_event.get("event_type") == "comparison_completed"
    )


# ---------------------------------------------------------------------------
# 4. FastAPI SSE Endpoint (/api/compare/stream) Tests
# ---------------------------------------------------------------------------


@patch("app.agent.multi_agent.query_catalog")
def test_compare_stream_sse_endpoint_returns_event_stream(mock_qc):
    mock_qc.return_value = _MOCK_RETRIEVED_RECORDS
    client = TestClient(app)
    resp = client.post(
        "/api/compare/stream",
        json={
            "query": "Compare Apple MacBook Air M3 [SKU: 6534606] and Dell XPS 13 [SKU: 6575132]",
            "category": "Laptops",
            "session_id": "sse-test-1",
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data: ")]
    assert len(lines) >= 2
    first_payload = json.loads(lines[0][len("data: ") :])
    last_payload = json.loads(lines[-1][len("data: ") :])
    assert first_payload["event"] == "matrix_ready"
    assert last_payload["event"] == "complete"
    assert len(first_payload["products"]) >= 2
    assert last_payload["data"]["summary"]


def test_compare_stream_sse_endpoint_empty_query():
    client = TestClient(app)
    resp = client.post(
        "/api/compare/stream",
        json={"query": "   "},
    )
    assert resp.status_code == 400
    assert "must not be empty" in resp.text
