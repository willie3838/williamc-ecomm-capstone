"""Unit tests verifying 2-character sub-token SQL tokenization and brand entity balancing.

Tests:
1. Extraction of 2-character brand and model sub-tokens (e.g., 'LG', 'C3', 'HP') in query_catalog().
2. Exclusion of 2-character grammatical stopwords (e.g., 'to', 'in', 'on', 'at', 'by', 'is', 'or', 'vs', 'an', 'no').
3. Exclusion of single-character tokens (len(t) < 2).
4. Balancing of 2-character brand entities in ComparisonOrchestrator._balance_entities() for LG and HP.
5. Verification of BigQuery parameter binding for 2-character tokens.
"""

from unittest.mock import MagicMock

from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec
from app.tools.catalog import query_catalog


def test_catalog_tokenizes_two_character_brand_and_model():
    """Verify query_catalog produces sub-token LIKE patterns for 2-character brands and models (LG, C3, HP)."""
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_client.query.return_value = mock_job

    query_catalog(
        keywords=["LG C3 OLED", "Samsung S90C"],
        client=mock_client,
    )

    mock_client.query.assert_called_once()
    job_config = mock_client.query.call_args[1]["job_config"]
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
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_client.query.return_value = mock_job

    query_catalog(
        keywords=["HP Envy", "Dell XPS"],
        client=mock_client,
    )

    mock_client.query.assert_called_once()
    job_config = mock_client.query.call_args[1]["job_config"]
    patterns_param = next(p for p in job_config.query_parameters if p.name == "product_patterns")
    patterns = patterns_param.values

    assert "%hp%" in patterns, f"Expected '%hp%' in patterns, got: {patterns}"
    assert "%envy%" in patterns, f"Expected '%envy%' in patterns, got: {patterns}"
    assert "%dell%" in patterns, f"Expected '%dell%' in patterns, got: {patterns}"
    assert "%xps%" in patterns, f"Expected '%xps%' in patterns, got: {patterns}"


def test_catalog_excludes_two_character_stopwords():
    """Verify 2-character grammatical stopwords are excluded from SQL sub-token patterns."""
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_client.query.return_value = mock_job

    query_catalog(
        keywords=[
            "laptop in an office on or at desk with no fan by tv is ok so we do go if it be up us"
        ],
        client=mock_client,
    )

    mock_client.query.assert_called_once()
    job_config = mock_client.query.call_args[1]["job_config"]
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
    mock_job = MagicMock()
    mock_job.result.return_value = []
    mock_client.query.return_value = mock_job

    query_catalog(
        keywords=["Sony TV A B C 1 2 3"],
        client=mock_client,
    )

    mock_client.query.assert_called_once()
    job_config = mock_client.query.call_args[1]["job_config"]
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
