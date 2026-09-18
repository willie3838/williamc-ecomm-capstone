"""Hermetic model adapter for executing ADK agents in offline test environments and local presubmits."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock

from app.models.requests import ComparisonSynthesis, QueryIntentAnalysis


class HermeticModelAdapter:
    """Mock Gemini model adapter providing deterministic grounded responses for offline ADK Agent execution."""

    @staticmethod
    def classify_intent_response(query: str) -> QueryIntentAnalysis:
        """Generate deterministic QueryIntentAnalysis matching the query."""
        lower_q = (query or "").lower().strip()

        if not lower_q:
            return QueryIntentAnalysis(
                intent_type="OPINION_OR_CHATTER",
                is_comparison_eligible=False,
                reasoning="Empty or blank query (offline hermetic).",
            )

        opinion_words = [
            "stupid",
            "sucks",
            "suck",
            "hate",
            "ugly",
            "trash",
            "garbage",
            "worst",
            "terrible",
            "awful",
            "horrible",
            "annoying",
            "useless",
            "bad",
        ]
        is_opinion = any(re.search(r"\b" + re.escape(w) + r"\b", lower_q) for w in opinion_words)
        comparative_tokens = [
            " vs ",
            " vs. ",
            " versus ",
            " compare ",
            " difference between ",
            " differences between ",
            " which is better ",
            " which has better ",
            " which one ",
            " compared to ",
        ]
        if any(tok in f" {lower_q} " for tok in comparative_tokens):
            is_opinion = False

        if is_opinion:
            return QueryIntentAnalysis(
                intent_type="OPINION_OR_CHATTER",
                is_comparison_eligible=False,
                reasoning="Subjective opinion or chatter detected (offline hermetic).",
            )

        detected_category = None
        if re.search(
            r"\b(?:laptops?|notebooks?|ultrabooks?|chromebooks?|macbooks?|xps|thinkpads?)\b",
            lower_q,
        ):
            detected_category = "Laptops"
        elif re.search(r"\b(?:tablets?|e-?readers?|ipads?|galaxy\s*tabs?)\b", lower_q):
            detected_category = "Tablets"
        elif re.search(
            r"\b(?:headphones?|earbuds?|earphones?|headsets?|airpods?|quietcomfort|wh-?1000\w*)\b",
            lower_q,
        ):
            detected_category = "Headphones"
        elif re.search(
            r"\b(?:smart\s*home|thermostats?|doorbells?|security\s*cameras?|nest)\b", lower_q
        ):
            detected_category = "Smart Home"
        elif re.search(r"\b(?:tvs?|televisions?|oled|qled|c3|c4|s90c|s95c)\b", lower_q):
            detected_category = "TVs"

        clean = re.sub(
            r"^(?:tell me about|what is the difference between|what are the differences between|which is better|which has better|can you compare|compare|difference between)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        )
        parts = re.split(
            r"\b(?:and|vs\.?|versus|or|with|compared to|against|than)\b|,",
            clean,
            flags=re.IGNORECASE,
        )
        keywords = [p.strip() for p in parts if len(p.strip()) >= 2]
        if not keywords:
            keywords = [query.strip()]

        is_comparative = (
            any(tok in f" {lower_q} " for tok in comparative_tokens) or len(keywords) >= 2
        )

        return QueryIntentAnalysis(
            intent_type="COMPARISON" if is_comparative else "PRODUCT_SEARCH",
            is_comparison_eligible=is_comparative,
            detected_category=detected_category,
            target_keywords=keywords,
            reasoning="Grounded intent extraction (offline hermetic).",
        )

    @staticmethod
    def rerank_response(prompt: str) -> str:
        """Parse candidates in prompt and produce relevance JSON array."""
        user_query_match = re.search(r"<user_query>(.*?)</user_query>", prompt, re.DOTALL)
        query = user_query_match.group(1).lower() if user_query_match else ""

        candidate_lines = re.findall(
            r"- SKU:\s*([A-Za-z0-9_-]+)\s*\|\s*([^|]+)\|\s*Brand:\s*([^|]+)", prompt
        )
        if not candidate_lines:
            candidate_skus = re.findall(r"SKU:\s*([A-Za-z0-9_-]+)", prompt)
            return json.dumps([{"sku": s, "score": 10.0} for s in candidate_skus])

        ranked: list[dict[str, Any]] = []
        for sku, name, brand in candidate_lines:
            cand_text = f"{name} {brand}".lower()
            tokens = [t for t in re.findall(r"[a-z0-9]+", query) if len(t) >= 3]
            match_count = sum(1 for t in tokens if t in cand_text)
            score = 10.0 if match_count > 0 or not tokens else 5.0
            if score >= 6.0:
                ranked.append({"sku": sku, "score": score})

        if not ranked and candidate_lines:
            ranked = [{"sku": candidate_lines[0][0], "score": 10.0}]

        return json.dumps(ranked)

    @staticmethod
    def synthesis_response(prompt: str) -> str:
        """Generate grounded narrative and recommendations with [SKU: ...] citations."""
        # Find all product specifications in prompt
        prod_matches = re.findall(
            r"- Product:\s*([^\[]+)\[SKU:\s*([A-Za-z0-9_-]+)\]\s*\|\s*Brand:\s*([^|]+)\|\s*Price:\s*\$([0-9\.,]+)\s*\|\s*Specs:\s*(\{.*?\})",
            prompt,
        )

        if not prod_matches or len(prod_matches) < 2:
            return ComparisonSynthesis(
                summary="No comparative catalog items found to compare.",
                recommendations=None,
            ).model_dump_json()

        name1, sku1, brand1, price1_str, specs1_raw = prod_matches[0]
        name2, sku2, brand2, price2_str, specs2_raw = prod_matches[1]

        name1 = name1.strip()
        name2 = name2.strip()
        price1 = float(price1_str.replace(",", ""))
        price2 = float(price2_str.replace(",", ""))

        try:
            specs1 = json.loads(specs1_raw)
        except Exception:
            specs1 = {}
        try:
            specs2 = json.loads(specs2_raw)
        except Exception:
            specs2 = {}

        summary_lines = [
            f"Direct comparison between {name1} [SKU: {sku1}] and {name2} [SKU: {sku2}]:",
        ]

        if price1 < price2:
            diff = price2 - price1
            summary_lines.append(
                f"- Price: {name1} [SKU: {sku1}] is ${diff:,.2f} more affordable at ${price1:,.2f} versus ${price2:,.2f} for {name2} [SKU: {sku2}]."
            )
        elif price2 < price1:
            diff = price1 - price2
            summary_lines.append(
                f"- Price: {name2} [SKU: {sku2}] is ${diff:,.2f} more affordable at ${price2:,.2f} versus ${price1:,.2f} for {name1} [SKU: {sku1}]."
            )
        else:
            summary_lines.append(f"- Price: Both products are priced identically at ${price1:,.2f}.")

        b1 = specs1.get("battery_life_hours")
        b2 = specs2.get("battery_life_hours")
        if b1 is not None and b2 is not None:
            if b1 > b2:
                summary_lines.append(
                    f"- Battery Life: {name1} [SKU: {sku1}] leads with up to {b1} hours of battery life versus {b2} hours on {name2} [SKU: {sku2}]."
                )
            elif b2 > b1:
                summary_lines.append(
                    f"- Battery Life: {name2} [SKU: {sku2}] leads with up to {b2} hours of battery life versus {b1} hours on {name1} [SKU: {sku1}]."
                )

        ram1 = specs1.get("ram_gb")
        ram2 = specs2.get("ram_gb")
        cpu1 = specs1.get("processor")
        cpu2 = specs2.get("processor")
        if ram1 or ram2 or cpu1 or cpu2:
            summary_lines.append(
                f"- Performance: {name1} [SKU: {sku1}] features {cpu1 or 'N/A'} with {ram1 or 'N/A'}GB RAM; "
                f"{name2} [SKU: {sku2}] features {cpu2 or 'N/A'} with {ram2 or 'N/A'}GB RAM."
            )

        w1 = specs1.get("weight_lbs")
        w2 = specs2.get("weight_lbs")
        if w1 is not None and w2 is not None:
            if w1 < w2:
                summary_lines.append(
                    f"- Weight: {name1} [SKU: {sku1}] is lighter and more portable at {w1} lbs versus {w2} lbs for {name2} [SKU: {sku2}]."
                )
            elif w2 < w1:
                summary_lines.append(
                    f"- Weight: {name2} [SKU: {sku2}] is lighter and more portable at {w2} lbs versus {w1} lbs for {name1} [SKU: {sku1}]."
                )
            else:
                summary_lines.append(f"- Weight: Both products weigh identically at {w1} lbs.")

        s1 = specs1.get("storage_gb")
        s2 = specs2.get("storage_gb")
        if s1 is not None and s2 is not None and s1 != s2:
            if s1 > s2:
                summary_lines.append(
                    f"- Storage: {name1} [SKU: {sku1}] offers more storage at {s1}GB versus {s2}GB for {name2} [SKU: {sku2}]."
                )
            else:
                summary_lines.append(
                    f"- Storage: {name2} [SKU: {sku2}] offers more storage at {s2}GB versus {s1}GB for {name1} [SKU: {sku1}]."
                )

        disp1 = specs1.get("display_resolution") or (f"{specs1['display_size_in']}\"" if specs1.get("display_size_in") else None)
        disp2 = specs2.get("display_resolution") or (f"{specs2['display_size_in']}\"" if specs2.get("display_size_in") else None)
        if disp1 or disp2:
            summary_lines.append(
                f"- Display: {name1} [SKU: {sku1}] features {disp1 or 'standard display'}; "
                f"{name2} [SKU: {sku2}] features {disp2 or 'standard display'}."
            )

        os1 = specs1.get("operating_system")
        os2 = specs2.get("operating_system")
        if os1 or os2:
            summary_lines.append(
                f"- Operating System: {name1} [SKU: {sku1}] runs {os1 or 'N/A'}; "
                f"{name2} [SKU: {sku2}] runs {os2 or 'N/A'}."
            )

        rec_parts = ["Key Buying Recommendations:"]
        if b1 is not None and b2 is not None and b1 > b2:
            rec_parts.append(
                f"- Best for Battery & Portability: Choose {name1} [SKU: {sku1}] for all-day endurance."
            )
        elif b1 is not None and b2 is not None and b2 > b1:
            rec_parts.append(
                f"- Best for Battery & Portability: Choose {name2} [SKU: {sku2}] for all-day endurance."
            )

        if price1 < price2:
            rec_parts.append(
                f"- Best Value for Money: {name1} [SKU: {sku1}] offers excellent performance per dollar."
            )
        elif price2 < price1:
            rec_parts.append(
                f"- Best Value for Money: {name2} [SKU: {sku2}] provides maximum cost efficiency."
            )

        return ComparisonSynthesis(
            summary="\n".join(summary_lines),
            recommendations="\n".join(rec_parts) if len(rec_parts) > 1 else None,
        ).model_dump_json()


def create_hermetic_genai_client() -> MagicMock:
    """Factory to construct a mock google.genai.Client responding via HermeticModelAdapter."""
    client = MagicMock()

    def mock_generate_content(model: str = "", contents: Any = "", config: Any = None, **kwargs: Any) -> MagicMock:
        prompt = str(contents)
        response = MagicMock()

        usage = MagicMock()
        usage.prompt_token_count = 150
        usage.candidates_token_count = 200
        response.usage_metadata = usage
        candidate = MagicMock()
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]

        # 1. Intent classification
        if "Query Intent Specialist" in prompt or "classify its intent" in prompt:
            user_query_match = re.search(r"<user_query>(.*?)</user_query>", prompt, re.DOTALL)
            query = user_query_match.group(1) if user_query_match else prompt
            intent_analysis = HermeticModelAdapter.classify_intent_response(query)
            response.text = intent_analysis.model_dump_json()
            return response

        # 2. Candidate reranking
        if "relevance judge" in prompt or "Candidates:" in prompt:
            response.text = HermeticModelAdapter.rerank_response(prompt)
            return response

        # 3. Narrative synthesis
        if "Comparison Specialist" in prompt or "Retrieved Catalog Products:" in prompt:
            response.text = HermeticModelAdapter.synthesis_response(prompt)
            return response

        # Default fallback
        response.text = "{}"
        return response

    client.models.generate_content.side_effect = mock_generate_content
    return client
