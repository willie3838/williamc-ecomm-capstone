import json

import pytest

from app.agent.hermetic_adapter import HermeticModelAdapter
from app.agent.multi_agent import (
    ComparisonAgentState,
    QueryIntentAgent,
    RelevanceDetectorAgent,
    RelevanceRerankerAgent,
)
from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec

SAMPLE_TAGGED_QUERY = """Compare the following products:
Product 1: Apple MacBook Air 13.6" Laptop (Apple) [SKU: 6534606] - $1099
  Specifications:
  * processor: Apple M3 8-core
  * ram_gb: 16
  * battery_life_hours: Up to 18 hours
Product 2: Dell XPS 13" (Dell) [SKU: 6575132] - $1199
  Specifications:
  * processor: Intel Core Ultra 7
  * ram_gb: 16
  * battery_life_hours: Up to 14 hours
User Focus / Follow-up: good for gaming"""

SAMPLE_GENERIC_FOCUS_QUERY = """Compare the following products:
Product 1: Apple MacBook Air 13.6" Laptop (Apple) [SKU: 6534606] - $1099
  Specifications:
  * processor: Apple M3 8-core
  * ram_gb: 16
  * battery_life_hours: Up to 18 hours
Product 2: Dell XPS 13" (Dell) [SKU: 6575132] - $1199
  Specifications:
  * processor: Intel Core Ultra 7
  * ram_gb: 16
  * battery_life_hours: Up to 14 hours
User Focus / Follow-up: Compare specifications, trade-offs, and recommend the best option."""

SAMPLE_PRICE_FOCUS_QUERY = """Compare the following products:
Product 1: Apple MacBook Air 13.6" Laptop (Apple) [SKU: 6534606] - $1099
  Specifications:
  * processor: Apple M3 8-core
  * ram_gb: 16
  * battery_life_hours: Up to 18 hours
Product 2: Dell XPS 13" (Dell) [SKU: 6575132] - $1199
  Specifications:
  * processor: Intel Core Ultra 7
  * ram_gb: 16
  * battery_life_hours: Up to 14 hours
User Focus / Follow-up: only price"""


@pytest.fixture
def sample_products() -> list[ProductSpec]:
    p1 = ProductSpec(
        sku="6534606",
        name='Apple MacBook Air 13.6" Laptop',
        brand="Apple",
        category="Laptops",
        price=1099.0,
        rating=4.8,
        specifications={
            "processor": "Apple M3 8-core",
            "ram_gb": 16,
            "battery_life_hours": 18,
            "display_size_in": 13.6,
            "refresh_rate_hz": 60,
        },
    )
    p2 = ProductSpec(
        sku="6575132",
        name='Dell XPS 13"',
        brand="Dell",
        category="Laptops",
        price=1199.0,
        rating=4.5,
        specifications={
            "processor": "Intel Core Ultra 7",
            "ram_gb": 16,
            "battery_life_hours": 14,
            "display_size_in": 13.4,
            "refresh_rate_hz": 120,
        },
    )
    # Gaming distractor candidate that would normally rank higher for "gaming"
    p3 = ProductSpec(
        sku="9999999",
        name="ASUS ROG Zephyrus G16 Gaming Laptop",
        brand="ASUS",
        category="Laptops",
        price=1999.0,
        rating=4.9,
        specifications={
            "processor": "Intel Core Ultra 9",
            "ram_gb": 32,
            "battery_life_hours": 8,
            "refresh_rate_hz": 240,
        },
    )
    return [p1, p2, p3]


def test_extract_keywords_from_build_comparison_prompt():
    """Verify only product names are extracted from tagged query, ignoring specs and follow-up."""
    keywords = ComparisonOrchestrator.extract_keywords(SAMPLE_TAGGED_QUERY)
    assert len(keywords) == 2
    assert 'Apple MacBook Air 13.6" Laptop' in keywords
    assert 'Dell XPS 13"' in keywords
    # Ensure specs and follow-up are NOT present in keywords
    assert not any("battery" in kw.lower() for kw in keywords)
    assert not any("gaming" in kw.lower() for kw in keywords)
    assert not any("processor" in kw.lower() for kw in keywords)


def test_extract_keywords_with_inline_sku_tags():
    """Verify inline [SKU: ...] queries extract clean product names."""
    query = "Compare Apple MacBook Air [SKU: 6534606] vs Dell XPS 13 [SKU: 6575132]"
    keywords = ComparisonOrchestrator.extract_keywords(query)
    assert len(keywords) == 2
    assert any("MacBook Air" in kw for kw in keywords)
    assert any("Dell XPS 13" in kw for kw in keywords)


def test_rank_and_select_locks_on_tagged_skus_ignoring_gaming_distractor(sample_products):
    """Verify rank_and_select_products locks onto tagged SKUs (6534606, 6575132) despite gaming follow-up."""
    orch = ComparisonOrchestrator()
    keywords = ['Apple MacBook Air 13.6" Laptop', 'Dell XPS 13"']
    ranked = orch.rank_and_select_products(
        sample_products,
        keywords,
        original_query=SAMPLE_TAGGED_QUERY,
    )
    assert len(ranked) == 2
    ranked_skus = [p.sku for p in ranked]
    assert ranked_skus == ["6534606", "6575132"]
    assert "9999999" not in ranked_skus

    # Verify alias rank_and_select_candidates exists and behaves identically
    ranked_via_alias = orch.rank_and_select_candidates(
        sample_products,
        keywords,
        original_query=SAMPLE_TAGGED_QUERY,
    )
    assert [p.sku for p in ranked_via_alias] == ["6534606", "6575132"]


def test_build_comparison_matrix_extracts_user_focus_without_body_false_triggers(sample_products):
    """Verify prompt body specs do not false-trigger battery life prioritization."""
    orch = ComparisonOrchestrator()
    products = sample_products[:2]

    # Case 1: Generic follow-up. Even though body contains 'battery_life_hours',
    # focus should NOT be set to battery life.
    generic_matrix = orch.build_comparison_matrix(products, query=SAMPLE_GENERIC_FOCUS_QUERY)
    feature_names = [row.feature for row in generic_matrix]
    # Price and Customer Rating come first
    assert feature_names[0] == "Price"
    assert feature_names[1] == "Customer Rating"
    # When no focus query is specified, technical specs follow registry insertion order (Processor / CPU first)
    assert feature_names[2] == "Processor / CPU"

    # Case 2: Follow-up is 'only price' -> only Price row returned
    price_matrix = orch.build_comparison_matrix(products, query=SAMPLE_PRICE_FOCUS_QUERY)
    assert len(price_matrix) == 1
    assert price_matrix[0].feature == "Price"

    # Case 3: Follow-up is 'good for gaming' -> gaming specs (Refresh Rate) prioritized
    gaming_matrix = orch.build_comparison_matrix(products, query=SAMPLE_TAGGED_QUERY)
    gaming_features = [row.feature for row in gaming_matrix]
    # Refresh Rate should be prioritized among technical specs (before Processor)
    refresh_idx = gaming_features.index("Refresh Rate")
    processor_idx = gaming_features.index("Processor / CPU")
    assert refresh_idx < processor_idx


def test_relevance_detector_agent_locks_tagged_skus(sample_products):
    """Verify RelevanceDetectorAgent (and alias RelevanceRerankerAgent) locks onto tagged SKUs."""
    agent = RelevanceDetectorAgent()
    assert RelevanceRerankerAgent is RelevanceDetectorAgent

    state = ComparisonAgentState(
        raw_query=SAMPLE_TAGGED_QUERY,
        sanitized_query=SAMPLE_TAGGED_QUERY,
        intent_type="COMPARISON",
        is_comparison_eligible=True,
        target_keywords=['Apple MacBook Air 13.6" Laptop', 'Dell XPS 13"'],
        retrieved_products=sample_products,
    )

    processed_state = agent.process(state)
    assert len(processed_state.ranked_products) == 2
    assert [p.sku for p in processed_state.ranked_products] == ["6534606", "6575132"]
    assert "9999999" not in [p.sku for p in processed_state.ranked_products]


def test_query_intent_agent_extracts_tagged_keywords():
    """Verify QueryIntentAgent extracts only product names when given a tagged query."""
    intent_agent = QueryIntentAgent()
    state = ComparisonAgentState(raw_query=SAMPLE_TAGGED_QUERY)
    processed = intent_agent.process(state)
    assert processed.intent_type == "COMPARISON"
    assert processed.is_comparison_eligible is True
    assert 'Apple MacBook Air 13.6" Laptop' in processed.target_keywords
    assert 'Dell XPS 13"' in processed.target_keywords
    assert not any("battery" in kw.lower() for kw in processed.target_keywords)


def test_hermetic_adapter_rerank_and_synthesis_respects_tagged_skus_and_focus():
    """Verify HermeticModelAdapter isolates user focus and reranks tagged SKUs."""
    # Test rerank response locks onto tagged SKUs
    prompt_with_candidates = f"""<user_query>{SAMPLE_TAGGED_QUERY}</user_query>
Candidates:
- SKU: 6534606 | Apple MacBook Air 13.6" Laptop | Brand: Apple | Category: Laptops | Price: $1099
- SKU: 9999999 | ASUS ROG Zephyrus G16 Gaming Laptop | Brand: ASUS | Category: Laptops | Price: $1999
- SKU: 6575132 | Dell XPS 13" | Brand: Dell | Category: Laptops | Price: $1199"""

    rerank_json = HermeticModelAdapter.rerank_response(prompt_with_candidates)
    data = json.loads(rerank_json)
    skus = [item["sku"] for item in data["rankings"]]
    # Tagged SKUs should be ranked top
    assert skus[0] in ("6534606", "6575132")
    assert skus[1] in ("6534606", "6575132")


def test_app_agent_exports_relevance_reranker_agent():
    """Verify app.agent exports RelevanceDetectorAgent and RelevanceRerankerAgent."""
    import app.agent as agent_pkg

    assert hasattr(agent_pkg, "RelevanceDetectorAgent")
    assert hasattr(agent_pkg, "RelevanceRerankerAgent")
    assert agent_pkg.RelevanceRerankerAgent is agent_pkg.RelevanceDetectorAgent
