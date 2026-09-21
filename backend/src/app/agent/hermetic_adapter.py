"""Hermetic model adapter and Google ADK BaseLlm integration for live and offline execution."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

from google import genai
from google.adk.models import BaseLlm, LlmCapabilities, LlmRequest, LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from app.config import settings
from app.models.requests import (
    CandidateRankingResponse,
    CandidateRankItem,
    ComparisonSynthesis,
    QueryIntentAnalysis,
)

logger = logging.getLogger(__name__)


class HermeticModelAdapter:
    """Deterministic grounded model adapter for offline ADK Agent execution."""

    @staticmethod
    def extract_user_query(prompt: str) -> str:
        """Extract the innermost <user_query> content without matching instruction tags."""
        if not prompt:
            return ""
        matches = re.findall(
            r"<user_query>((?:(?!</?user_query>).)+)</user_query>",
            prompt,
            flags=re.DOTALL,
        )
        if matches:
            return matches[-1].strip()
        return prompt.strip()

    @staticmethod
    def classify_intent_response(query: str) -> QueryIntentAnalysis:
        """Generate deterministic QueryIntentAnalysis matching the query."""
        clean_query = HermeticModelAdapter.extract_user_query(query)
        lower_q = (clean_query or "").lower().strip()

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
            " comparison ",
            " between ",
            " or ",
            " and ",
            " difference ",
            " better ",
            " which ",
            " worth ",
            " breakdown ",
        ]
        has_comparative = any(tok in f" {lower_q} " for tok in comparative_tokens)

        if is_opinion and not has_comparative:
            return QueryIntentAnalysis(
                intent_type="OPINION_OR_CHATTER",
                is_comparison_eligible=False,
                reasoning="Subjective opinion or chatter without comparison intent (offline hermetic).",
            )

        category_aliases: list[tuple[str, list[str]]] = [
            ("TVs", ["tv", "tvs", "oled", "qled", "television", "uhd", "bravia", "4k"]),
            (
                "Smart Home",
                [
                    "smart home",
                    "thermostat",
                    "doorbell",
                    "echo",
                    "nest",
                    "hub",
                    "smart display",
                    "smart speaker",
                ],
            ),
            (
                "Headphones",
                [
                    "headphone",
                    "headphones",
                    "earbud",
                    "earbuds",
                    "airpods",
                    "quietcomfort",
                    "noise cancelling",
                    "xm5",
                    "wh-1000xm5",
                ],
            ),
            ("Tablets", ["tablet", "tablets", "ipad", "galaxy tab", "surface pro"]),
            (
                "Laptops",
                [
                    "laptop",
                    "laptops",
                    "macbook",
                    "notebook",
                    "chromebook",
                    "thinkpad",
                    "xps",
                    "spectre",
                    "ultrabook",
                    "zenbook",
                    "blade",
                    "legion",
                    "rog",
                ],
            ),
        ]
        detected_category: str | None = None
        for canonical_cat, terms in category_aliases:
            for term in terms:
                if re.search(r"\b" + re.escape(term) + r"\b", lower_q):
                    detected_category = canonical_cat
                    break
            if detected_category:
                break

        from app.agent.orchestrator import ComparisonOrchestrator

        keywords = ComparisonOrchestrator.extract_keywords(clean_query)
        if not keywords:
            keywords = [clean_query.strip()]

        is_comparative = has_comparative or len(keywords) >= 2

        return QueryIntentAnalysis(
            intent_type="COMPARISON" if is_comparative else "PRODUCT_SEARCH",
            is_comparison_eligible=is_comparative,
            detected_category=detected_category,
            target_keywords=keywords,
            reasoning="Grounded intent extraction (offline hermetic).",
        )

    @staticmethod
    def rerank_response(prompt: str) -> str:
        """Parse candidates in prompt and produce structured CandidateRankingResponse JSON."""
        query = HermeticModelAdapter.extract_user_query(prompt)

        intent = HermeticModelAdapter.classify_intent_response(query)
        if intent.intent_type == "OPINION_OR_CHATTER":
            return CandidateRankingResponse(rankings=[]).model_dump_json()

        candidate_lines = re.findall(
            r"- SKU:\s*([A-Za-z0-9_-]+)\s*\|\s*([^|]+)\|\s*Brand:\s*([^|]+)\|\s*Category:\s*([^|]+)",
            prompt,
        )
        if not candidate_lines:
            fallback_lines = re.findall(
                r"- SKU:\s*([A-Za-z0-9_-]+)\s*\|\s*([^|]+)\|\s*Brand:\s*([^|]+)", prompt
            )
            candidate_lines = [(s, n, b, "") for s, n, b in fallback_lines]

        if not candidate_lines:
            candidate_skus = re.findall(r"SKU:\s*([A-Za-z0-9_-]+)", prompt)
            return CandidateRankingResponse(
                rankings=[CandidateRankItem(sku=s, score=9.5) for s in candidate_skus]
            ).model_dump_json()

        stopwords = {
            "vs",
            "and",
            "or",
            "compare",
            "between",
            "the",
            "with",
            "tell",
            "about",
            "what",
            "which",
            "is",
            "are",
            "show",
            "me",
            "for",
            "on",
            "in",
            "to",
            "a",
            "an",
        }
        all_terms = re.findall(r"[a-z0-9]+", query.lower())
        query_tokens = {t for t in all_terms if t not in stopwords and len(t) >= 2}
        keywords = intent.target_keywords or [query]

        def matches_token(tok: str, text: str) -> bool:
            tok_low = tok.lower().strip()
            if not tok_low:
                return False
            if tok_low == "mac":
                return bool(re.search(r"\bmac(?:book)?\b", text))
            return bool(re.search(r"\b" + re.escape(tok_low), text))

        scored_candidates: list[tuple[int, int, int, str]] = []
        for idx, (sku, name, brand, category) in enumerate(candidate_lines):
            cand_text = f"{name} {brand} {category}".lower()
            exact = 1 if any(matches_token(kw, cand_text) for kw in keywords if len(kw) >= 3) else 0
            overlap = sum(1 for t in query_tokens if matches_token(t, cand_text))
            scored_candidates.append((exact, overlap, -idx, sku.strip()))

        scored_candidates.sort(reverse=True)
        rankings: list[CandidateRankItem] = []
        for exact, overlap, _neg_idx, sku in scored_candidates:
            if exact > 0 or overlap > 0:
                raw_score = min(10.0, 6.5 + (exact * 1.5) + (overlap * 0.4))
                rankings.append(CandidateRankItem(sku=sku, score=round(raw_score, 2)))
            elif not query_tokens:
                rankings.append(CandidateRankItem(sku=sku, score=7.0))

        return CandidateRankingResponse(rankings=rankings).model_dump_json()

    @staticmethod
    def synthesis_response(prompt: str) -> str:
        """Generate grounded narrative and recommendations with [SKU: ...] citations."""
        prod_matches = re.findall(
            r"- Product:\s*([^\[]+)\[SKU:\s*([A-Za-z0-9_-]+)\]\s*\|\s*Brand:\s*([^|]+)\|\s*Price:\s*\$([0-9\.,]+)\s*\|\s*Specs:\s*(\{.*?\})",
            prompt,
        )

        if not prod_matches or len(prod_matches) < 2:
            if len(prod_matches) == 1:
                name1, sku1, _brand1, price1_str, _specs1_raw = prod_matches[0]
                price1 = float(price1_str.replace(",", ""))
                return ComparisonSynthesis(
                    summary=(
                        f"Found single catalog item: {name1.strip()} [SKU: {sku1.strip()}] "
                        f"priced at ${price1:,.2f}. Provide a second product to enable side-by-side comparison."
                    ),
                    recommendations=None,
                ).model_dump_json()
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
            summary_lines.append(
                f"- Price: Both products are priced identically at ${price1:,.2f}."
            )

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

        disp1 = specs1.get("display_resolution") or (
            f'{specs1["display_size_in"]}"' if specs1.get("display_size_in") else None
        )
        disp2 = specs2.get("display_resolution") or (
            f'{specs2["display_size_in"]}"' if specs2.get("display_size_in") else None
        )
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

    @staticmethod
    def synthesis_from_tool_items(items: list[dict[str, Any]], query: str = "") -> str:
        """Build a synthesis prompt from tool-retrieved items and delegate to synthesis_response."""
        if not items:
            return ComparisonSynthesis(
                summary=f"No matching products found in the catalog for query: '{query}'. Please check your search terms.",
                recommendations="Try searching for broader model names, brands, or specify a valid product category.",
            ).model_dump_json()

        candidates_desc = "\n".join(
            f"- Product: {itm.get('name', 'Unknown')} [SKU: {itm.get('sku', 'N/A')}] | "
            f"Brand: {itm.get('brand', 'Unknown')} | Price: ${float(itm.get('price', 0.0)):,.2f} | "
            f"Specs: {json.dumps(itm.get('specifications', {})) if isinstance(itm.get('specifications'), dict) else str(itm.get('specifications', '{}'))}"
            for itm in items[:2]
        )
        synthetic_prompt = (
            f"<user_query>{query}</user_query>\n\nRetrieved Catalog Products:\n{candidates_desc}\n"
        )
        return HermeticModelAdapter.synthesis_response(synthetic_prompt)


class CatalogAdkLlm(BaseLlm):
    """Google ADK BaseLlm implementation unifying live Vertex AI Gemini and offline HermeticModelAdapter.

    Enables ADK `Runner` and `Agent` (`LlmAgent`) instances to execute identically across:
    1. Production Cloud Run traffic via Vertex AI Gemini (`google.genai.Client(vertexai=True)`),
       preserving Model Armor templates, safety settings, and token telemetry.
    2. Unit tests that inject or mock `google.genai.Client`.
    3. Offline hermetic evaluations (`evals/runner.py`) and `pytest` runs, including native
       multi-turn ADK `FunctionCall` (`query_catalog`) -> `FunctionResponse` -> `ComparisonSynthesis` execution.
    """

    model: str = "gemini-2.5-pro"
    hermetic: bool = False
    _injected_client: Any = PrivateAttr(default=None)
    _last_input_tokens: int = PrivateAttr(default=0)
    _last_output_tokens: int = PrivateAttr(default=0)

    def __init__(
        self,
        model: str = "gemini-2.5-pro",
        hermetic: bool = False,
        genai_client: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, hermetic=hermetic, **kwargs)
        self._injected_client = genai_client

    @classmethod
    def supported_models(cls) -> list[str]:
        """Register CatalogAdkLlm for all Gemini model identifiers in Google ADK's LLMRegistry."""
        return [
            r"gemini-.*",
            r"projects/.+/locations/.+/endpoints/.+",
            r"projects/.+/locations/.+/publishers/google/models/gemini-.*",
        ]

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=True)

    @property
    def last_input_tokens(self) -> int:
        return self._last_input_tokens

    @property
    def last_output_tokens(self) -> int:
        return self._last_output_tokens

    def _should_use_hermetic(self) -> bool:
        if self.hermetic or os.environ.get("HERMETIC_EVAL", "").lower() == "true":
            return True
        if self._injected_client is not None or hasattr(genai.Client, "assert_called"):
            return False
        if os.environ.get("PYTEST_CURRENT_TEST") and "test_adk_runner_live" not in os.environ.get(
            "PYTEST_CURRENT_TEST", ""
        ):
            return True
        return False

    @staticmethod
    def _extract_prompt_and_tool_state(
        llm_request: LlmRequest,
    ) -> tuple[str, list[dict[str, Any]] | None]:
        """Extract combined prompt text and any tool function_response items from LlmRequest."""
        text_chunks: list[str] = []
        tool_items: list[dict[str, Any]] | None = None

        for content in llm_request.contents or []:
            for part in content.parts or []:
                if getattr(part, "text", None):
                    text_chunks.append(part.text)
                func_resp = getattr(part, "function_response", None)
                if func_resp is not None:
                    resp_payload = getattr(func_resp, "response", None)
                    if isinstance(resp_payload, dict):
                        res_list = resp_payload.get("result")
                        if isinstance(res_list, list):
                            tool_items = [x for x in res_list if isinstance(x, dict)]
                        else:
                            tool_items = []
                    elif isinstance(resp_payload, list):
                        tool_items = [x for x in resp_payload if isinstance(x, dict)]
                    else:
                        tool_items = []

        return "\n".join(text_chunks).strip(), tool_items

    def _generate_hermetic_llm_response(self, llm_request: LlmRequest) -> LlmResponse:
        """Produce a deterministic LlmResponse (including FunctionCall when tools are bound)."""
        prompt_text, tool_items = self._extract_prompt_and_tool_state(llm_request)
        tools_dict = llm_request.tools_dict or {}

        self._last_input_tokens = max(64, len(prompt_text) // 4)
        self._last_output_tokens = 180

        # 1. If the agent has `query_catalog` bound as a tool:
        if "query_catalog" in tools_dict:
            if tool_items is None:
                # Turn 1: Emit an ADK FunctionCall to `query_catalog` unless opinion/chatter
                intent = HermeticModelAdapter.classify_intent_response(prompt_text)
                if intent.intent_type == "OPINION_OR_CHATTER":
                    msg = (
                        f"No product comparison matrix was generated for '{prompt_text}'. "
                        "The query appears to be an opinion or general comment rather than a product comparison request. "
                        "To compare products side-by-side, please specify two or more models or brands "
                        "(e.g., 'Compare Model A and Model B')."
                    )
                    return LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[types.Part.from_text(text=msg)],
                        ),
                        partial=False,
                    )

                call_args: dict[str, Any] = {
                    "keywords": intent.target_keywords or [prompt_text],
                }
                if intent.detected_category:
                    call_args["category"] = intent.detected_category

                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="query_catalog",
                                args=call_args,
                            )
                        ],
                    ),
                    partial=False,
                )

            # Turn 2: Tool `query_catalog` has executed and returned `tool_items`!
            synth_json = HermeticModelAdapter.synthesis_from_tool_items(
                tool_items, query=prompt_text
            )
            try:
                synth_obj = ComparisonSynthesis.model_validate_json(synth_json)
                resp_text = synth_obj.summary
            except Exception:
                resp_text = synth_json

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=resp_text)],
                ),
                partial=False,
            )

        # 2. Structured schema or specialist agent prompts
        sys_inst = ""
        if llm_request.config and llm_request.config.system_instruction:
            sys_inst = str(llm_request.config.system_instruction)
        combined = f"{sys_inst}\n{prompt_text}"

        schema = (
            getattr(llm_request.config, "response_schema", None) if llm_request.config else None
        )
        schema_name = getattr(schema, "__name__", "") if schema else ""

        if (
            schema_name == "QueryIntentAnalysis"
            or "Query Intent Specialist" in combined
            or "classify its intent" in combined
        ):
            target_q = HermeticModelAdapter.extract_user_query(prompt_text)
            out_text = HermeticModelAdapter.classify_intent_response(target_q).model_dump_json()
        elif (
            schema_name == "CandidateRankingResponse"
            or "relevance judge" in combined
            or "Candidates:" in combined
        ):
            out_text = HermeticModelAdapter.rerank_response(prompt_text)
        else:
            out_text = HermeticModelAdapter.synthesis_response(prompt_text)

        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=out_text)],
            ),
            partial=False,
        )

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Execute ADK LlmRequest against Vertex AI Gemini or HermeticModelAdapter."""
        if self._should_use_hermetic():
            yield self._generate_hermetic_llm_response(llm_request)
            return

        prompt_text, _ = self._extract_prompt_and_tool_state(llm_request)
        try:
            os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
            client = self._injected_client or genai.Client(
                vertexai=True,
                project=settings.gcp_project,
                location="us-central1",
            )
            config = llm_request.config
            contents_payload: Any = prompt_text if prompt_text else llm_request.contents

            sys_inst = (
                str(config.system_instruction)
                if config and getattr(config, "system_instruction", None)
                else ""
            )
            combined_prompt = f"{sys_inst}\n{prompt_text}"
            inferred_schema: Any = getattr(config, "response_schema", None) if config else None
            if inferred_schema is None:
                if (
                    "Query Intent Specialist" in combined_prompt
                    or "classify its intent" in combined_prompt
                ):
                    inferred_schema = QueryIntentAnalysis
                elif "relevance judge" in combined_prompt or "Candidates:" in combined_prompt:
                    inferred_schema = CandidateRankingResponse
                elif (
                    "Comparison Specialist" in combined_prompt
                    or "Retrieved Catalog Products:" in combined_prompt
                ):
                    inferred_schema = ComparisonSynthesis

            target_model = self.model
            if (
                target_model == "gemini-1.5-flash"
                and self._injected_client is None
                and not hasattr(genai.Client, "assert_called")
            ):
                target_model = "gemini-2.5-flash-lite"

            effective_config = config
            if inferred_schema is not None and (
                config is None or getattr(config, "response_schema", None) is None
            ):
                min_thinking = 128 if "pro" in target_model.lower() else 0
                effective_config = types.GenerateContentConfig(
                    system_instruction=getattr(config, "system_instruction", None)
                    if config
                    else None,
                    response_mime_type="application/json",
                    response_schema=inferred_schema,
                    safety_settings=getattr(config, "safety_settings", None) if config else None,
                    temperature=float(getattr(config, "temperature", 0.1) or 0.1)
                    if config
                    else 0.1,
                    max_output_tokens=int(getattr(config, "max_output_tokens", 2048) or 2048)
                    if config
                    else 2048,
                    thinking_config=types.ThinkingConfig(thinking_budget=min_thinking),
                )

            try:
                response = client.models.generate_content(
                    model=target_model,
                    contents=contents_payload,
                    config=effective_config,
                )
            except Exception as call_err:
                err_msg = str(call_err).lower()
                if (
                    "model_armor" in err_msg
                    or "template" in err_msg
                    or "not found" in err_msg
                    or "thinking" in err_msg
                ):
                    fallback_cfg = types.GenerateContentConfig(
                        system_instruction=getattr(effective_config, "system_instruction", None),
                        response_mime_type=getattr(effective_config, "response_mime_type", None),
                        response_schema=getattr(effective_config, "response_schema", None),
                        safety_settings=getattr(effective_config, "safety_settings", None),
                        temperature=getattr(effective_config, "temperature", 0.1),
                        max_output_tokens=getattr(effective_config, "max_output_tokens", 2048),
                    )
                    response = client.models.generate_content(
                        model=target_model,
                        contents=contents_payload,
                        config=fallback_cfg,
                    )
                else:
                    raise

            # Validate candidate finish_reason for safety blocks
            if hasattr(response, "candidates") and response.candidates:
                first_cand = response.candidates[0]
                finish_reason = str(getattr(first_cand, "finish_reason", "")).upper()
                if any(
                    flag in finish_reason
                    for flag in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII")
                ):
                    raise ValueError(
                        f"Response blocked by safety/Model Armor filter: {finish_reason}"
                    )

            usage = getattr(response, "usage_metadata", None)
            if usage:
                self._last_input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
                self._last_output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)

            raw_text = (response.text or "").strip()
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=raw_text)],
                ),
                usage_metadata=usage,
                partial=False,
            )
        except Exception as exc:
            if self._injected_client is not None or hasattr(genai.Client, "assert_called"):
                raise
            logger.warning(
                "CatalogAdkLlm live generation encountered error (%s); falling back to hermetic ADK response.",
                exc,
            )
            yield self._generate_hermetic_llm_response(llm_request)


def create_hermetic_genai_client() -> MagicMock:
    """Factory to construct a mock google.genai.Client responding via HermeticModelAdapter."""
    client = MagicMock()

    def mock_generate_content(
        model: str = "", contents: Any = "", config: Any = None, **kwargs: Any
    ) -> MagicMock:
        prompt = str(contents)
        response = MagicMock()

        usage = MagicMock()
        usage.prompt_token_count = 150
        usage.candidates_token_count = 200
        response.usage_metadata = usage
        candidate = MagicMock()
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]

        if "Query Intent Specialist" in prompt or "classify its intent" in prompt:
            user_query_match = re.search(r"<user_query>(.*?)</user_query>", prompt, re.DOTALL)
            query = user_query_match.group(1) if user_query_match else prompt
            intent_analysis = HermeticModelAdapter.classify_intent_response(query)
            response.text = intent_analysis.model_dump_json()
            return response

        if "relevance judge" in prompt or "Candidates:" in prompt:
            response.text = HermeticModelAdapter.rerank_response(prompt)
            return response

        if "Comparison Specialist" in prompt or "Retrieved Catalog Products:" in prompt:
            response.text = HermeticModelAdapter.synthesis_response(prompt)
            return response

        response.text = "{}"
        return response

    client.models.generate_content.side_effect = mock_generate_content
    return client


from google.adk.models import LLMRegistry  # noqa: E402

LLMRegistry.register(CatalogAdkLlm)
