"""Unit tests for Deterministic Claim-to-SKU Citation Verifier and post-hoc appending removal.

Tests:
1. Removal of post-hoc appending in synthesize_comparison_with_llm (no trailing '$price' fragments).
2. Strict non-injection: Python does NOT artificially inject [SKU: ...] tags when omitted.
3. Scrubbing of hallucinated SKUs not in catalog set.
4. Scrubbing of contradictory claim citations (e.g. Dell XPS 13 citing Apple SKU).
5. Preservation of valid, grounded inline citations.
"""

from unittest.mock import MagicMock

from app.agent.orchestrator import ComparisonOrchestrator
from app.models.responses import ProductSpec


def _make_mock_products() -> list[ProductSpec]:
    return [
        ProductSpec(
            sku="6534606",
            name='Apple - MacBook Air 13.6" Laptop - M2 chip - 8GB Memory - 256GB SSD - Midnight',
            brand="Apple",
            category="Laptops",
            price=999.0,
            rating=4.8,
            review_count=1200,
            specifications={"ram_gb": 8, "storage_gb": 256, "battery_life_hours": 18},
        ),
        ProductSpec(
            sku="6543210",
            name='Dell - XPS 13 Plus 13.4" OLED Touch Screen Laptop - Intel Core i7 - 16GB Memory - 512GB SSD',
            brand="Dell",
            category="Laptops",
            price=1299.0,
            rating=4.5,
            review_count=450,
            specifications={"ram_gb": 16, "storage_gb": 512, "battery_life_hours": 13},
        ),
    ]


def test_no_artificial_sku_injection_when_omitted():
    """Verify that when a summary names products without citations, Python does NOT inject [SKU: ...] tags."""
    products = _make_mock_products()
    raw_summary = (
        "The MacBook Air offers exceptional battery endurance for daily portability, "
        "while the Dell XPS 13 features double the memory for intensive multitasking."
    )
    aligned = ComparisonOrchestrator.verify_and_align_claim_citations(raw_summary, products)
    assert aligned is not None
    # No artificial injection
    assert "[SKU: 6534606]" not in aligned
    assert "[SKU: 6543210]" not in aligned
    assert aligned == raw_summary


def test_verify_and_align_claim_citations_scrubs_hallucinated_sku():
    """Verify that citations with non-existent SKUs are stripped."""
    products = _make_mock_products()
    raw_summary = "The MacBook Air [SKU: 9999999] is lightweight, while the Dell XPS 13 [SKU: 6543210] has higher RAM."
    aligned = ComparisonOrchestrator.verify_and_align_claim_citations(raw_summary, products)
    assert aligned is not None
    assert "[SKU: 9999999]" not in aligned
    assert "[SKU: 6543210]" in aligned


def test_verify_and_align_claim_citations_scrubs_contradictory_brand_sku():
    """Verify that a citation is scrubbed if the clause describes a competing brand."""
    products = _make_mock_products()
    # 6534606 is Apple MacBook Air, but here attached to Dell XPS 13
    contradictory_summary = "The Dell XPS 13 [SKU: 6534606] features 16GB of RAM."
    aligned = ComparisonOrchestrator.verify_and_align_claim_citations(
        contradictory_summary, products
    )
    assert aligned is not None
    # The contradictory citation must be scrubbed
    assert "[SKU: 6534606]" not in aligned


def test_verify_and_align_claim_citations_preserves_valid_citations():
    """Verify that correctly grounded citations are preserved."""
    products = _make_mock_products()
    valid_summary = (
        "The Apple MacBook Air [SKU: 6534606] lasts 18 hours, "
        "while the Dell XPS 13 [SKU: 6543210] offers 16GB of memory."
    )
    aligned = ComparisonOrchestrator.verify_and_align_claim_citations(valid_summary, products)
    assert aligned is not None
    assert "[SKU: 6534606]" in aligned
    assert "[SKU: 6543210]" in aligned


def test_post_hoc_appending_removed_from_synthesize():
    """Verify synthesize_comparison_with_llm no longer artificially tacks on '[SKU: ...] ($price)'."""
    products = _make_mock_products()
    orchestrator = ComparisonOrchestrator(model="gemini-2.5-pro")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = (
        '{"summary": "The MacBook Air [SKU: 6534606] provides class-leading battery life, '
        'while Dell XPS 13 delivers double the memory for productivity.", '
        '"recommendations": "Best for travel: MacBook Air [SKU: 6534606]. Best for power: Dell XPS 13 [SKU: 6543210]."}'
    )
    mock_client.models.generate_content.return_value = mock_resp
    orchestrator.genai_client = mock_client

    synth = orchestrator.synthesize_comparison_with_llm(
        products=products,
        matrix=orchestrator.build_comparison_matrix(products),
        query="Compare MacBook Air and Dell XPS 13",
    )
    summary = synth.summary
    # Check that post-hoc appended fragment is NOT present at the end
    assert not summary.endswith("($1,299.00).")
    assert not summary.endswith("($999.00).")
    # Verify no artificial injection added [SKU: 6543210] to the summary text where the LLM omitted it
    assert "[SKU: 6543210]" not in summary
