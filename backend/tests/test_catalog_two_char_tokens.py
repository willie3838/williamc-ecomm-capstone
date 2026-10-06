"""Unit tests verifying 2-character sub-token SQL tokenization and brand entity balancing.

Tests:
1. Extraction of 2-character brand and model sub-tokens (e.g., 'LG', 'C3', 'HP') in query_catalog().
2. Exclusion of 2-character grammatical stopwords (e.g., 'to', 'in', 'on', 'at', 'by', 'is', 'or', 'vs', 'an', 'no').
3. Exclusion of single-character tokens (len(t) < 2).
4. Balancing of 2-character brand entities in ComparisonOrchestrator._balance_entities() for LG and HP.
5. Verification of BigQuery parameter binding for 2-character tokens.
"""

import ast
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec
from app.tools.catalog import query_catalog


def test_catalog_tokenizes_two_character_brand_and_model():
    """Verify query_catalog produces sub-token LIKE patterns for 2-character brands and models (LG, C3, HP)."""
    mock_client = MagicMock()
    mock_client.query_and_wait.return_value = []

    query_catalog(
        keywords=["LG C3 OLED", "Samsung S90C"],
        client=mock_client,
    )

    mock_client.query_and_wait.assert_called_once()
    job_config = mock_client.query_and_wait.call_args[1]["job_config"]
    patterns_param = next(p for p in job_config.query_parameters if p.name == "product_patterns")
    patterns = patterns_param.values

    # Check 2-character tokens are present
    assert "%lg%" in patterns, f"Expected '%lg%' in patterns, got: {patterns}"
    assert "%c3%" in patterns, f"Expected '%c3%' in patterns, got: {patterns}"
    assert "%oled%" in patterns, f"Expected '%oled%' in patterns, got: {patterns}"
    assert "%samsung%" in patterns, f"Expected '%samsung%' in patterns, got: {patterns}"
    assert "%s90c%" in patterns, f"Expected '%s90c%' in patterns, got: {patterns}"


def test_catalog_tokenizes_hp_brand_sub_token():
    """Verify query_catalog produces sub-token LIKE pattern for 2-character brand 'HP'."""
    mock_client = MagicMock()
    mock_client.query_and_wait.return_value = []

    query_catalog(
        keywords=["HP Envy", "Dell XPS"],
        client=mock_client,
    )

    mock_client.query_and_wait.assert_called_once()
    job_config = mock_client.query_and_wait.call_args[1]["job_config"]
    patterns_param = next(p for p in job_config.query_parameters if p.name == "product_patterns")
    patterns = patterns_param.values

    assert "%hp%" in patterns, f"Expected '%hp%' in patterns, got: {patterns}"
    assert "%envy%" in patterns, f"Expected '%envy%' in patterns, got: {patterns}"
    assert "%dell%" in patterns, f"Expected '%dell%' in patterns, got: {patterns}"
    assert "%xps%" in patterns, f"Expected '%xps%' in patterns, got: {patterns}"


def test_catalog_excludes_two_character_stopwords():
    """Verify 2-character grammatical stopwords are excluded from SQL sub-token patterns."""
    mock_client = MagicMock()
    mock_client.query_and_wait.return_value = []

    query_catalog(
        keywords=[
            "laptop in an office on or at desk with no fan by tv is ok so we do go if it be up us"
        ],
        client=mock_client,
    )

    mock_client.query_and_wait.assert_called_once()
    job_config = mock_client.query_and_wait.call_args[1]["job_config"]
    patterns_param = next(p for p in job_config.query_parameters if p.name == "product_patterns")
    patterns = patterns_param.values

    two_letter_stopwords = [
        "an",
        "as",
        "at",
        "be",
        "by",
        "do",
        "go",
        "if",
        "in",
        "is",
        "it",
        "no",
        "of",
        "on",
        "or",
        "so",
        "to",
        "up",
        "us",
        "we",
        "vs",
    ]
    for sw in two_letter_stopwords:
        assert f"%{sw}%" not in patterns, (
            f"Stopword '%{sw}%' should NOT be extracted as a sub-token pattern in: {patterns}"
        )


def test_catalog_excludes_single_character_tokens():
    """Verify single-character tokens (len < 2) are not added as sub-token patterns."""
    mock_client = MagicMock()
    mock_client.query_and_wait.return_value = []

    query_catalog(
        keywords=["Sony TV A B C 1 2 3"],
        client=mock_client,
    )

    mock_client.query_and_wait.assert_called_once()
    job_config = mock_client.query_and_wait.call_args[1]["job_config"]
    patterns_param = next(p for p in job_config.query_parameters if p.name == "product_patterns")
    patterns = patterns_param.values

    for single_char in ["a", "b", "c", "1", "2", "3"]:
        assert f"%{single_char}%" not in patterns, (
            f"Single char '%{single_char}%' should NOT be in patterns: {patterns}"
        )


def test_balance_entities_two_char_brand_lg_c3():
    """Verify _balance_entities balances LG C3 into top 2 when candidates start with multiple Samsungs."""
    candidates = [
        ProductSpec(
            sku="6543210",
            name='Samsung - 65" Class S90C OLED 4K Smart Tizen TV',
            brand="Samsung",
            category="TVs",
            price=1599.99,
        ),
        ProductSpec(
            sku="6543211",
            name='Samsung - 65" Class S95C OLED 4K Smart Tizen TV',
            brand="Samsung",
            category="TVs",
            price=2199.99,
        ),
        ProductSpec(
            sku="6535928",
            name='LG - 65" Class C3 Series OLED 4K UHD Smart webOS TV',
            brand="LG",
            category="TVs",
            price=1499.99,
        ),
    ]

    orchestrator = ComparisonOrchestrator()
    balanced = orchestrator._balance_entities(candidates, keywords=["Samsung S90C", "LG C3"])

    assert len(balanced) == 3
    top_two = balanced[:2]
    brands = {p.brand.lower() for p in top_two}
    assert "samsung" in brands, f"Expected Samsung in top 2, got: {[p.name for p in top_two]}"
    assert "lg" in brands, f"Expected LG in top 2, got: {[p.name for p in top_two]}"
    assert top_two[1].sku == "6535928", (
        f"Expected LG C3 (SKU 6535928) in 2nd slot, got: {top_two[1]}"
    )


def test_balance_entities_two_char_brand_hp_envy():
    """Verify _balance_entities balances HP Envy into top 2 when candidates start with multiple Dells."""
    candidates = [
        ProductSpec(
            sku="6575132",
            name='Dell - XPS 13" Laptop - Intel Core Ultra 7',
            brand="Dell",
            category="Laptops",
            price=1299.99,
        ),
        ProductSpec(
            sku="6575133",
            name='Dell - Inspiron 15" Touch Laptop',
            brand="Dell",
            category="Laptops",
            price=649.99,
        ),
        ProductSpec(
            sku="6565123",
            name='HP - Envy 16" Touch-Screen Laptop - Intel Core i7',
            brand="HP",
            category="Laptops",
            price=1199.99,
        ),
    ]

    orchestrator = ComparisonOrchestrator()
    balanced = orchestrator._balance_entities(candidates, keywords=["Dell XPS", "HP Envy"])

    assert len(balanced) == 3
    top_two = balanced[:2]
    brands = {p.brand.lower() for p in top_two}
    assert "dell" in brands, f"Expected Dell in top 2, got: {[p.name for p in top_two]}"
    assert "hp" in brands, f"Expected HP in top 2, got: {[p.name for p in top_two]}"
    assert top_two[1].sku == "6565123", (
        f"Expected HP Envy (SKU 6565123) in 2nd slot, got: {top_two[1]}"
    )


def test_balance_entities_with_two_char_model_token():
    """Verify _balance_entities matches 2-character model tokens like 'C3' when prefix tokens match."""
    candidates = [
        ProductSpec(
            sku="1111111",
            name="Sony - Bravia 8 OLED 4K HDR TV",
            brand="Sony",
            category="TVs",
            price=1799.99,
        ),
        ProductSpec(
            sku="1111112",
            name="Sony - Bravia 7 Mini-LED 4K TV",
            brand="Sony",
            category="TVs",
            price=1499.99,
        ),
        ProductSpec(
            sku="2222222",
            name="LG - C3 OLED evo 4K Smart TV",
            brand="LG Electronics",
            category="TVs",
            price=1399.99,
        ),
    ]

    # Keyword only has "C3" and "Bravia" - brand "LG Electronics" is NOT in kw_text
    orchestrator = ComparisonOrchestrator()
    balanced = orchestrator._balance_entities(candidates, keywords=["Bravia", "C3"])

    top_two = balanced[:2]
    assert top_two[0].sku == "1111111"
    assert top_two[1].sku == "2222222", (
        f"Expected 2-char model 'C3' to balance into slot 2, got: {top_two[1].name}"
    )


def test_orchestrator_future_timeout_is_eight_seconds():
    """Verify that all speculative and in-flight .result(timeout=...) calls use timeout=8.0 via AST analysis."""
    orch_path = Path(__file__).resolve().parent.parent / "src" / "app" / "agent" / "orchestrator.py"
    content = orch_path.read_text(encoding="utf-8")

    # Assert no timeout=4.0 remains
    assert "timeout=4.0" not in content, "Found lingering timeout=4.0 in orchestrator.py!"

    # AST-level inspection of all Call nodes invoking .result(timeout=...)
    tree = ast.parse(content)
    result_timeout_values: list[float] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "result"
        ):
            for kw in node.keywords:
                if kw.arg == "timeout" and isinstance(kw.value, ast.Constant):
                    result_timeout_values.append(float(kw.value.value))

    assert 4.0 not in result_timeout_values, (
        f"Found Call with timeout=4.0 in AST: {result_timeout_values}"
    )
    assert result_timeout_values.count(8.0) >= 3 and all(t >= 8.0 for t in result_timeout_values), (
        f"Expected all .result(timeout=...) calls to use timeout=8.0, found: {result_timeout_values}"
    )


def test_classify_intent_prompt_and_keywords_exclude_spec_attributes():
    """Verify prompt instructs excluding spec attributes and post-processor filters them."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    # LLM returns spec attributes mixed in target_keywords
    mock_resp.text = json.dumps(
        {
            "intent_type": "COMPARISON",
            "is_comparison_eligible": True,
            "detected_category": "TVs",
            "target_keywords": [
                "LG C3",
                "Samsung S90C",
                "Dolby Vision",
                "HDR10+",
                "OLED",
                "4K TVs",
            ],
            "reasoning": "Comparison request.",
        }
    )
    mock_resp.usage_metadata.prompt_token_count = 120
    mock_resp.usage_metadata.candidates_token_count = 60
    mock_client.models.generate_content.return_value = mock_resp

    orchestrator = ComparisonOrchestrator(genai_client=mock_client)
    res = orchestrator.classify_intent_with_llm(
        "LG C3 vs Samsung S90C for Dolby Vision and HDR10+ OLED 4K TVs"
    )

    # Verify prompt instructions
    call_args = mock_client.models.generate_content.call_args
    prompt_used = call_args.kwargs.get("contents", "")
    assert "CRITICAL KEYWORD EXTRACTION RULES" in prompt_used
    assert (
        "target_keywords MUST extract only distinct product, brand, or model entities"
        in prompt_used
    )

    # Verify spec attributes were scrubbed/filtered
    assert "LG C3" in res.target_keywords
    assert "Samsung S90C" in res.target_keywords
    assert "Dolby Vision" not in res.target_keywords
    assert "HDR10+" not in res.target_keywords
    assert "OLED" not in res.target_keywords
    assert "4K TVs" not in res.target_keywords
    assert len(res.target_keywords) == 2


def test_classify_intent_normalizes_comparative_query_to_comparison():
    """Verify non-opinion comparative queries with >= 2 target_keywords normalize to COMPARISON with is_comparison_eligible=True."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    # Mock LLM returning PRODUCT_SEARCH and is_comparison_eligible=False by mistake
    mock_resp.text = json.dumps(
        {
            "intent_type": "PRODUCT_SEARCH",
            "is_comparison_eligible": False,
            "detected_category": "Laptops",
            "target_keywords": ["Dell XPS 13", "HP Envy"],
            "reasoning": "Product lookup.",
        }
    )
    mock_resp.usage_metadata.prompt_token_count = 100
    mock_resp.usage_metadata.candidates_token_count = 40
    mock_client.models.generate_content.return_value = mock_resp

    orchestrator = ComparisonOrchestrator(genai_client=mock_client)
    # Query with 'versus'
    res = orchestrator.classify_intent_with_llm("Dell XPS 13 versus HP Envy")
    assert res.intent_type == "COMPARISON"
    assert res.is_comparison_eligible is True

    # Query with 'compare'
    res_compare = orchestrator.classify_intent_with_llm("compare Dell XPS 13 and HP Envy")
    assert res_compare.intent_type == "COMPARISON"
    assert res_compare.is_comparison_eligible is True

    # Query with 'difference between'
    res_diff = orchestrator.classify_intent_with_llm("difference between Dell XPS 13 and HP Envy")
    assert res_diff.intent_type == "COMPARISON"
    assert res_diff.is_comparison_eligible is True


def test_classify_intent_retries_on_json_parse_failure_and_succeeds():
    """Verify classify_intent_with_llm executes 1 clean retry when initial JSON parsing fails and succeeds on 2nd attempt."""
    mock_client = MagicMock()
    bad_resp = MagicMock()
    bad_resp.text = "NOT JSON at all { malformed"
    bad_resp.usage_metadata.prompt_token_count = 100
    bad_resp.usage_metadata.candidates_token_count = 20

    good_resp = MagicMock()
    good_resp.text = json.dumps(
        {
            "intent_type": "COMPARISON",
            "is_comparison_eligible": True,
            "detected_category": "Laptops",
            "target_keywords": ["MacBook Air", "Dell XPS 13"],
            "reasoning": "Comparison request.",
        }
    )
    good_resp.usage_metadata.prompt_token_count = 100
    good_resp.usage_metadata.candidates_token_count = 40

    mock_client.models.generate_content.side_effect = [bad_resp, good_resp]

    orchestrator = ComparisonOrchestrator(genai_client=mock_client)
    result = orchestrator.classify_intent_with_llm("MacBook Air vs Dell XPS 13")

    assert mock_client.models.generate_content.call_count == 2
    assert result.intent_type == "COMPARISON"
    assert result.is_comparison_eligible is True
    assert result.target_keywords == ["MacBook Air", "Dell XPS 13"]


def test_classify_intent_retries_on_json_parse_failure_and_fails_fast_on_second_failure():
    """Verify classify_intent_with_llm preserves fail-fast exception when retry also fails."""
    mock_client = MagicMock()
    bad_resp1 = MagicMock()
    bad_resp1.text = "Bad response 1"
    bad_resp2 = MagicMock()
    bad_resp2.text = "Bad response 2"

    mock_client.models.generate_content.side_effect = [bad_resp1, bad_resp2]

    orchestrator = ComparisonOrchestrator(genai_client=mock_client)
    with pytest.raises((ValidationError, RuntimeError, ValueError)):
        orchestrator.classify_intent_with_llm("MacBook Air vs Dell XPS 13")

    assert mock_client.models.generate_content.call_count == 2


def test_rerank_with_llm_retries_on_json_parse_failure_and_succeeds():
    """Verify _rerank_with_llm executes 1 clean retry when initial JSON parsing fails and succeeds on 2nd attempt."""
    mock_client = MagicMock()
    bad_resp = MagicMock()
    bad_resp.text = "NOT JSON"

    good_resp = MagicMock()
    good_resp.text = json.dumps(
        {
            "rankings": [
                {"sku": "6543210", "score": 10},
                {"sku": "6535928", "score": 9},
            ]
        }
    )
    mock_client.models.generate_content.side_effect = [bad_resp, good_resp]

    candidates = [
        ProductSpec(
            sku="6543210",
            name="Samsung S90C",
            brand="Samsung",
            category="TVs",
            price=1599.99,
        ),
        ProductSpec(
            sku="6535928",
            name="LG C3",
            brand="LG",
            category="TVs",
            price=1499.99,
        ),
    ]

    orchestrator = ComparisonOrchestrator(genai_client=mock_client)
    ranked = orchestrator._rerank_with_llm(candidates, query="Samsung S90C vs LG C3")

    assert mock_client.models.generate_content.call_count == 2
    assert ranked is not None
    assert len(ranked) == 2
    assert ranked[0].sku == "6543210"
    assert ranked[1].sku == "6535928"


def test_rerank_with_llm_retries_on_json_parse_failure_and_fails_fast_on_second_failure():
    """Verify _rerank_with_llm raises RuntimeError when retry also fails to produce valid JSON."""
    mock_client = MagicMock()
    bad_resp1 = MagicMock()
    bad_resp1.text = "Bad rerank 1"
    bad_resp2 = MagicMock()
    bad_resp2.text = "Bad rerank 2"

    mock_client.models.generate_content.side_effect = [bad_resp1, bad_resp2]

    candidates = [
        ProductSpec(
            sku="6543210",
            name="Samsung S90C",
            brand="Samsung",
            category="TVs",
            price=1599.99,
        ),
        ProductSpec(
            sku="6535928",
            name="LG C3",
            brand="LG",
            category="TVs",
            price=1499.99,
        ),
    ]

    orchestrator = ComparisonOrchestrator(genai_client=mock_client)
    with pytest.raises(RuntimeError, match="Gemini reranking LLM"):
        orchestrator._rerank_with_llm(candidates, query="Samsung S90C vs LG C3")

    assert mock_client.models.generate_content.call_count == 2
