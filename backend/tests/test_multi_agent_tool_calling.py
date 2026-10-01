"""Unit tests for deterministic CatalogRetrievalStep and 3-agent SequentialAgent pipeline."""

from __future__ import annotations

from unittest.mock import patch

from app.agent.multi_agent import (
    CatalogRetrievalAgent,
    CatalogRetrievalStep,
    ComparisonAgentState,
    MultiAgentCoordinator,
)


def test_catalog_retrieval_step_pure_deterministic_sql():
    """Verify CatalogRetrievalStep has no adk_agent, model, or LLM tool-calling methods."""
    step = CatalogRetrievalStep()
    assert not hasattr(step, "adk_agent"), (
        "CatalogRetrievalStep must not instantiate an ADK LLM agent"
    )
    assert not hasattr(step, "model"), "CatalogRetrievalStep must not have a model attribute"
    assert not hasattr(step, "use_llm_tool_call"), (
        "CatalogRetrievalStep must not support use_llm_tool_call"
    )
    assert not hasattr(step, "process_with_llm_tool_call"), (
        "CatalogRetrievalStep must not define process_with_llm_tool_call"
    )


def test_catalog_retrieval_agent_alias_compatibility():
    """Verify CatalogRetrievalAgent is an alias to CatalogRetrievalStep for backward compatibility."""
    assert CatalogRetrievalAgent is CatalogRetrievalStep


@patch("app.agent.multi_agent.query_catalog")
def test_catalog_retrieval_step_execution(mock_query_catalog):
    """Verify standard deterministic path calls query_catalog directly and deduplicates SKUs."""
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
            "sku": "6534606",  # duplicate SKU
            "name": "Apple MacBook Air 15 - Duplicate",
            "price": 1299.0,
            "brand": "Apple",
            "category": "Laptops",
            "specifications": {"ram_gb": 16, "battery_life_hours": 18.0},
        },
    ]
    step = CatalogRetrievalStep()
    state = ComparisonAgentState(
        raw_query="MacBook Air vs Dell XPS",
        target_keywords=["MacBook Air", "Dell XPS"],
        detected_category="Laptops",
        is_comparison_eligible=True,
    )
    result = step.process(state)
    assert len(result.retrieved_products) == 1
    assert result.retrieved_products[0].sku == "6534606"
    assert result.step_history[-1]["status"] == "COMPLETED"
    assert result.step_history[-1]["agent"] in ("CatalogRetrievalStep", "CatalogRetrievalAgent")
    assert result.step_history[-1]["products_retrieved"] == 1


def test_catalog_retrieval_step_skipped_for_non_comparison():
    """Verify retrieval is skipped when query is non-comparison."""
    step = CatalogRetrievalStep()
    state = ComparisonAgentState(
        raw_query="These laptops suck",
        is_comparison_eligible=False,
    )
    result = step.process(state)
    assert len(result.retrieved_products) == 0
    assert result.step_history[-1]["status"] == "SKIPPED"


def test_sequential_agent_only_contains_three_llm_agents():
    """Verify SequentialAgent contains ONLY the 3 real LLM specialist agents."""
    coordinator = MultiAgentCoordinator()
    sub_agent_names = [agent.name for agent in coordinator.adk_sequential_agent.sub_agents]
    assert len(sub_agent_names) == 3, (
        f"Expected 3 sub-agents, got {len(sub_agent_names)}: {sub_agent_names}"
    )
    assert "query_intent_specialist" in sub_agent_names
    assert "relevance_detector_specialist" in sub_agent_names
    assert "spec_comparison_specialist" in sub_agent_names
    assert "catalog_retrieval_specialist" not in sub_agent_names


def test_multi_agent_coordinator_deterministic_retrieval_integration():
    """Verify MultiAgentCoordinator routes through deterministic retrieval step seamlessly."""
    coordinator = MultiAgentCoordinator()
    assert isinstance(coordinator.retrieval_agent, CatalogRetrievalStep)

    with (
        patch.object(coordinator.intent_agent, "process", side_effect=lambda s: s),
        patch.object(coordinator.retrieval_agent, "process") as mock_retrieval,
        patch.object(coordinator.relevance_agent, "process", side_effect=lambda s: s),
        patch.object(coordinator.comparison_agent, "process", side_effect=lambda s: s),
    ):
        mock_retrieval.side_effect = lambda s, **kwargs: s
        coordinator.execute("Compare MacBook and XPS")
        mock_retrieval.assert_called_once()


def test_build_thinking_config_coverage():
    """Verify _build_thinking_config correctly returns ThinkingConfig or None based on model family."""
    from app.agent.orchestrator import _build_thinking_config

    assert _build_thinking_config(None) is None
    assert _build_thinking_config("") is None
    # 2.5-flash / 2.0-flash allow thinking_budget=0
    cfg_25 = _build_thinking_config("gemini-2.5-flash")
    assert cfg_25 is not None
    assert getattr(cfg_25, "thinking_budget", None) == 0

    cfg_20 = _build_thinking_config("gemini-2.0-flash")
    assert cfg_20 is not None
    assert getattr(cfg_20, "thinking_budget", None) == 0

    # 3.x, pro, 1.5, and flash-lite reject thinking_budget=0
    assert _build_thinking_config("gemini-3.5-flash") is None
    assert _build_thinking_config("gemini-3.6-flash") is None
    assert _build_thinking_config("gemini-3.7-flash") is None
    assert _build_thinking_config("gemini-3.8-flash") is None
    assert _build_thinking_config("gemini-2.5-flash-lite") is None
    assert _build_thinking_config("gemini-3.1-flash-lite") is None
    assert _build_thinking_config("gemini-2.5-pro") is None
    assert _build_thinking_config("gemini-1.5-flash") is None


def test_extract_json_snippet_coverage():
    """Verify _extract_json_snippet extracts JSON objects and arrays from diverse response formats."""
    from app.agent.orchestrator import _extract_json_snippet

    assert _extract_json_snippet("") == ""
    assert _extract_json_snippet(None) == ""

    # Markdown code fences with json tag
    fence_json = '```json\n{"intent_type": "COMPARISON"}\n```'
    assert _extract_json_snippet(fence_json) == '{"intent_type": "COMPARISON"}'

    # Markdown code fences without json tag
    fence_raw = '```\n[{"sku": "123", "score": 10}]\n```'
    assert _extract_json_snippet(fence_raw) == '[{"sku": "123", "score": 10}]'

    # Conversational lead-in and sign-off
    conversational = 'Here is the analysis:\n{"intent_type": "PRODUCT_SEARCH"}\nHope this helps!'
    assert _extract_json_snippet(conversational) == '{"intent_type": "PRODUCT_SEARCH"}'

    # Conversational array
    conv_array = "Rankings below:\n[1, 2, 3]\nDone."
    assert _extract_json_snippet(conv_array) == "[1, 2, 3]"

    # Already valid clean JSON
    clean = '{"a": 1, "b": 2}'
    assert _extract_json_snippet(clean) == clean

    # Plain text without brackets
    plain = "No JSON here whatsoever."
    assert _extract_json_snippet(plain) == plain


def test_orchestrator_opinion_and_model_helpers():
    """Verify orchestrator opinion detection and model resolution branches."""
    from app.agent.orchestrator import ComparisonOrchestrator, resolve_model_pair

    orch = ComparisonOrchestrator()
    assert orch._is_opinion_query("") is True
    assert orch._is_opinion_query("This product is stupid") is True
    assert orch._is_opinion_query("I hate this terrible thing") is True
    assert orch._is_opinion_query("Compare MacBook and XPS") is False

    r, s, is_hybrid = resolve_model_pair(model="tiered-hybrid")
    assert r == "gemini-2.5-flash"
    assert s == "gemini-2.5-pro"
    assert is_hybrid is True

    r2, s2, is_hybrid2 = resolve_model_pair(
        model="gemini-2.5-flash-lite", synthesis_model="gemini-2.5-flash-lite"
    )
    assert r2 == "gemini-2.5-flash-lite"
    assert s2 == "gemini-2.5-flash-lite"
    assert is_hybrid2 is False


def test_orchestrator_extraction_and_speculative_helpers():
    """Verify orchestrator keyword extraction, tagged extraction, and speculative keys."""
    from app.agent.orchestrator import ComparisonOrchestrator
    from app.models.responses import ProductSpec

    orch = ComparisonOrchestrator()

    # extract_tagged_products
    assert orch.extract_tagged_products("") == []
    tagged1 = orch.extract_tagged_products(
        "Product 1: MacBook Pro (Apple) [SKU: 6534606] vs Product 2: Dell XPS 13 [SKU: 6543210]"
    )
    assert len(tagged1) == 2
    assert tagged1[0] == ("MacBook Pro", "6534606")
    assert tagged1[1] == ("Dell XPS 13", "6543210")

    tagged2 = orch.extract_tagged_products(
        "Compare MacBook Pro [SKU: 6534606] and Dell XPS [SKU: 6543210]"
    )
    assert len(tagged2) == 2

    tagged3 = orch.extract_tagged_products("[SKU: 6534606]")
    assert tagged3 == [("", "6534606")]

    # extract_keywords
    kw1 = orch.extract_keywords(
        "Product 1: MacBook Pro [SKU: 6534606] vs Product 2: Dell XPS [SKU: 6543210]"
    )
    assert "MacBook Pro" in kw1

    kw2 = orch.extract_keywords("Compare MacBook Air and Dell XPS 13")
    assert any("MacBook" in k for k in kw2)

    kw3 = orch.extract_keywords("Price breakdown: Sony WH-1000XM5 vs Bose QC45")
    assert any("Sony" in k for k in kw3)

    # _get_speculative_synth_key / _get_speculative_rerank_key
    prod1 = ProductSpec(
        sku="111", name="Product A", brand="Brand A", category="Laptops", price=999.0
    )
    prod2 = ProductSpec(
        sku="222", name="Product B", brand="Brand B", category="Laptops", price=1299.0
    )
    synth_key = orch._get_speculative_synth_key([prod2, prod1], "Compare A and B")
    assert synth_key[0] == ("111", "222")

    rerank_key = orch._get_speculative_rerank_key([prod2, prod1], "Compare A and B")
    assert rerank_key[0] == ("111", "222")


def test_orchestrator_build_comparison_matrix():
    """Verify build_comparison_matrix aligns specifications and computes winners."""
    from app.agent.orchestrator import ComparisonOrchestrator
    from app.models.responses import ProductSpec

    orch = ComparisonOrchestrator()
    assert orch.build_comparison_matrix([]) == []

    p1 = ProductSpec(
        sku="1001",
        name="MacBook Air M3",
        brand="Apple",
        category="Laptops",
        price=1099.0,
        rating=4.8,
        review_count=120,
        specifications={"ram_gb": 16, "storage_gb": 512, "battery_life_hours": 18},
    )
    p2 = ProductSpec(
        sku="1002",
        name="Dell XPS 13",
        brand="Dell",
        category="Laptops",
        price=1299.0,
        rating=4.5,
        review_count=85,
        specifications={"ram_gb": 16, "storage_gb": 512, "battery_life_hours": 12},
    )

    rows = orch.build_comparison_matrix([p1, p2])
    assert len(rows) > 0
    features = [r.feature for r in rows]
    assert "Price" in features
    assert "Customer Rating" in features

    # Price winner should be p1 (cheaper)
    price_row = next(r for r in rows if r.feature == "Price")
    assert price_row.winner_sku == "1001"

    # Only price query
    price_only_rows = orch.build_comparison_matrix([p1, p2], query="only price")
    assert len(price_only_rows) == 1
    assert price_only_rows[0].feature == "Price"


def test_coverage_gap_closers():
    """Targeted coverage tests for edge branches across multi_agent, agent_card, requests, and prompts_service."""
    from unittest.mock import MagicMock, patch

    from app.agent.agent_card import build_a2a_agent_card
    from app.agent.multi_agent import (
        CatalogRetrievalStep,
        ComparisonAgentState,
        MultiAgentCoordinator,
        RelevanceDetectorAgent,
        SpecComparisonAgent,
    )
    from app.agent.prompts_service import get_active_prompt
    from app.models.requests import ComparisonSynthesis
    from app.models.responses import ProductSpec

    # 1. CatalogRetrievalStep with malformed product spec row
    step = CatalogRetrievalStep()
    with patch("app.agent.multi_agent.query_catalog") as mock_query:
        mock_query.return_value = [
            {"sku": "CORRUPT_ITEM_MISSING_FIELDS"},
            {
                "sku": "VALID_1",
                "name": "Test Laptop",
                "brand": "Brand",
                "category": "Laptops",
                "price": 999.0,
            },
        ]
        st = ComparisonAgentState(
            raw_query="compare laptops",
            target_keywords=["laptops"],
            is_comparison_eligible=True,
        )
        out = step.process(st)
        assert len(out.retrieved_products) == 1
        assert out.retrieved_products[0].sku == "VALID_1"

    # 2. RelevanceDetectorAgent with < 2 ranked candidates
    rel_agent = RelevanceDetectorAgent()
    p1 = ProductSpec(sku="1", name="P1", brand="B1", category="Laptops", price=500.0)
    st_rel = ComparisonAgentState(
        raw_query="compare laptops",
        target_keywords=["laptops"],
        is_comparison_eligible=True,
        retrieved_products=[p1],
    )
    with patch.object(rel_agent.orchestrator, "rank_and_select_products", return_value=[p1]):
        out_rel = rel_agent.process(st_rel)
        assert out_rel.is_comparison_eligible is False
        assert len(out_rel.ranked_products) == 1

    # 3. SpecComparisonAgent with single ranked product
    spec_agent = SpecComparisonAgent()
    st_spec = ComparisonAgentState(
        raw_query="macbook",
        is_comparison_eligible=False,
        ranked_products=[p1],
    )
    with patch.object(spec_agent.orchestrator, "synthesize_summary", return_value="Summary for P1"):
        out_spec = spec_agent.process(st_spec)
        assert out_spec.comparison_response is not None
        assert len(out_spec.comparison_response.citations) == 1
        assert out_spec.comparison_response.citations[0].sku == "1"

    # 4. MultiAgentCoordinator with session_id
    coord = MultiAgentCoordinator()
    with patch("app.agent.multi_agent.query_catalog", return_value=[]):
        res = coord.execute("test query", session_id="session-xyz-999")
        assert res is not None

    # 5. build_a2a_agent_card with unregistered flash and non-flash versions
    card_flash = build_a2a_agent_card("https://test.run.app", version="v9.9-flash-canary")
    assert "flash" in card_flash["metadata"]["model"]
    card_pro = build_a2a_agent_card("https://test.run.app", version="v9.9-pro-custom")
    assert card_pro["metadata"]["model"] is not None

    # 6. ComparisonSynthesis validators
    s1 = ComparisonSynthesis(summary=["Part 1", "Part 2"], recommendations=None)
    assert s1.summary == "Part 1 Part 2"
    assert s1.recommendations is None

    s2 = ComparisonSynthesis(summary="Valid", recommendations=["Rec A", "Rec B"])
    assert s2.recommendations == "Rec A\nRec B"

    s3 = ComparisonSynthesis(summary="Valid", recommendations={"Key1": "Val1"})
    assert s3.recommendations == "Key1: Val1"

    # 7. get_active_prompt vertex prompt object with system_instruction attribute
    from app.config import settings

    orig_flag = settings.enable_vertex_prompt_registry
    try:
        settings.enable_vertex_prompt_registry = True
        mock_prompt_obj = MagicMock()
        mock_raw = MagicMock()
        mock_raw.system_instruction = "Custom enterprise instruction"
        mock_prompt_obj.prompt_data = mock_raw
        mock_prompt_obj.version_id = "v42"
        with patch("vertexai.preview.prompts.get", return_value=mock_prompt_obj) as mock_get:
            mock_get.assert_called = MagicMock()  # bypass PYTEST_CURRENT_TEST guard
            inst, ver = get_active_prompt("prompt-custom", "v42")
            assert inst == "Custom enterprise instruction"
            assert ver == "v42"
    finally:
        settings.enable_vertex_prompt_registry = orig_flag

    # 8. reasoning_engine tracing exception handling
    from app.agent.reasoning_engine import CatalogComparisonReasoningEngine

    with patch("app.observability.tracing.setup_tracing", side_effect=RuntimeError("Tracing boom")):
        engine = CatalogComparisonReasoningEngine()
        engine.set_up()
        assert engine._coordinator is not None
