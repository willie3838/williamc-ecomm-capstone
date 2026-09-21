"""Tests verifying ADK agent de-overfitting, brand-agnostic extraction, and generalization."""

import json
from pathlib import Path

from evals.runner import create_hermetic_bq_client

from app.agent.multi_agent import ComparisonAgentState, QueryIntentAgent
from app.agent.orchestrator import ComparisonOrchestrator
from app.agent.prompts import SYSTEM_INSTRUCTION


class TestAgentDeoverfitting:
    """Verify elimination of benchmark-specific overfitting across agent components."""

    def test_prompts_free_of_hardcoded_benchmark_products_and_skus(self):
        """Ensure SYSTEM_INSTRUCTION uses generic patterns, not overfitted benchmark products/skus."""
        # Overfitted strings that were previously hardcoded in prompts
        forbidden_specifics = [
            "MacBook Air M3",
            "Dell XPS 13",
            "6534606",
            "6575132",
            "Sony WH-1000XM5",
            "Bose QC Ultra",
        ]
        for forbidden in forbidden_specifics:
            assert forbidden not in SYSTEM_INSTRUCTION, (
                f"Found overfitted term '{forbidden}' in SYSTEM_INSTRUCTION"
            )

        # Ensure generic placeholder examples are used instead
        assert "Model Alpha" in SYSTEM_INSTRUCTION or "Model" in SYSTEM_INSTRUCTION, (
            "SYSTEM_INSTRUCTION should use generic model placeholders"
        )

    def test_extract_keywords_unseen_brands(self):
        """Ensure extract_keywords works for novel brands never seen in the 80 benchmark pairs."""
        orchestrator = ComparisonOrchestrator(model="gemini-2.5-flash")

        # Novel mobile brands
        kws = orchestrator.extract_keywords("Nothing Phone 2 vs Asus ROG Phone 8")
        assert len(kws) >= 2
        assert any("nothing" in k.lower() for k in kws)
        assert any("asus" in k.lower() or "rog" in k.lower() for k in kws)

        # Novel audio brands
        kws_audio = orchestrator.extract_keywords(
            "Anker Soundcore Space One compared to Sennheiser Momentum 4"
        )
        assert len(kws_audio) >= 2
        assert any("anker" in k.lower() or "soundcore" in k.lower() for k in kws_audio)
        assert any("sennheiser" in k.lower() or "momentum" in k.lower() for k in kws_audio)

        # Novel appliance brands
        kws_appl = orchestrator.extract_keywords(
            "Breville Barista Touch versus DeLonghi Magnifica S"
        )
        assert len(kws_appl) >= 2
        assert any("breville" in k.lower() for k in kws_appl)
        assert any("delonghi" in k.lower() for k in kws_appl)

    def test_extract_keywords_structural_leadins_and_attributes(self):
        """Ensure attribute breakdown lead-ins and trailing qualifiers are stripped robustly."""
        orchestrator = ComparisonOrchestrator(model="gemini-2.5-flash")

        # Colon lead-in with comparative markers in after part
        q1 = "Audio and smart features comparison: Sony WH-1000XM5 vs Bose QC Ultra"
        kws1 = orchestrator.extract_keywords(q1)
        assert len(kws1) >= 2
        assert any("sony" in k.lower() for k in kws1)
        assert any("bose" in k.lower() for k in kws1)

        # Attribute lead-in without colon
        q2 = "Screen size breakdown of LG OLED C3 vs Samsung S90C"
        kws2 = orchestrator.extract_keywords(q2)
        assert len(kws2) >= 2
        assert any("lg" in k.lower() or "c3" in k.lower() for k in kws2)
        assert any("samsung" in k.lower() or "s90c" in k.lower() for k in kws2)

        # Trailing attribute qualifier
        q3 = "Compare Brand A Model X and Brand B Model Y on price and battery life"
        kws3 = orchestrator.extract_keywords(q3)
        assert len(kws3) >= 2
        assert not any("price and battery life" in k.lower() for k in kws3)

    def test_intent_classification_prompt_generic(self):
        """Ensure classify_intent prompt does not anchor on specific benchmark models."""
        orchestrator = ComparisonOrchestrator(model="gemini-2.5-flash")
        # Test heuristic / hermetic mode intent classification without API call
        analysis = orchestrator.classify_intent("Compare NovelDevice A and NovelDevice B")
        assert analysis.is_comparison_eligible is True
        assert analysis.intent_type == "COMPARISON"
        assert len(analysis.target_keywords) >= 2

    def test_multi_agent_query_intent_generalization(self):
        """Verify QueryIntentAgent handles novel entities without hardcoded brand lists."""
        agent = QueryIntentAgent(model="gemini-2.5-flash")
        state = ComparisonAgentState(raw_query="Compare Nothing Phone 2 vs Asus ROG Phone 8")
        updated_state = agent.process(state)

        assert updated_state.is_comparison_eligible is True
        assert len(updated_state.target_keywords) >= 2
        assert any("nothing" in k.lower() for k in updated_state.target_keywords)
        assert any("asus" in k.lower() or "rog" in k.lower() for k in updated_state.target_keywords)

    def test_hermetic_bq_client_generalized_matching(self, tmp_path: Path):
        """Verify create_hermetic_bq_client matches novel brands without a hardcoded brand whitelist."""
        # Create a catalog with novel brands not in the old whitelist
        novel_catalog = [
            {
                "sku": "9000001",
                "name": "Asus ROG Phone 8 Pro Gaming Smartphone",
                "brand": "Asus",
                "category": "Smartphones",
                "price": 999.0,
                "specifications": {"ram_gb": 16, "storage_gb": 512},
            },
            {
                "sku": "9000002",
                "name": "Nothing Phone 2 Transparent Flagship",
                "brand": "Nothing",
                "category": "Smartphones",
                "price": 699.0,
                "specifications": {"ram_gb": 12, "storage_gb": 256},
            },
        ]
        cat_file = tmp_path / "novel_catalog.json"
        cat_file.write_text(json.dumps(novel_catalog), encoding="utf-8")

        client = create_hermetic_bq_client(cat_file)

        # Mock query parameter
        class MockParam:
            def __init__(self, name: str, values: list[str]):
                self.name = name
                self.values = values

        class MockJobConfig:
            def __init__(self, patterns: list[str]):
                self.query_parameters = [MockParam("product_patterns", patterns)]

        job = client.query(
            "SELECT ...", job_config=MockJobConfig(["%Asus ROG Phone%", "%Nothing Phone%"])
        )
        results = job.result()

        assert len(results) == 2
        skus = {r["sku"] for r in results}
        assert "9000001" in skus
        assert "9000002" in skus

    def test_extract_keywords_complex_trailing_and_colon_patterns(self):
        """Verify extract_keywords handles trailing comparison phrases and question-colon formats without dropping entities."""
        orchestrator = ComparisonOrchestrator(model="gemini-2.5-flash")

        # 1. Trailing comparison & attribute phrases
        q1 = "MacBook Air 13 M3 vs MacBook Pro 14 M3 Pro display size and memory comparison"
        kws1 = orchestrator.extract_keywords(q1)
        assert len(kws1) == 2
        assert "MacBook Air" in kws1[0]
        assert "MacBook Pro" in kws1[1]

        q2 = "iPad Pro 11 M4 OLED versus Samsung Galaxy Tab S9 AMOLED screen comparison"
        kws2 = orchestrator.extract_keywords(q2)
        assert len(kws2) == 2
        assert "iPad Pro" in kws2[0]
        assert "Samsung Galaxy Tab S9" in kws2[1]

        q3 = "30-hour battery Sony WH-1000XM5 vs 20-hour Apple AirPods Max comparison"
        kws3 = orchestrator.extract_keywords(q3)
        assert len(kws3) == 2
        assert "Sony" in kws3[0]
        assert "AirPods" in kws3[1]

        # 2. Question prefix with colon-separated choices
        q4 = "Which 65-inch OLED TV is better for bright rooms: LG C3 or Samsung S90C?"
        kws4 = orchestrator.extract_keywords(q4)
        assert len(kws4) == 2
        assert "LG C3" in kws4[0]
        assert "Samsung S90C" in kws4[1]

        q5 = "Which 65-inch OLED TV is cheaper: LG C3 or Samsung S90C?"
        kws5 = orchestrator.extract_keywords(q5)
        assert len(kws5) == 2
        assert "LG C3" in kws5[0]
        assert "Samsung S90C" in kws5[1]

        # 3. Specification lead-in with colon-separated target models
        q6 = "Apple M4 chip vs Snapdragon 8 Gen 2: iPad Pro 11 vs Galaxy Tab S9"
        kws6 = orchestrator.extract_keywords(q6)
        assert len(kws6) == 2
        assert "iPad Pro" in kws6[0]
        assert "Galaxy Tab S9" in kws6[1]
