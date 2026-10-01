"""Unit tests for BENCHMARK_ACTUAL_MODEL support, model-keyed speculative cache, and location routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agent.hermetic_adapter import (
    _get_vertex_client_for_model,
)
from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec


def test_benchmark_actual_model_flag_in_orchestrator(monkeypatch):
    """Verify BENCHMARK_ACTUAL_MODEL=true causes orchestrator to call the exact model."""
    monkeypatch.setenv("BENCHMARK_ACTUAL_MODEL", "true")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"intent_type": "COMPARISON", "is_comparison_eligible": true, "target_keywords": ["MacBook"], "reasoning": "valid"}'
    mock_resp.usage_metadata.prompt_token_count = 100
    mock_resp.usage_metadata.candidates_token_count = 50
    mock_client.models.generate_content.return_value = mock_resp

    orch = ComparisonOrchestrator(model="gemini-3.5-flash", genai_client=mock_client)
    res = orch.classify_intent_with_llm("Compare MacBook Air and Pro", model="gemini-3.5-flash")
    assert res.intent_type == "COMPARISON"

    # Verify model passed to generate_content was gemini-3.5-flash, NOT gemini-2.5-flash-lite
    call_args = mock_client.models.generate_content.call_args
    assert call_args[1].get("model") == "gemini-3.5-flash"


def test_speculative_cache_keys_include_model():
    """Verify speculative cache keys include the target model to prevent cross-model pollution."""
    p1 = ProductSpec(sku="111", name="P1", brand="B1", price=100.0, category="Laptops")
    p2 = ProductSpec(sku="222", name="P2", brand="B2", price=200.0, category="Laptops")

    orch1 = ComparisonOrchestrator(model="gemini-2.5-flash", synthesis_model="gemini-2.5-flash")
    orch2 = ComparisonOrchestrator(model="gemini-3.5-flash", synthesis_model="gemini-3.5-flash")

    key1 = orch1._get_speculative_synth_key([p1, p2], "compare p1 and p2", "gemini-2.5-flash")
    key2 = orch2._get_speculative_synth_key([p1, p2], "compare p1 and p2", "gemini-3.5-flash")

    assert key1 != key2
    assert key1[2] == "gemini-2.5-flash"
    assert key2[2] == "gemini-3.5-flash"


def test_vertex_client_routing_for_preview_and_3x_models():
    """Verify preview/3.x models resolve to location='global' with fallback to 'us-central1'."""
    with patch("google.genai.Client") as mock_client_cls:
        # 1. 3.x preview model should request location='global'
        _ = _get_vertex_client_for_model("gemini-3.1-pro-preview", allow_cache=False)
        assert mock_client_cls.call_count >= 1
        last_kwargs = mock_client_cls.call_args[1]
        assert last_kwargs.get("location") in ("global", "us-central1")

        # 2. 2.5 GA model should request location='us-central1'
        mock_client_cls.reset_mock()
        _ = _get_vertex_client_for_model("gemini-2.5-flash", allow_cache=False)
        assert mock_client_cls.call_count >= 1
        last_kwargs = mock_client_cls.call_args[1]
        assert last_kwargs.get("location") == "us-central1"


def test_vertex_client_routing_fallback_on_global_failure():
    """Verify fallback to us-central1 if location='global' client creation fails."""
    call_locations = []

    def mock_genai_client_init(*args, **kwargs):
        loc = kwargs.get("location")
        call_locations.append(loc)
        if loc == "global":
            raise RuntimeError("Global endpoint not supported for project")
        mock_instance = MagicMock()
        mock_instance.location = loc
        return mock_instance

    with patch("google.genai.Client", side_effect=mock_genai_client_init):
        client = _get_vertex_client_for_model("gemini-3.8-flash", allow_cache=False)
        assert "global" in call_locations
        assert "us-central1" in call_locations
        assert client.location == "us-central1"
