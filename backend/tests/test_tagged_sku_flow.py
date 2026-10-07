import pytest

from app.agent.multi_agent import (
    CatalogRetrievalStep,
    ComparisonAgentState,
    QueryIntentAgent,
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


def test_compare_and_retrieval_step_lock_on_tagged_skus_ignoring_gaming_distractor(
    sample_products, monkeypatch
):
    """Verify CatalogRetrievalStep and compare() lock onto tagged SKUs (6534606, 6575132) despite gaming follow-up."""
    from unittest.mock import patch

    import app.agent.orchestrator as orch_mod

    step = CatalogRetrievalStep()
    state = ComparisonAgentState(
        raw_query=SAMPLE_TAGGED_QUERY,
        sanitized_query=SAMPLE_TAGGED_QUERY,
        intent_type="COMPARISON",
        is_comparison_eligible=True,
        target_keywords=['Apple MacBook Air 13.6" Laptop', 'Dell XPS 13"'],
    )
    with patch(
        "app.agent.multi_agent.query_catalog",
        return_value=[p.model_dump() for p in sample_products],
    ):
        processed_state = step.process(state)
    assert len(processed_state.retrieved_products) >= 2
    retrieved_skus = [p.sku for p in processed_state.retrieved_products[:2]]
    assert retrieved_skus == ["6534606", "6575132"]
    assert "9999999" not in retrieved_skus

    orch = ComparisonOrchestrator()
    monkeypatch.setattr(
        orch_mod,
        "query_catalog",
        lambda **kwargs: [p.model_dump() for p in sample_products],
    )
    resp = orch.compare(SAMPLE_TAGGED_QUERY, category="Laptops")
    assert [p.sku for p in resp.products] == ["6534606", "6575132"]


def test_build_comparison_matrix_extracts_user_focus_without_body_false_triggers(sample_products):
    """Verify prompt body specs do not false-trigger battery life prioritization."""
    orch = ComparisonOrchestrator()
    products = sample_products[:2]

    # Case 1: Generic follow-up. Even though body contains 'battery_life_hours',
    # focus should NOT be set to battery life.
    generic_matrix = orch.build_comparison_matrix(products, query=SAMPLE_GENERIC_FOCUS_QUERY)
    feature_names = [row.feature for row in generic_matrix]
    assert feature_names[0] == "Price"
    assert feature_names[1] == "Customer Rating"
    assert feature_names[2] == "Processor / CPU"

    # Case 2: Follow-up is 'only price' -> only Price row returned
    price_matrix = orch.build_comparison_matrix(products, query=SAMPLE_PRICE_FOCUS_QUERY)
    assert len(price_matrix) == 1
    assert price_matrix[0].feature == "Price"

    # Case 3: Follow-up is 'good for gaming' -> gaming specs (Refresh Rate) prioritized
    gaming_matrix = orch.build_comparison_matrix(products, query=SAMPLE_TAGGED_QUERY)
    gaming_features = [row.feature for row in gaming_matrix]
    refresh_idx = gaming_features.index("Refresh Rate")
    processor_idx = gaming_features.index("Processor / CPU")
    assert refresh_idx < processor_idx


def test_catalog_retrieval_step_locks_tagged_skus(sample_products):
    """Verify CatalogRetrievalStep locks onto tagged SKUs and preserves order."""
    from unittest.mock import patch

    step = CatalogRetrievalStep()

    state = ComparisonAgentState(
        raw_query=SAMPLE_TAGGED_QUERY,
        sanitized_query=SAMPLE_TAGGED_QUERY,
        intent_type="COMPARISON",
        is_comparison_eligible=True,
        target_keywords=['Apple MacBook Air 13.6" Laptop', 'Dell XPS 13"'],
    )

    with patch(
        "app.agent.multi_agent.query_catalog",
        return_value=[p.model_dump() for p in sample_products],
    ):
        processed_state = step.process(state)
    assert len(processed_state.retrieved_products) >= 2
    assert [p.sku for p in processed_state.retrieved_products[:2]] == ["6534606", "6575132"]
    assert "9999999" not in [p.sku for p in processed_state.retrieved_products[:2]]


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


def test_app_agent_does_not_export_relevance_detector_agent():
    """Verify app.agent no longer exports RelevanceDetectorAgent or RelevanceRerankerAgent."""
    import app.agent as agent_pkg

    assert not hasattr(agent_pkg, "RelevanceDetectorAgent")
    assert not hasattr(agent_pkg, "RelevanceRerankerAgent")


def test_catalog_retrieval_step_supports_up_to_5_tagged_skus():
    """Verify CatalogRetrievalStep returns up to 5 tagged products in click order."""
    from unittest.mock import patch

    step = CatalogRetrievalStep()
    prods = [
        ProductSpec(
            sku=f"SKU00{i}",
            name=f"Laptop Model {i}",
            brand=f"Brand{i}",
            category="Laptops",
            price=1000.0 + i * 100,
        )
        for i in range(1, 7)
    ]
    # 3 tagged SKUs
    query_3 = "Compare: [SKU: SKU001] vs [SKU: SKU002] vs [SKU: SKU003]"
    state_3 = ComparisonAgentState(
        raw_query=query_3,
        sanitized_query=query_3,
        target_keywords=["Laptop Model 1", "Laptop Model 2", "Laptop Model 3"],
    )
    with patch(
        "app.agent.multi_agent.query_catalog",
        return_value=[p.model_dump() for p in prods],
    ):
        res_3 = step.process(state_3)
    assert len(res_3.retrieved_products[:3]) == 3
    assert [p.sku for p in res_3.retrieved_products[:3]] == ["SKU001", "SKU002", "SKU003"]

    # 4 tagged SKUs
    query_4 = "Compare: [SKU: SKU001], [SKU: SKU002], [SKU: SKU003], [SKU: SKU004]"
    state_4 = ComparisonAgentState(
        raw_query=query_4,
        sanitized_query=query_4,
        target_keywords=["Model 1", "Model 2", "Model 3", "Model 4"],
    )
    with patch(
        "app.agent.multi_agent.query_catalog",
        return_value=[p.model_dump() for p in prods],
    ):
        res_4 = step.process(state_4)
    assert len(res_4.retrieved_products[:4]) == 4
    assert [p.sku for p in res_4.retrieved_products[:4]] == ["SKU001", "SKU002", "SKU003", "SKU004"]

    # 5 tagged SKUs
    query_5 = "Compare: [SKU: SKU001], [SKU: SKU002], [SKU: SKU003], [SKU: SKU004], [SKU: SKU005]"
    state_5 = ComparisonAgentState(
        raw_query=query_5,
        sanitized_query=query_5,
        target_keywords=["Model 1", "Model 2", "Model 3", "Model 4", "Model 5"],
    )
    with patch(
        "app.agent.multi_agent.query_catalog",
        return_value=[p.model_dump() for p in prods],
    ):
        res_5 = step.process(state_5)
    assert len(res_5.retrieved_products[:5]) == 5
    assert [p.sku for p in res_5.retrieved_products[:5]] == [
        "SKU001",
        "SKU002",
        "SKU003",
        "SKU004",
        "SKU005",
    ]


def test_catalog_retrieval_untagged_multi_product_queries():
    """Verify untagged multi-product queries retrieve catalog products."""
    from unittest.mock import patch

    step = CatalogRetrievalStep()
    prods = [
        ProductSpec(
            sku=f"SKU00{i}",
            name=f"Product {i}",
            brand=f"Brand{i}",
            category="Laptops",
            price=1000.0 + i * 100,
        )
        for i in range(1, 7)
    ]
    for count in (2, 3, 4, 5):
        kw = [f"Brand{i}" for i in range(1, count + 1)]
        state = ComparisonAgentState(
            raw_query="Compare " + ", ".join(kw),
            sanitized_query="Compare " + ", ".join(kw),
            target_keywords=kw,
        )
        with patch(
            "app.agent.multi_agent.query_catalog",
            return_value=[p.model_dump() for p in prods[:count]],
        ):
            res = step.process(state)
        assert len(res.retrieved_products) == count


def test_catalog_retrieval_step_supports_3_4_5_tagged_skus():
    """Verify CatalogRetrievalStep locks onto 3, 4, and 5 tagged SKUs without truncation."""
    from unittest.mock import patch

    step = CatalogRetrievalStep()
    prods = [
        ProductSpec(
            sku=f"SKU00{i}",
            name=f"Laptop Model {i}",
            brand=f"Brand{i}",
            category="Laptops",
            price=1000.0 + i * 100,
        )
        for i in range(1, 6)
    ]
    for count in (3, 4, 5):
        tagged_query = "Compare products: " + ", ".join(
            f"Product {i} [SKU: SKU00{i}]" for i in range(1, count + 1)
        )
        state = ComparisonAgentState(
            raw_query=tagged_query,
            sanitized_query=tagged_query,
            intent_type="COMPARISON",
            is_comparison_eligible=True,
            target_keywords=[f"Model {i}" for i in range(1, count + 1)],
        )
        with patch(
            "app.agent.multi_agent.query_catalog",
            return_value=[p.model_dump() for p in prods],
        ):
            updated = step.process(state)
        assert len(updated.retrieved_products[:count]) == count
        assert [p.sku for p in updated.retrieved_products[:count]] == [
            f"SKU00{i}" for i in range(1, count + 1)
        ]


def test_catalog_retrieval_and_sql_direct_sku_lookup_for_tagged_queries(mock_bq_client):
    """Verify tagged SKU prompts query BigQuery directly via LOWER(sku) IN UNNEST(@product_patterns)."""
    from app.agent.multi_agent import CatalogRetrievalAgent
    from app.tools.catalog import query_catalog

    mock_bq_client.query_and_wait.return_value = [
        {
            "sku": "6534606",
            "name": 'Apple MacBook Air 13.6" Laptop',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "specifications": {"ram_gb": 16},
            "in_stock": True,
        },
        {
            "sku": "6575132",
            "name": 'Dell XPS 13"',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
            "specifications": {"ram_gb": 16},
            "in_stock": True,
        },
    ]

    retrieval_agent = CatalogRetrievalAgent(bq_client=mock_bq_client)
    state = ComparisonAgentState(
        raw_query=SAMPLE_TAGGED_QUERY,
        sanitized_query=SAMPLE_TAGGED_QUERY,
        intent_type="COMPARISON",
        is_comparison_eligible=True,
        detected_category="Laptops",
        target_keywords=['Apple MacBook Air 13.6" Laptop', 'Dell XPS 13"'],
    )
    updated_state = retrieval_agent.process(state)
    assert len(updated_state.retrieved_products) == 2

    mock_bq_client.query_and_wait.assert_called_once()
    sql_arg = mock_bq_client.query_and_wait.call_args[0][0]
    job_config = mock_bq_client.query_and_wait.call_args[1]["job_config"]
    patterns_param = next(p for p in job_config.query_parameters if p.name == "product_patterns")

    assert "LOWER(sku) IN UNNEST(@product_patterns)" in sql_arg
    assert "GREATEST(" not in sql_arg
    assert patterns_param.values == ["6534606", "6575132"]
    assert query_catalog is not None


def test_stage4_synthesis_prompt_short_handles_and_spec_pruning():
    """Verify Stage 4 synthesis shortens verbose catalog titles, prunes non-comparative metadata, and uses compact schema."""
    orch = ComparisonOrchestrator()
    p1 = ProductSpec(
        sku="6534606",
        name='Apple - MacBook Air 13.6" Laptop - M2 chip - 8GB Memory - 256GB SSD - Midnight',
        brand="Apple",
        category="Laptops",
        price=1099.0,
        specifications={
            "processor": "Apple M2",
            "ram_gb": 8,
            "storage_gb": 256,
            "upc": "194253081234",
            "model_number": "MLY33LL/A",
            "taxonomy_path": "Computers & Tablets > Laptops > All Laptops",
        },
    )
    p2 = ProductSpec(
        sku="4531200",
        name='Microsoft - Surface Book 2-in-1 13.5" Touch-Screen Laptop - Intel Core i5 - 8GB Memory - 256GB Solid State Drive - Silver',
        brand="Microsoft",
        category="Laptops",
        price=1899.99,
        specifications={
            "processor": "Intel Core i5",
            "ram_gb": 8,
            "display_size_in": 13.5,
            "upc": "889842015515",
            "model_number": "SX3-00001",
            "product_type": "HardGood",
            "subcategory": "PC Laptops",
            "taxonomy_path": "Computers & Tablets > Laptops > All Laptops > PC Laptops",
            "warranty": "1-Year Manufacturer Limited Warranty",
            "shipping_tier": "Free Standard Shipping",
        },
    )

    assert ComparisonOrchestrator._short_product_label(p1) == 'Apple - MacBook Air 13.6" Laptop'
    assert (
        ComparisonOrchestrator._short_product_label(p2)
        == 'Microsoft - Surface Book 2-in-1 13.5" Touch-Screen Laptop'
    )

    prompt = orch._build_synthesis_prompt([p1, p2], [], SAMPLE_GENERIC_FOCUS_QUERY)
    # Non-comparative inventory keys must be pruned from prompt
    for non_comp_key in (
        "889842015515",
        "SX3-00001",
        "HardGood",
        "taxonomy_path",
        "shipping_tier",
        "warranty",
    ):
        assert non_comp_key not in prompt

    # Verbose suffix should not appear in sku_tags_list
    assert "256GB Solid State Drive - Silver" not in prompt

    mw_prompt, spec_keys = orch._build_matrix_winners_prompt([p1, p2])
    for non_comp_field in (
        "upc",
        "model_number",
        "product_type",
        "subcategory",
        "taxonomy_path",
        "warranty",
        "shipping_tier",
    ):
        assert non_comp_field not in spec_keys
        assert non_comp_field not in mw_prompt


def test_compare_runs_stage1_and_stage2_in_parallel_and_discards_on_chatter(monkeypatch):
    """Verify ComparisonOrchestrator.compare runs Stage 1 and Stage 2 in parallel at t=0 and discards BQ results on chatter."""
    import threading
    import time

    import app.agent.orchestrator as orch_mod
    from app.models.requests import QueryIntentAnalysis

    orch = ComparisonOrchestrator()
    barrier = threading.Barrier(2, timeout=2.0)
    overlap_detected = {"both_running_at_t0": False}

    def fake_classify_intent(query, model=None):
        try:
            barrier.wait()
            overlap_detected["both_running_at_t0"] = True
        except threading.BrokenBarrierError:
            pass
        return QueryIntentAnalysis(
            intent_type="COMPARISON",
            detected_category="Laptops",
            target_keywords=["6534606", "6575132"],
            is_comparison_eligible=True,
            reasoning="Valid tagged comparison",
        )

    def fake_query_catalog(keywords=None, category=None, client=None, **kwargs):
        try:
            barrier.wait()
            overlap_detected["both_running_at_t0"] = True
        except threading.BrokenBarrierError:
            pass
        assert keywords == ["6534606", "6575132"]
        assert category is None
        return [
            {
                "sku": "6534606",
                "name": 'Apple MacBook Air 13.6" Laptop',
                "brand": "Apple",
                "category": "Laptops",
                "price": 1099.0,
                "specifications": {"ram_gb": 16},
                "in_stock": True,
            },
            {
                "sku": "6575132",
                "name": 'Dell XPS 13"',
                "brand": "Dell",
                "category": "Laptops",
                "price": 1199.0,
                "specifications": {"ram_gb": 16},
                "in_stock": True,
            },
        ]

    monkeypatch.setattr(orch, "classify_intent", fake_classify_intent)
    monkeypatch.setattr(orch_mod, "query_catalog", fake_query_catalog)

    resp = orch.compare(SAMPLE_TAGGED_QUERY, category="Laptops")
    assert overlap_detected["both_running_at_t0"] is True
    assert [p.sku for p in resp.products] == ["6534606", "6575132"]

    # Now verify that if Stage 1 marks query as ineligible/chatter, Stage 2 BQ results are discarded
    bq_called = {"count": 0}

    def fake_chatter_intent(query, model=None):
        time.sleep(0.02)
        return QueryIntentAnalysis(
            intent_type="OPINION_OR_CHATTER",
            detected_category=None,
            target_keywords=[],
            is_comparison_eligible=False,
            reasoning="Off-topic chatter despite tagged SKUs",
        )

    def fake_qc_discarded(keywords=None, category=None, client=None, **kwargs):
        bq_called["count"] += 1
        return [
            {
                "sku": "6534606",
                "name": 'Apple MacBook Air 13.6" Laptop',
                "brand": "Apple",
                "category": "Laptops",
                "price": 1099.0,
                "specifications": {"ram_gb": 16},
                "in_stock": True,
            }
        ]

    monkeypatch.setattr(orch, "classify_intent", fake_chatter_intent)
    monkeypatch.setattr(orch_mod, "query_catalog", fake_qc_discarded)
    chatter_resp = orch.compare(SAMPLE_TAGGED_QUERY, category="Laptops")
    assert bq_called["count"] == 1
    assert chatter_resp.products == []
    assert chatter_resp.comparison_matrix == []


def test_multi_agent_runs_stage1_and_stage2_in_parallel_and_discards_on_chatter(monkeypatch):
    """Verify MultiAgentCoordinator runs Stage 1 and Stage 2 in parallel at t=0 via native ADK JoinNode and discards BQ results on chatter."""
    import threading

    from google.adk.workflow import START, FunctionNode, JoinNode

    import app.agent.multi_agent as ma_mod
    from app.agent.multi_agent import MultiAgentCoordinator
    from app.models.requests import QueryIntentAnalysis

    coordinator = MultiAgentCoordinator()
    assert coordinator.adk_workflow.graph is not None
    function_nodes = [
        n for n in coordinator.adk_workflow.graph.nodes if isinstance(n, FunctionNode)
    ]
    assert len(function_nodes) == 3
    join_nodes = [n for n in coordinator.adk_workflow.graph.nodes if isinstance(n, JoinNode)]
    assert len(join_nodes) == 1
    assert join_nodes[0].name == "intent_retrieval_join"
    start_targets = {
        e.to_node.name
        for e in coordinator.adk_workflow.graph.edges
        if e.from_node.name == START.name
    }
    assert start_targets == {"query_intent_specialist", "catalog_retrieval_step"}

    barrier = threading.Barrier(2, timeout=2.0)
    overlap_detected = {"both_running_at_t0": False}

    def fake_classify_intent(query, model=None):
        try:
            barrier.wait()
            overlap_detected["both_running_at_t0"] = True
        except threading.BrokenBarrierError:
            pass
        return QueryIntentAnalysis(
            intent_type="COMPARISON",
            detected_category="Laptops",
            target_keywords=["6534606", "6575132"],
            is_comparison_eligible=True,
            reasoning="Valid tagged comparison",
        )

    def fake_query_catalog(keywords=None, category=None, client=None, **kwargs):
        try:
            barrier.wait()
            overlap_detected["both_running_at_t0"] = True
        except threading.BrokenBarrierError:
            pass
        assert keywords == ["6534606", "6575132"]
        assert category is None
        return [
            {
                "sku": "6534606",
                "name": 'Apple MacBook Air 13.6" Laptop',
                "brand": "Apple",
                "category": "Laptops",
                "price": 1099.0,
                "specifications": {"ram_gb": 16},
                "in_stock": True,
            },
            {
                "sku": "6575132",
                "name": 'Dell XPS 13"',
                "brand": "Dell",
                "category": "Laptops",
                "price": 1199.0,
                "specifications": {"ram_gb": 16},
                "in_stock": True,
            },
        ]

    monkeypatch.setattr(
        coordinator.intent_agent.orchestrator, "classify_intent", fake_classify_intent
    )
    monkeypatch.setattr(ma_mod, "query_catalog", fake_query_catalog)

    resp, state = coordinator.compare_with_trace(SAMPLE_TAGGED_QUERY, category="Laptops")
    assert overlap_detected["both_running_at_t0"] is True
    assert [p.sku for p in resp.products] == ["6534606", "6575132"]

    # Now verify chatter discards Stage 2 retrieved products
    def fake_chatter_intent(query, model=None):
        return QueryIntentAnalysis(
            intent_type="OPINION_OR_CHATTER",
            detected_category=None,
            target_keywords=[],
            is_comparison_eligible=False,
            reasoning="User chatter",
        )

    monkeypatch.setattr(
        coordinator.intent_agent.orchestrator, "classify_intent", fake_chatter_intent
    )
    chatter_resp, chatter_state = coordinator.compare_with_trace(
        SAMPLE_TAGGED_QUERY, category="Laptops"
    )
    assert chatter_resp.products == []
    assert chatter_resp.comparison_matrix == []
    assert chatter_state.retrieved_products == []


def test_stage3_does_not_invoke_rerank_with_llm_while_stage4_runs_parallel_matrix_winners(
    monkeypatch, sample_products
):
    """Verify _rerank_with_llm and relevance_agent are removed while compare keeps _run_matrix_winners_llm + build_comparison_matrix."""
    import app.agent.multi_agent as ma_mod
    import app.agent.orchestrator as orch_mod
    from app.agent.multi_agent import MultiAgentCoordinator

    orch = ComparisonOrchestrator()
    assert not hasattr(orch, "_rerank_with_llm")
    assert not hasattr(orch, "rank_and_select_products")

    matrix_winners_called = {"count": 0}
    orig_mw = orch._run_matrix_winners_llm

    def spy_mw(*args, **kwargs):
        matrix_winners_called["count"] += 1
        return orig_mw(*args, **kwargs)

    monkeypatch.setattr(orch, "_run_matrix_winners_llm", spy_mw)
    monkeypatch.setattr(
        orch_mod,
        "query_catalog",
        lambda **kwargs: [p.model_dump() for p in sample_products[:2]],
    )

    resp = orch.compare("Compare MacBook Air vs Dell XPS 13", category="Laptops")
    assert len(resp.products) == 2
    assert len(resp.comparison_matrix) >= 1
    assert matrix_winners_called["count"] == 1

    # Also check MultiAgentCoordinator
    coordinator = MultiAgentCoordinator()
    assert not hasattr(coordinator, "relevance_agent")
    monkeypatch.setattr(
        ma_mod,
        "query_catalog",
        lambda **kwargs: [p.model_dump() for p in sample_products],
    )
    ma_resp, _ = coordinator.compare_with_trace(SAMPLE_TAGGED_QUERY, category="Laptops")
    assert [p.sku for p in ma_resp.products] == ["6534606", "6575132"]
    assert len(ma_resp.comparison_matrix) >= 1


def test_compact_synthesis_prompt_preserves_skus_and_prices(sample_products):
    """Verify compacted _build_synthesis_prompt and STAGE4_SYNTHESIS_PROMPT_TEMPLATE preserve [SKU: ...], $ prices, and exact numeric spec values."""
    from app.agent.prompts import STAGE4_SYNTHESIS_PROMPT_TEMPLATE

    orch = ComparisonOrchestrator()
    products = sample_products[:2]
    prompt = orch._build_synthesis_prompt(products, [], SAMPLE_TAGGED_QUERY)

    assert "[SKU: 6534606]" in prompt
    assert "[SKU: 6575132]" in prompt
    assert "$1099.00" in prompt
    assert "$1199.00" in prompt
    assert "<catalog_products>" in prompt
    assert "<user_query>" in prompt
    assert "exact numeric" in STAGE4_SYNTHESIS_PROMPT_TEMPLATE.lower()
    assert len(STAGE4_SYNTHESIS_PROMPT_TEMPLATE) < 1100
    assert len(prompt) < 1500


def test_telemetry_logger_non_blocking_in_live_mode_and_background_warmup(monkeypatch):
    """Verify TelemetryLogger.log_comparison_run is non-blocking in live mode and background warmup is enabled in config."""
    import time

    from app.config import Settings
    from app.data.analytics import TelemetryLogger
    from app.observability import TelemetryLogger as ObsTelemetryLogger

    assert TelemetryLogger is ObsTelemetryLogger

    # 1. Verify default enable_background_warmup is True in Settings
    default_settings = Settings()
    assert default_settings.enable_background_warmup is True

    # 2. Verify TelemetryLogger.log_comparison_run runs non-blockingly on ThreadPoolExecutor in live mode
    slow_call_completed = {"done": False}

    class SlowBqClient:
        def insert_rows_json(self, table_id, rows):
            time.sleep(0.25)
            slow_call_completed["done"] = True
            return []

    t_logger = TelemetryLogger(bq_client=SlowBqClient())
    t0 = time.perf_counter()
    future = t_logger.log_comparison_run(
        {
            "query": "MacBook Air [SKU: 6534606] vs Dell XPS 13 [SKU: 6575132]",
            "category": "Laptops",
            "skus_returned": ["6534606", "6575132"],
            "latency_ms": 1200.0,
            "success": True,
        },
        force_async=True,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # Must return immediately (< 50ms) even though insert_rows_json sleeps 250ms
    assert elapsed_ms < 50.0
    assert future is not None
    result = future.result(timeout=2.0)
    assert result is True
    assert slow_call_completed["done"] is True


def test_verify_live_latency_uses_tagged_sku_queries():
    """Verify verify_live_latency.py BENCHMARK_QUERIES use realistic [SKU: ...] tagged queries."""
    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "verify_live_latency.py"
    spec = importlib.util.spec_from_file_location("verify_live_latency", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert len(mod.BENCHMARK_QUERIES) >= 3
    for query_str, _category in mod.BENCHMARK_QUERIES:
        assert "[SKU:" in query_str
        tagged = ComparisonOrchestrator.extract_tagged_products(query_str)
        assert len(tagged) >= 2
