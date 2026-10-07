import asyncio
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, ClassVar

from google import genai
from google.adk.agents import Agent
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import bigquery
from google.genai import types

from app.agent.adk_llm import (
    CatalogAdkLlm,
    _check_model_armor_prompt_guard,
    _check_model_armor_response_guard,
    _get_vertex_client_for_model,
    _is_preview_or_3x_model,
)
from app.agent.matrix_evaluator import MatrixEvaluator, format_spec_label
from app.agent.prompts import (
    SYSTEM_INSTRUCTION,
    format_followup_chat_prompt,
    format_stage1_intent_prompt,
    format_stage4_matrix_winners_prompt,
    format_stage4_synthesis_prompt,
)
from app.agent.prompts_service import get_active_prompt, get_stage_prompt
from app.agent.registry import default_registry
from app.config import settings
from app.models.comparison import (
    ComparisonSynthesis,
    SpecWinnersSynthesis,
)
from app.models.requests import (
    ChatMessage,
    ComparisonRequest,
    QueryIntentAnalysis,
)
from app.models.responses import (
    ChatResponse,
    Citation,
    CompareResponse,
    MatrixRow,
    ProductSpec,
)
from app.observability.tracing import get_current_trace_id, get_tracer
from app.tools.catalog import query_catalog

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
_DEFAULT_GENAI_CLIENT_CLS = genai.Client
_DEFAULT_MA_PROMPT_GUARD = _check_model_armor_prompt_guard


class SecurityViolationError(RuntimeError):
    """Raised when Google Cloud Model Armor blocks a prompt or model response."""


_SPECULATIVE_SYNTH_POOL = ThreadPoolExecutor(max_workers=512, thread_name_prefix="spec-llm")
_CHAT_PERSIST_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="chat-persist")


def _build_thinking_config(model_id: str | None) -> types.ThinkingConfig | None:
    """Construct ThinkingConfig for Gemini models.

    gemini-2.5-pro supports bounded thinking (thinking_budget=128) for fast structured JSON synthesis.
    All Flash and Flash-Lite models (2.0, 2.5, 3.x) use thinking_budget=0 to avoid unbounded CoT latency.
    """
    if not model_id:
        return None
    m = model_id.lower()
    if "2.5-pro" in m:
        return types.ThinkingConfig(thinking_budget=128)
    if "1.5" in m or "pro" in m:
        return None
    if "flash" in m or "lite" in m:
        return types.ThinkingConfig(thinking_budget=0)
    return None


def _extract_json_snippet(text: str) -> str:
    """Robustly extract a JSON object or array from LLM response text that may contain markdown code fences or conversational text."""
    if not text:
        return ""
    cleaned = text.strip()
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()
    first_brace = cleaned.find("{")
    first_bracket = cleaned.find("[")
    start_idx = -1
    end_idx = -1
    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        start_idx = first_brace
        end_idx = cleaned.rfind("}")
    elif first_bracket != -1:
        start_idx = first_bracket
        end_idx = cleaned.rfind("]")

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return cleaned[start_idx : end_idx + 1]

    return cleaned


_SPEC_LABELS: dict[str, str] = {
    "processor": "Processor / CPU",
    "ram_gb": "Memory (RAM)",
    "storage_gb": "Storage (SSD)",
    "battery_life_hours": "Battery Life",
    "battery_life_months": "Battery Life (Months)",
    "display_size_in": "Display Size",
    "screen_size_in": "Screen Size",
    "display_resolution": "Display Resolution",
    "refresh_rate_hz": "Refresh Rate",
    "weight_lbs": "Weight",
    "weight_oz": "Weight (oz)",
    "bluetooth_version": "Bluetooth Version",
    "ports": "Ports & Connectivity",
    "driver_size_mm": "Driver Size",
    "noise_canceling": "Active Noise Canceling",
    "sensor_range_ft": "Sensor Detection Range",
    "response_time_ms": "Response Time",
    "panel_type": "Display Panel Type",
    "hdr_support": "HDR Format Support",
    "smart_platform": "Smart Platform / Ecosystem",
    "connectivity": "Wireless Connectivity",
    "voice_assistant": "Voice Assistant",
}


def _format_spec_label(spec_key: str) -> str:
    """Format a specification key into a human-readable matrix feature label."""
    if spec_key in _SPEC_LABELS:
        return _SPEC_LABELS[spec_key]
    return spec_key.replace("_", " ").title()


def _format_spec_value(spec_key: str, raw_val: Any) -> str:
    """Format a raw specification value with appropriate units."""
    if raw_val is None:
        return "Not specified"
    if spec_key == "storage_gb" and isinstance(raw_val, (int, float)):
        return f"{raw_val} GB" if raw_val < 1000 else f"{raw_val / 1000:g} TB"
    if spec_key == "battery_life_hours" and isinstance(raw_val, (int, float)):
        return f"Up to {raw_val} hours"
    if isinstance(raw_val, bool):
        return "Yes" if raw_val else "No"
    if isinstance(raw_val, (int, float)):
        suffix_units = (
            ("_gb", " GB"),
            ("_months", " months"),
            ("_in", '"'),
            ("_hz", " Hz"),
            ("_lbs", " lbs"),
            ("_oz", " oz"),
            ("_mm", " mm"),
            ("_ft", " ft"),
            ("_ms", " ms"),
            ("_db", " dB"),
            ("_nits", " nits"),
            ("_w", " W"),
        )
        for suffix, unit in suffix_units:
            if spec_key.endswith(suffix):
                return f"{raw_val}{unit}"
        return str(raw_val)
    if isinstance(raw_val, list):
        return ", ".join(str(item) for item in raw_val)
    return str(raw_val)


# Standalone spec attributes blocklist to prevent spec features from being extracted as distinct product entities
SPEC_ATTRIBUTES_BLOCKLIST: set[str] = {
    "dolby vision",
    "hdr10+",
    "hdr10",
    "hdr",
    "oled",
    "qled",
    "mini-led",
    "4k",
    "4k tv",
    "4k tvs",
    "8k",
    "1080p",
    "ram",
    "battery life",
    "battery",
    "weight",
    "refresh rate",
    "hdmi",
    "bluetooth",
    "wifi",
    "anc",
    "noise canceling",
    "display",
    "screen",
    "price",
}


def sanitize_user_prompt(prompt: str) -> str:
    """Sanitize user input to neutralize prompt injection, jailbreak attacks, and XML delimiter escaping.

    1. Neutralizes adversarial injection phrases (e.g. 'ignore previous instructions', 'system override').
    2. Escapes XML delimiter characters (< and >) to prevent escaping boundary isolation tags.
    3. Normalizes excessive whitespace and limits prompt boundaries.
    """
    if not prompt:
        return ""

    # Neutralize common jailbreak & prompt injection vectors
    injection_patterns = [
        r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|above)?\s*instructions?",
        r"(?i)disregard\s+(?:all\s+)?(?:previous|prior|above)?\s*guidelines?",
        r"(?i)system\s+(?:prompt|override|command)",
        r"(?i)you\s+are\s+now\s+in\s+dan\s+mode",
        r"(?i)developer\s+mode\s+output",
        r"(?i)jailbreak",
        r"(?i)repeat\s+(?:the\s+)?(?:system|hidden)\s+prompt",
        r"(?i)reveal\s+(?:the\s+)?(?:system|hidden)\s+prompt",
    ]
    sanitized = prompt
    for pattern in injection_patterns:
        sanitized = re.sub(pattern, "[BLOCKED_INJECTION]", sanitized)

    # Escape XML tags to preserve boundary isolation
    sanitized = sanitized.replace("<", "&lt;").replace(">", "&gt;")

    return sanitized.strip()


def get_model_armor_config(
    mode: str = "both",
    model: str | None = None,
    is_mock_env: bool = False,
) -> types.ModelArmorConfig | None:
    """Construct Google Cloud Model Armor configuration scoped to the active stage and model region.

    Gemini 2.x models run in regional us-central1 and attach inline ModelArmorConfig.
    Gemini 3.x / preview models run in location='global', which rejects regional ModelArmorConfig
    templates inline; returning None delegates those models to the regional REST guard.

    Args:
        mode: One of:
            - "both": Attach both prompt and response guard templates (Conversational Agent).
            - "prompt_only": Attach only the prompt guard template (Stage 1 User Input).
            - "response_only": Attach only the response guard template (Stage 3/4 Model Output).
        model: Target Gemini model ID.
        is_mock_env: True when running under unit test mocks that inspect inline config.
    """
    if not getattr(settings, "enable_model_armor", True):
        return None
    if model and not is_mock_env and _is_preview_or_3x_model(model):
        return None
    prompt_tmpl = settings.model_armor_prompt_template if mode in ("both", "prompt_only") else None
    resp_tmpl = (
        settings.model_armor_response_template if mode in ("both", "response_only") else None
    )
    if not prompt_tmpl and not resp_tmpl:
        return None
    return types.ModelArmorConfig(
        prompt_template_name=prompt_tmpl,
        response_template_name=resp_tmpl,
    )


STAGE_OPTIMAL_MODELS: dict[str, str] = {
    "stage1_intent": "gemini-3.5-flash-lite",
    "stage2_retrieval": "deterministic-bq-sql",
    "stage2_relevance": "gemini-2.5-flash-lite",
    "stage3_synthesis": "gemini-3.5-flash-lite",
    "stage3_fast_synthesis": "gemini-2.5-flash-lite",
    "stage4_matrix_winners": "gemini-2.5-flash-lite",
    "stage5_chat": "gemini-2.5-flash",
}


def resolve_stage_models(fast_synthesis: bool = False) -> dict[str, str]:
    """Resolve optimal models per specialist pipeline stage from env vars, settings, or defaults."""
    s1 = (
        os.environ.get("STAGE1_INTENT_MODEL")
        or getattr(settings, "stage1_intent_model", None)
        or STAGE_OPTIMAL_MODELS["stage1_intent"]
    )
    s2 = (
        os.environ.get("STAGE2_RELEVANCE_MODEL")
        or os.environ.get("STAGE3_RELEVANCE_MODEL")
        or getattr(settings, "stage2_relevance_model", None)
        or STAGE_OPTIMAL_MODELS["stage2_relevance"]
    )
    s3 = (
        (
            os.environ.get("STAGE3_FAST_SYNTHESIS_MODEL")
            or getattr(settings, "stage3_fast_synthesis_model", None)
            or STAGE_OPTIMAL_MODELS["stage3_fast_synthesis"]
        )
        if fast_synthesis
        else (
            os.environ.get("STAGE3_SYNTHESIS_MODEL")
            or os.environ.get("STAGE4_SYNTHESIS_MODEL")
            or getattr(settings, "stage3_synthesis_model", None)
            or STAGE_OPTIMAL_MODELS["stage3_synthesis"]
        )
    )
    s4_mw = (
        os.environ.get("STAGE4_MATRIX_WINNERS_MODEL")
        or getattr(settings, "stage4_matrix_winners_model", None)
        or STAGE_OPTIMAL_MODELS["stage4_matrix_winners"]
    )
    s5_chat = (
        os.environ.get("STAGE5_CHAT_MODEL")
        or os.environ.get("GEMINI_MODEL")
        or getattr(settings, "stage5_chat_model", None)
        or getattr(settings, "gemini_model", None)
        or STAGE_OPTIMAL_MODELS["stage5_chat"]
    )
    return {
        "stage1_intent": s1,
        "stage2_retrieval": "deterministic-bq-sql",
        "stage2_relevance": s2,
        "stage3_synthesis": s3,
        "stage4_matrix_winners": s4_mw,
        "stage5_chat": s5_chat,
    }


def resolve_model_pair(
    model: str | None = None,
    synthesis_model: str | None = None,
    default_model: str | None = None,
) -> tuple[str, str, bool]:
    """Resolve routing/intent model and synthesis model, supporting 'tiered-hybrid' and 'stage-optimal' routing.

    Returns:
        tuple[str, str, bool]: (routing_model, synthesis_model, is_tiered_hybrid)
    """
    fallback = (
        default_model
        or os.environ.get("GEMINI_MODEL")
        or getattr(settings, "gemini_model", "gemini-2.5-flash")
    )
    raw_model = (model or fallback or "").strip()

    if raw_model.lower() == "stage-optimal":
        stage_cfg = resolve_stage_models()
        routing = stage_cfg["stage1_intent"]
        syn = (synthesis_model or "").strip()
        synthesis = (
            syn
            if syn and syn.lower() not in ("stage-optimal", "tiered-hybrid")
            else stage_cfg["stage3_synthesis"]
        )
        return routing, synthesis, True

    if raw_model.lower() == "tiered-hybrid":
        routing = "gemini-2.5-flash"
        syn = (synthesis_model or "").strip()
        synthesis = syn if syn and syn.lower() != "tiered-hybrid" else "gemini-2.5-pro"
        return routing, synthesis, True

    routing = raw_model or "gemini-2.5-flash"
    syn = (synthesis_model or "").strip()
    synthesis = syn if syn and syn.lower() != "tiered-hybrid" else routing
    is_hybrid = routing != synthesis
    return routing, synthesis, is_hybrid


async def generate_memories_callback(callback_context: Any) -> None:
    """ADK after_agent_callback to automatically ingest session events into Memory Bank."""
    if hasattr(callback_context, "add_session_to_memory"):
        try:
            await callback_context.add_session_to_memory()
        except Exception as exc:
            logger.debug("add_session_to_memory callback note: %s", exc)
    return None


def create_adk_agent(
    model: str | None = None,
    synthesis_model: str | None = None,
    name: str = "catalog_comparison_orchestrator",
    instruction: str = SYSTEM_INSTRUCTION,
    before_model_callback: Any = None,
) -> Agent:
    """Factory to instantiate a Google ADK Agent with dynamic model swappability and memory tools."""
    from app.agent.compaction import prune_tool_outputs_callback

    _, resolved_synthesis, _ = resolve_model_pair(model=model, synthesis_model=synthesis_model)
    return Agent(
        name=name,
        model=resolved_synthesis,
        instruction=instruction,
        tools=[query_catalog, PreloadMemoryTool()],
        before_model_callback=(
            before_model_callback
            if before_model_callback is not None
            else prune_tool_outputs_callback
        ),
        after_agent_callback=generate_memories_callback,
    )


# Core ADK Root Agent definition
catalog_agent = create_adk_agent(
    model=settings.gemini_model,
    name="catalog_comparison_orchestrator",
)


class _SynthesisResult(tuple):
    """2-tuple (summary, recommendations) that also exposes ComparisonSynthesis attributes."""

    summary: str
    recommendations: str | None
    spec_winners: dict[str, str]

    def __new__(
        cls,
        summary: str,
        recommendations: str | None,
        spec_winners: dict[str, str] | None = None,
    ) -> "_SynthesisResult":
        instance = super().__new__(cls, (summary, recommendations))
        instance.summary = summary
        instance.recommendations = recommendations
        instance.spec_winners = dict(spec_winners or {})
        return instance


def _unpack_synthesis_result(
    res: Any,
    orchestrator: "ComparisonOrchestrator",
    products: list[ProductSpec],
    query: str,
    matrix: list[MatrixRow] | None = None,
) -> tuple[str, str | None]:
    if isinstance(res, ComparisonSynthesis):
        if matrix is not None:
            matrix[:] = orchestrator.build_comparison_matrix(
                products, query=query, spec_winners=res.spec_winners
            )
        return (
            orchestrator.verify_and_align_claim_citations(res.summary, products) or "",
            orchestrator.verify_and_align_claim_citations(res.recommendations, products),
        )
    if matrix is not None and not matrix:
        matrix[:] = orchestrator.build_comparison_matrix(
            products, query=query, spec_winners=getattr(res, "spec_winners", None)
        )
    summary_val, recs_val = res
    return summary_val, recs_val


class ComparisonOrchestrator:
    """Orchestrator for managing catalog comparison workflows and grounded synthesis."""

    GENERIC_FOCUS_PHRASES: ClassVar[frozenset[str]] = frozenset(
        {
            "compare specifications, trade-offs, and recommend the best option",
            "compare specifications, trade-offs and recommend the best option",
            "compare specifications, trade offs, and recommend the best option",
            "compare specifications, trade offs and recommend the best option",
            "compare specifications and recommend the best option",
            "compare specifications",
            "compare products",
            "side-by-side comparison",
            "side by side comparison",
            "general comparison",
            "standard comparison",
            "default",
            "none",
            "n/a",
            "no preference",
            "no preferences",
            "overview",
            "recommend the best option",
            "all specs",
            "all specifications",
        }
    )

    @staticmethod
    def _is_structured_comparison_prompt(query: str) -> bool:
        """Return True if query is a structured prompt embedding product specifications."""
        if not query:
            return False
        q_lower = query.lower()
        return (
            "compare the following products:" in q_lower
            or bool(re.search(r"Product\s+\d+:\s*.+?\[SKU:\s*\w+\]", query, re.IGNORECASE))
            or (
                "specifications:" in q_lower
                and bool(re.search(r"Product\s+\d+:", query, re.IGNORECASE))
            )
        )

    def __init__(
        self,
        bq_client: bigquery.Client | None = None,
        genai_client: Any = None,
        model: str | None = None,
        synthesis_model: str | None = None,
        repository: Any = None,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("hermetic", None)
        self.bq_client = bq_client
        self.repository = repository
        self.genai_client = genai_client
        self._injected_model = model
        self._injected_synthesis_model = synthesis_model
        self.configured_model_id: str = model or getattr(settings, "gemini_model", "gemini-2.5-pro")
        self.model, self.synthesis_model, self.is_tiered_hybrid = resolve_model_pair(
            model=model,
            synthesis_model=synthesis_model,
        )
        self.active_system_instruction: str = SYSTEM_INSTRUCTION
        self.adk_agent = create_adk_agent(
            model=model,
            synthesis_model=synthesis_model,
            instruction=self.active_system_instruction,
        )
        self.matrix_evaluator = MatrixEvaluator()
        self._thread_local = threading.local()
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self._active_category_hint = None
        self.last_synthesis_model: str = self.synthesis_model
        if self.genai_client is None and getattr(settings, "enable_background_warmup", False):
            from app.agent.adk_llm import (
                _get_shared_vertex_client,
                _warm_vertex_client_and_auth,
            )

            _get_shared_vertex_client()
            _warm_vertex_client_and_auth()

    @property
    def last_input_tokens(self) -> int:
        return int(getattr(self._thread_local, "last_input_tokens", 0))

    @last_input_tokens.setter
    def last_input_tokens(self, value: int) -> None:
        self._thread_local.last_input_tokens = int(value)

    @property
    def last_output_tokens(self) -> int:
        return int(getattr(self._thread_local, "last_output_tokens", 0))

    @last_output_tokens.setter
    def last_output_tokens(self, value: int) -> None:
        self._thread_local.last_output_tokens = int(value)

    @property
    def _active_category_hint(self) -> str | None:
        return getattr(self._thread_local, "active_category_hint", None)

    @_active_category_hint.setter
    def _active_category_hint(self, value: str | None) -> None:
        self._thread_local.active_category_hint = value

    def _get_genai_client(self, model: str | None = None) -> Any:
        """Return injected genai_client if provided, or return the shared Vertex AI genai.Client."""
        if self.genai_client is not None:
            return self.genai_client

        target_model = model or self.model
        return _get_vertex_client_for_model(target_model)

    def _call_genai_with_failover(
        self,
        client: Any,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig,
    ) -> Any:
        """Invoke Vertex AI generate_content in us-central1 with failover on transient errors."""
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as err:
            from app.agent.adk_llm import (
                _get_shared_vertex_client,
                _is_preview_or_3x_model,
            )

            if _is_preview_or_3x_model(model):
                logger.info(
                    "Model %s call on global endpoint failed (%s); failing over to us-central1",
                    model,
                    err,
                )
                fb_client = self.genai_client or _get_shared_vertex_client(location="us-central1")
                return fb_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )

            if "404" in str(err) and model.startswith("gemini-1.5"):
                fallback_25 = "gemini-2.5-pro" if "pro" in model else "gemini-2.5-flash"
                logger.info(
                    "Model %s returned 404 NOT_FOUND; failing over to %s",
                    model,
                    fallback_25,
                )
                return client.models.generate_content(
                    model=fallback_25,
                    contents=contents,
                    config=config,
                )

            if any(
                tok in str(err).lower()
                for tok in (
                    "429",
                    "resource_exhausted",
                    "preempted",
                    "503",
                    "unavailable",
                    "deadline",
                    "overloaded",
                )
            ):
                time.sleep(0.1)
                fb_client = self.genai_client or _get_shared_vertex_client(location="us-central1")
                return fb_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            raise err

    @staticmethod
    def _infer_category_from_query(query: str) -> str | None:
        """Infer explicit product category from query tokens so Stage 1 prelaunch matches Stage 2 category filter."""
        lower_q = f" {(query or '').lower()} "
        category_patterns = (
            (
                "Laptops",
                (
                    " laptop ",
                    " laptops ",
                    " macbook ",
                    " thinkpad ",
                    " xps ",
                    " specter ",
                    " spectre ",
                ),
            ),
            ("Tablets", (" tablet ", " tablets ", " ipad ", " galaxy tab ", " surface pro ")),
            (
                "Headphones",
                (
                    " headphone ",
                    " headphones ",
                    " earbuds ",
                    " airpods ",
                    " wh-1000",
                    " quietcomfort ",
                ),
            ),
            ("TVs", (" tv ", " tvs ", " oled ", " qled ", " bravia ")),
            (
                "Smartphones",
                (
                    " phone ",
                    " phones ",
                    " smartphone ",
                    " smartphones ",
                    " iphone ",
                    " pixel 8",
                    " pixel 9",
                    " galaxy s2",
                ),
            ),
        )
        for cat, tokens in category_patterns:
            if any(tok in lower_q for tok in tokens):
                return cat
        return None

    @staticmethod
    def extract_tagged_products(query: str) -> list[tuple[str, str]]:
        """Extract product names and SKUs from explicit comparison prompts (e.g. buildComparisonPrompt).

        Matches:
        - 'Product N: <Name> [(Brand)] [SKU: <sku>]'
        - '<Name> ... [SKU: <sku>]'
        - Standalone '[SKU: <sku>]'
        """
        if not query:
            return []
        # Pattern 1: Product N: <Name> [(Brand)] [SKU: <sku>]
        matches_product_n = re.findall(
            r"Product\s*\d+:\s*([^[(\n\r]+?)(?:\s*\([^)]*\))?\s*\[SKU:\s*([A-Za-z0-9_-]+)\]",
            query,
            re.IGNORECASE,
        )
        if matches_product_n:
            return [
                (name.strip(), sku.strip())
                for name, sku in matches_product_n
                if name.strip() or sku.strip()
            ]

        # Pattern 2: <Name> [SKU: <sku>]
        matches_general = re.findall(
            r"([^[,\n\r]+?)\s*\[SKU:\s*([A-Za-z0-9_-]+)\]",
            query,
            re.IGNORECASE,
        )
        results = []
        for raw_name, sku in matches_general:
            name = re.sub(
                r"^(?:compare|and|vs\.?|versus|or)\s+", "", raw_name.strip(), flags=re.IGNORECASE
            ).strip()
            if name or sku:
                results.append((name, sku.strip()))
        if results:
            return results

        # Pattern 3: Standalone [SKU: <sku>]
        standalone_skus = re.findall(r"\[SKU:\s*([A-Za-z0-9_-]+)\]", query)
        return [("", s.strip()) for s in standalone_skus]

    @staticmethod
    def extract_keywords(query: str) -> list[str]:
        """Parse natural language query into target candidate keywords using brand-agnostic syntactic extraction."""
        cleaned = query.strip()

        # Check for explicit tagged products/SKUs from buildComparisonPrompt or inline tags
        tagged = ComparisonOrchestrator.extract_tagged_products(cleaned)
        if tagged:
            names = [name for name, _sku in tagged if name]
            if names:
                return names
            skus = [sku for _name, sku in tagged if sku]
            if skus:
                return skus

        # If a colon is present (e.g. 'Price and processor breakdown: MacBook Air vs Dell XPS 13'
        # or 'Sony WH-1000XM5 versus Apple AirPods Max: battery life, weight, and price comparison'),
        # determine which side contains the comparative entities versus the topic/attribute lead-in.
        if ":" in cleaned:
            prefix, after = cleaned.split(":", 1)
            strong_markers = r"\b(?:vs\.?|versus|compared to|against)\b"
            has_prefix_strong = bool(re.search(strong_markers, prefix, re.IGNORECASE))
            has_after_strong = bool(re.search(strong_markers, after, re.IGNORECASE))
            prefix_is_question = bool(
                re.match(r"^\s*(?:which|what|how|is|are|can|tell|why)\b", prefix, re.IGNORECASE)
            )

            if has_prefix_strong and not has_after_strong:
                cleaned = prefix.strip()
            elif has_after_strong and not has_prefix_strong:
                cleaned = after.strip()
            elif prefix_is_question and not bool(
                re.match(r"^\s*(?:which|what|how|is|are)\b", after, re.IGNORECASE)
            ):
                cleaned = after.strip()
            elif re.match(
                r"^\s*(?:compare|comparison|side-by-side|breakdown|evaluate|review)\b",
                prefix,
                re.IGNORECASE,
            ) and ("," in after or re.search(r"\b(?:and|vs\.?|versus|or)\b", after, re.IGNORECASE)):
                cleaned = after.strip()
            else:
                attr_words = r"\b(?:battery|price|weight|specs?|specifications?|display|screen|performance|features?|breakdown|differences?|comparison|chip|cheaper|better|faster|longer|lighter)\b"
                prefix_attrs = len(re.findall(attr_words, prefix, re.IGNORECASE))
                after_attrs = len(re.findall(attr_words, after, re.IGNORECASE))
                if prefix_attrs > after_attrs:
                    cleaned = after.strip()
                elif after_attrs > prefix_attrs:
                    cleaned = prefix.strip()
                elif re.search(r"\b(?:or|vs\.?|versus)\b", after, re.IGNORECASE):
                    cleaned = after.strip()
                elif len(after.strip().split()) >= len(prefix.strip().split()):
                    cleaned = after.strip()
                else:
                    cleaned = prefix.strip()

        # Strip conversational and question lead-ins
        cleaned = re.sub(
            r"^(?:tell me about|tell me more about|what about|show me|can you compare|describe|info on|details for|search for|find me|give me info on|tell me|compare|difference between|what (?:are the )?differences between|which (?:is|has) (?:better|cheaper|lighter|longer)|is the|is|do|does|summary of differences between)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Strip generic topic/attribute prefixes ONLY if followed by 'of', 'between', 'for'
        cleaned = re.sub(
            r"^(?:[a-zA-Z0-9\s,&/-]+?\s+(?:breakdown|comparison|differences?|compatibility)\s+(?:of|between|for)\s+)",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Strip trailing attribute qualifiers (e.g. '... on price and battery life', '... for travel comfort and ANC')
        cleaned = re.sub(
            r"\s+(?:on|for|regarding|in terms of|based on)\s+(?:price|battery|weight|specs|display|screen|performance|ram|storage|features|ratings?|travel|comfort|noise|anc).*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Strip trailing topic / comparison words (e.g. '... display size and memory comparison', '... screen comparison', '... comparison')
        trailing_attr_regex = re.compile(
            r"\s+(?:(?:display(?:\s+size)?|screen(?:\s+size)?|amoled(?:\s+screen)?|oled(?:\s+screen)?|memory|battery(?:\s+life)?|price|weight|specs?|specifications?|performance|ram|storage|contrast|colors?|refresh\s+rate|ports?|connectivity|smart\s+features?|audio)\s*(?:and|,|&)?\s*)*(?:breakdown|comparison|differences?)\s*$",
            re.IGNORECASE,
        )
        cleaned = trailing_attr_regex.sub("", cleaned)

        cleaned = re.sub(r"[\?:\.!]+", " ", cleaned)

        # Split on comparative conjunctions and prepositions
        parts = re.split(
            r"\b(?:and|vs\.?|versus|or|with|compared to|against|than|over|more than|worth [^\b]+ over)\b|,",
            cleaned,
            flags=re.IGNORECASE,
        )
        keywords = [p.strip() for p in parts if len(p.strip()) >= 2]
        if not keywords:
            # Fallback to non-stopword tokens
            tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 3]
            keywords = tokens if tokens else [cleaned.strip()]
        return keywords

    def build_comparison_matrix(
        self,
        products: list[ProductSpec],
        query: str = "",
        spec_winners: dict[str, str] | None = None,
    ) -> list[MatrixRow]:
        """Align product specifications side-by-side across all 5 categories and determine winners.

        Uses MatrixEvaluator across the greater set of non-warehouse specs for up to 5 products,
        evaluating polarities where missing specs automatically lose, and respecting Stage 4 LLM
        spec_winners overrides when provided.
        """
        evaluator = getattr(self, "matrix_evaluator", None) or MatrixEvaluator()
        rows = evaluator.evaluate_matrix(products, query=query, spec_winners=spec_winners)

        # Extract explicit User Focus / Follow-up line if present to prevent spec keys in prompt body
        # (e.g. * battery_life_hours: 18) from false-triggering focus ordering.
        focus_match = re.search(r"User Focus\s*/\s*Follow-up:\s*(.+)", query or "", re.IGNORECASE)
        if focus_match:
            effective_query = focus_match.group(1).strip()
            norm_focus = re.sub(r"^[\"'\s]+|[\"'\s.,;!]+$", "", effective_query.lower()).strip()
            if norm_focus in self.GENERIC_FOCUS_PHRASES:
                effective_query = ""
        else:
            is_structured = self._is_structured_comparison_prompt(query or "")
            effective_query = "" if is_structured else (query or "").strip()
        clean_query = effective_query.lower()

        is_only_price = any(
            phrase in clean_query
            for phrase in (
                "only price",
                "price only",
                "just price",
                "strictly price",
                "only the price",
            )
        )
        if is_only_price:
            return [r for r in rows if r.feature == "Price"]

        # Intent-driven spec key prioritization
        priority_keys: list[str] = []
        if any(term in clean_query for term in ("gaming", "game", "gamer", "fps", "esports")):
            priority_keys = [
                "refresh_rate_hz",
                "response_time_ms",
                "processor",
                "ram_gb",
                "display_resolution",
                "storage_gb",
            ]
        elif any(
            term in clean_query
            for term in ("office", "work", "business", "productivity", "study", "school")
        ):
            priority_keys = [
                "battery_life_hours",
                "weight_lbs",
                "ram_gb",
                "processor",
                "storage_gb",
                "display_size_in",
            ]
        elif any(
            term in clean_query
            for term in ("battery", "travel", "portability", "commute", "endurance", "lightweight")
        ):
            priority_keys = [
                "battery_life_hours",
                "weight_lbs",
                "weight_oz",
                "display_size_in",
                "battery_life_months",
            ]
        elif any(
            term in clean_query
            for term in ("display", "screen", "oled", "resolution", "vision", "color")
        ):
            priority_keys = [
                "display_resolution",
                "screen_size_in",
                "display_size_in",
                "refresh_rate_hz",
                "panel_type",
                "hdr_support",
            ]
        elif any(
            term in clean_query for term in ("audio", "sound", "noise", "anc", "music", "headphone")
        ):
            priority_keys = [
                "noise_canceling",
                "driver_size_mm",
                "battery_life_hours",
                "bluetooth_version",
                "weight_oz",
                "connectivity",
            ]

        if priority_keys:
            header_features = {"Category", "Price", "Customer Rating"}
            header_rows = [r for r in rows if r.feature in header_features]
            spec_rows = [r for r in rows if r.feature not in header_features]

            priority_labels = [format_spec_label(k) for k in priority_keys]

            def _spec_sort_order(row: MatrixRow) -> int:
                try:
                    return priority_labels.index(row.feature)
                except ValueError:
                    return len(priority_labels) + 100

            spec_rows.sort(key=_spec_sort_order)
            return header_rows + spec_rows

        return rows

    _NON_COMPARATIVE_SPEC_KEYS: frozenset[str] = frozenset(
        {
            "upc",
            "model_number",
            "product_type",
            "subcategory",
            "taxonomy_path",
            "warranty",
            "shipping_tier",
        }
    )

    @staticmethod
    def _short_product_label(p: ProductSpec) -> str:
        """Return '<Brand> - <Model>' or '<Brand> <Model>' without trailing catalog spec suffixes."""
        raw_name = (p.name or "").strip()
        if " - " not in raw_name:
            return raw_name
        parts = [seg.strip() for seg in raw_name.split(" - ") if seg.strip()]
        if not parts:
            return raw_name
        brand_lower = (p.brand or "").strip().lower()
        if len(parts) >= 2 and brand_lower and parts[0].lower() == brand_lower:
            return f"{parts[0]} - {parts[1]}"
        return parts[0]

    @classmethod
    def _filter_comparative_specs(cls, specs: dict[str, Any] | None) -> dict[str, Any]:
        """Strip non-comparative warehouse/inventory metadata keys from specifications."""
        if not specs:
            return {}
        return {
            k: v
            for k, v in specs.items()
            if str(k).strip().lower() not in cls._NON_COMPARATIVE_SPEC_KEYS
        }

    def _build_synthesis_prompt(
        self,
        products: list[ProductSpec],
        matrix: list[MatrixRow],
        query: str,
    ) -> str:
        candidates_desc = "\n".join(
            f"- {self._short_product_label(p)} [SKU: {p.sku}] | {p.brand} | ${p.price:.2f} | "
            + ", ".join(
                f"{k}={v}" for k, v in self._filter_comparative_specs(p.specifications).items()
            )
            for p in products
        )
        matrix_desc = ""
        price_grounding = ""
        if len(products) >= 2:
            sorted_by_price = sorted(products, key=lambda x: x.price)
            cheapest = sorted_by_price[0]
            most_exp = sorted_by_price[-1]
            if cheapest.price < most_exp.price:
                diff = most_exp.price - cheapest.price
                price_grounding = (
                    f"Price Grounding: {self._short_product_label(cheapest)} [SKU: {cheapest.sku}] "
                    f"(${cheapest.price:,.2f}) is ${diff:,.2f} cheaper than "
                    f"{self._short_product_label(most_exp)} [SKU: {most_exp.sku}] (${most_exp.price:,.2f})."
                )
            else:
                price_grounding = f"Price Grounding: Equal price ${cheapest.price:,.2f}."

        num_prods = len(products)
        summary_word_limit = 60 if num_prods <= 2 else min(75, 40 + num_prods * 7)
        recs_word_limit = 30 if num_prods <= 2 else min(50, 18 + num_prods * 6)
        sku_tags_list = ", ".join(
            f"'{self._short_product_label(p)}' [SKU: {p.sku}]" for p in products
        )
        all_spec_keys: list[str] = []
        for p in products:
            for k in self._filter_comparative_specs(p.specifications).keys():
                if k not in all_spec_keys:
                    all_spec_keys.append(k)
        spec_keys_str = ", ".join(all_spec_keys) if all_spec_keys else "all specification keys"
        example_sku = products[0].sku if products else "SKU"

        effective_query = query
        if (
            query
            and "Specifications:" in query
            and re.search(r"Product\s*1:", query, re.IGNORECASE)
        ):
            focus_m = re.search(r"User Focus\s*/\s*Follow-up:\s*(.+)", query, re.IGNORECASE)
            focus_line = f" | Focus: {focus_m.group(1).strip()}" if focus_m else ""
            effective_query = f"Compare {num_prods} products.{focus_line}"

        stage4_tpl, _ = get_stage_prompt("stage4")
        if stage4_tpl and (
            "spec_winners" in stage4_tpl
            or "Short Product Name" not in stage4_tpl
            or "<catalog_products>" not in stage4_tpl
        ):
            stage4_tpl = None
        return format_stage4_synthesis_prompt(
            num_prods=num_prods,
            sku_tags_list=sku_tags_list,
            summary_word_limit=summary_word_limit,
            recs_word_limit=recs_word_limit,
            spec_keys_str=spec_keys_str,
            example_sku=example_sku,
            query=effective_query,
            candidates_desc=candidates_desc,
            matrix_desc=matrix_desc,
            price_grounding=price_grounding,
            template=stage4_tpl,
        )

    @classmethod
    def _detect_customer_preferences(cls, query: str) -> tuple[bool, str]:
        """Detect whether query contains extra user constraints/preferences vs clean product comparison."""
        if not query:
            return False, ""
        # 1. Explicit User Focus / Follow-up line
        focus_m = re.search(r"User Focus\s*/\s*Follow-up:\s*(.+)", query, re.IGNORECASE)
        if focus_m:
            f_val = focus_m.group(1).strip()
            norm_val = re.sub(r"^[\"'\s]+|[\"'\s.,;!]+$", "", f_val.lower()).strip()
            if not norm_val or norm_val in cls.GENERIC_FOCUS_PHRASES:
                return False, ""
            return True, f_val

        # 2. Structured prompt isolation: if query is a structured comparison prompt
        # without explicit non-generic user focus, the search bar was empty.
        # Do not scan prompt body to avoid false positives from catalog specs (e.g. Battery Life).
        if cls._is_structured_comparison_prompt(query):
            return False, ""

        clean_q = query.lower().strip()
        # Look for "for <context>" phrases like "for travel", "for coding", "for editing"
        for_m = re.search(r"\bfor\s+([a-z0-9_\-\s]{2,40})", clean_q)
        if for_m:
            candidate = for_m.group(1).strip()
            if candidate and not candidate.startswith("sale"):
                return True, candidate

        contextual_kws = (
            "travel",
            "coding",
            "editing",
            "gaming",
            "gamer",
            "game",
            "fps",
            "esports",
            "office",
            "work",
            "business",
            "productivity",
            "study",
            "school",
            "commute",
            "portability",
            "lightweight",
            "student",
            "developer",
            "creator",
            "programming",
            "audio",
            "sound",
            "budget",
            "cheap",
            "battery life",
            "long battery",
            "battery endurance",
            "prefer",
            "prioritize",
            "best for",
        )
        for kw in contextual_kws:
            if re.search(rf"\b{re.escape(kw)}\b", clean_q):
                return True, kw

        return False, ""

    def _build_matrix_winners_prompt(
        self,
        products: list[ProductSpec],
        customer_preferences: str | None = None,
    ) -> tuple[str, list[str]]:
        """Build the prompt for the parallel Stage 4 MatrixWinnerAgent (SpecWinnersSynthesis)."""
        evaluator = getattr(self, "matrix_evaluator", None) or MatrixEvaluator()
        all_spec_keys = evaluator.collect_greater_spec_keys(products)
        if not all_spec_keys:
            return "", []

        candidates_desc = "\n".join(
            f"- {self._short_product_label(p)} [SKU: {p.sku}] | "
            + ", ".join(
                f"{k}: {v}" for k, v in self._filter_comparative_specs(p.specifications).items()
            )
            for p in products
        )
        sku_tags_list = ", ".join(
            f"'{self._short_product_label(p)}' [SKU: {p.sku}]" for p in products
        )
        spec_keys_str = ", ".join(all_spec_keys)
        example_sku = products[0].sku if products else "SKU"
        prompt = format_stage4_matrix_winners_prompt(
            sku_tags_list=sku_tags_list,
            spec_keys_str=spec_keys_str,
            example_sku=example_sku,
            candidates_desc=candidates_desc,
            customer_preferences=customer_preferences,
        )
        return prompt, all_spec_keys

    def _run_matrix_winners_llm(
        self,
        client: Any,
        call_model: str,
        matrix_prompt: str,
        armor_cfg: Any,
        thinking_cfg: Any,
        is_mock_env: bool,
        clean_json_fn: Any,
    ) -> tuple[dict[str, str], int, int]:
        """Execute the parallel MatrixWinnerAgent LLM call returning (spec_winners, in_tokens, out_tokens)."""
        if not matrix_prompt:
            return {}, 0, 0
        matrix_cfg = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SpecWinnersSynthesis if is_mock_env else None,
            model_armor_config=armor_cfg if armor_cfg is not None else None,
            temperature=float(getattr(settings, "temperature", 0.1)),
            max_output_tokens=512,
            thinking_config=thinking_cfg,
        )
        with tracer.start_as_current_span("gemini.synthesize_matrix_winners") as mw_span:
            mw_span.set_attribute("gen_ai.system", "vertexai")
            mw_span.set_attribute("gen_ai.request.model", call_model)
            try:
                mw_resp = self._call_genai_with_failover(
                    client,
                    call_model,
                    matrix_prompt,
                    matrix_cfg,
                )
            except Exception as mw_err:
                if armor_cfg is not None:
                    fallback_mw_cfg = types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=SpecWinnersSynthesis if is_mock_env else None,
                        temperature=float(getattr(settings, "temperature", 0.1)),
                        max_output_tokens=512,
                        thinking_config=thinking_cfg,
                    )
                    mw_resp = self._call_genai_with_failover(
                        client,
                        call_model,
                        matrix_prompt,
                        fallback_mw_cfg,
                    )
                else:
                    logger.debug("Parallel matrix winners call failed (%s)", mw_err)
                    return {}, 0, 0

            in_toks = 0
            out_toks = 0
            usage = getattr(mw_resp, "usage_metadata", None)
            if usage:
                in_toks = int(getattr(usage, "prompt_token_count", 0) or 0)
                out_toks = int(getattr(usage, "candidates_token_count", 0) or 0)
                mw_span.set_attribute("gen_ai.usage.prompt_tokens", in_toks)
                mw_span.set_attribute("gen_ai.usage.completion_tokens", out_toks)

            raw_text = getattr(mw_resp, "text", None)
            if not raw_text:
                return {}, in_toks, out_toks
            try:
                cleaned = clean_json_fn(raw_text)
                parsed = SpecWinnersSynthesis.model_validate_json(cleaned)
                return dict(parsed.spec_winners or {}), in_toks, out_toks
            except Exception as val_err:
                logger.debug("Matrix winners JSON parse fallback (%s)", val_err)
                try:
                    raw_obj = json.loads(clean_json_fn(raw_text))
                    if isinstance(raw_obj, dict):
                        sw = raw_obj.get("spec_winners", raw_obj)
                        if isinstance(sw, dict):
                            return (
                                {str(k): str(v) for k, v in sw.items() if v is not None},
                                in_toks,
                                out_toks,
                            )
                except Exception:
                    pass
                return {}, in_toks, out_toks

    @staticmethod
    def verify_and_scrub_sku_citations(text: str | None, valid_skus: set[str]) -> str | None:
        """Post-generation grounding check: scrub any hallucinated [SKU: <id>] citation not in valid_skus."""
        if not text:
            return text

        def _check_sku(match: re.Match[str]) -> str:
            cited_sku = match.group(1).strip()
            if cited_sku in valid_skus:
                return match.group(0)
            return ""

        scrubbed = re.sub(r"\[SKU:\s*([^\]]+)\]", _check_sku, text)
        return re.sub(r"  +", " ", scrubbed).strip()

    @staticmethod
    def verify_and_align_claim_citations(
        text: str | None, products: list[ProductSpec]
    ) -> str | None:
        """Deterministically verify, validate, and scrub claim-to-SKU citations.

        Strict Rules:
        1. Never artificially inject or append [SKU: ...] tags that the LLM did not generate.
        2. Scrub any hallucinated [SKU: <id>] citation where <id> is not in the retrieved products.
        3. Scrub/reject any [SKU: <id>] citation if the immediate clause directly contradicts
           the cited product's identity (e.g. citing SKU X immediately following a competing
           brand's distinct product name).
        """
        if not text:
            return text
        if not products:
            return text

        valid_skus = {p.sku for p in products if p.sku}
        sku_to_prod = {p.sku: p for p in products if p.sku}

        # Step 1: Scrub any hallucinated SKUs not in valid_skus
        def _check_sku_membership(match: re.Match[str]) -> str:
            cited_sku = match.group(1).strip()
            if cited_sku in valid_skus:
                return match.group(0)
            return ""

        scrubbed = re.sub(r"\[SKU:\s*([^\]]+)\]", _check_sku_membership, text)

        # Step 2: Verify claim-to-SKU alignment across clauses
        def _verify_clause_attribution(match: re.Match[str]) -> str:
            cited_sku = match.group(1).strip()
            prod = sku_to_prod.get(cited_sku)
            if not prod:
                return ""

            start_pos = match.start()
            preceding = scrubbed[max(0, start_pos - 60) : start_pos]
            preceding_lower = preceding.lower()

            prod_brand_lower = (prod.brand or "").strip().lower()
            for other_p in products:
                other_brand_lower = (other_p.brand or "").strip().lower()
                if (
                    other_brand_lower
                    and other_brand_lower != prod_brand_lower
                    and re.search(rf"\b{re.escape(other_brand_lower)}\b", preceding_lower)
                    and not re.search(rf"\b{re.escape(prod_brand_lower)}\b", preceding_lower)
                ):
                    # Contradicting brand claim: cited prod brand does not match the named brand
                    return ""

            return match.group(0)

        result = re.sub(r"\[SKU:\s*([^\]]+)\]", _verify_clause_attribution, scrubbed)
        result = re.sub(r"  +", " ", result)
        return result.strip()

    _NARRATIVE_SYNTHESIS_SCHEMA: dict[str, Any] = {
        "type": "OBJECT",
        "properties": {
            "summary": {"type": "STRING"},
            "recommendations": {"type": "STRING"},
        },
        "required": ["summary", "recommendations"],
    }

    def synthesize_comparison_with_llm(
        self,
        products: list[ProductSpec],
        matrix: list[MatrixRow],
        query: str = "",
        model: str | None = None,
    ) -> "_SynthesisResult":
        """Synthesize grounded comparison narrative, persona recommendations, and spec_winners using 2 parallel Gemini calls."""
        if not products:
            return _SynthesisResult("No matching products found in the catalog to compare.", None)

        if len(products) == 1:
            p = products[0]
            return _SynthesisResult(
                f"Found single catalog item: {p.name} [SKU: {p.sku}] priced at ${p.price:,.2f}. "
                "Provide a second product to enable side-by-side comparison.",
                None,
            )

        active_model = model or self.synthesis_model
        self.last_synthesis_model = active_model

        has_preferences, pref_text = self._detect_customer_preferences(query)

        # Pre-populate matrix deterministically if empty (0ms)
        if matrix is not None and not matrix:
            matrix[:] = self.build_comparison_matrix(products, query=query)

        prompt = self._build_synthesis_prompt(products, matrix, sanitize_user_prompt(query))

        is_mock_env = self.genai_client is not None or genai.Client is not _DEFAULT_GENAI_CLIENT_CLS
        _, call_model, _ = resolve_model_pair(model=active_model, synthesis_model=active_model)
        client = self._get_genai_client(model=call_model)
        armor_cfg = (
            get_model_armor_config(
                mode="response_only",
                model=call_model,
                is_mock_env=is_mock_env,
            )
            if is_mock_env
            else None
        )
        thinking_cfg = _build_thinking_config(call_model)
        narrative_sys_inst = self.active_system_instruction if is_mock_env else None
        config = types.GenerateContentConfig(
            system_instruction=narrative_sys_inst,
            response_mime_type="application/json",
            response_schema=self._NARRATIVE_SYNTHESIS_SCHEMA if is_mock_env else None,
            model_armor_config=armor_cfg if armor_cfg is not None else None,
            temperature=float(getattr(settings, "temperature", 0.1)),
            max_output_tokens=1024,
            thinking_config=thinking_cfg,
        )

        def _clean_synthesis_json(txt: str) -> str:
            raw_t = (txt or "").strip()
            if "```" in raw_t:
                if "```json" in raw_t:
                    raw_t = raw_t.split("```json", 1)[1].split("```", 1)[0].strip()
                else:
                    raw_t = raw_t.split("```", 1)[1].split("```", 1)[0].strip()
            if "{" not in raw_t:
                return raw_t
            s_idx = raw_t.find("{")
            if "}" in raw_t[s_idx:]:
                e_idx = raw_t.rfind("}")
                sliced = raw_t[s_idx : e_idx + 1]
                try:
                    json.loads(sliced)
                    return sliced
                except Exception:
                    try:
                        json.loads(sliced + "}")
                        return sliced + "}"
                    except Exception:
                        pass
            # Robust handling of unclosed JSON string/brace from token truncation
            cand = raw_t[s_idx:].strip()
            in_str = False
            esc = False
            depth = 0
            for ch in cand:
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                elif not in_str:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth = max(0, depth - 1)
            if in_str:
                cand += '"'
            cand = cand.rstrip().rstrip(",")
            if cand.endswith(":"):
                cand += '""'
            if depth > 0:
                cand += "}" * depth
            try:
                json.loads(cand)
                return cand
            except Exception:
                sum_m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)', raw_t[s_idx:], re.DOTALL)
                rec_m = re.search(
                    r'"recommendations"\s*:\s*"((?:[^"\\]|\\.)*)', raw_t[s_idx:], re.DOTALL
                )
                if sum_m:
                    sum_val = sum_m.group(1).replace("\\n", "\n").replace('\\"', '"')
                    rec_val = (
                        rec_m.group(1).replace("\\n", "\n").replace('\\"', '"') if rec_m else None
                    )
                    return json.dumps(
                        {
                            "summary": sum_val,
                            "recommendations": rec_val,
                            "spec_winners": {},
                        }
                    )
                return cand

        # Hybrid router:
        # If query is clean product comparison without extra user constraints/focus,
        # execute build_comparison_matrix deterministically in 0ms without spawning _run_matrix_winners_llm.
        # If user provides extra constraints/preferences (User Focus / Follow-up or contextual keywords
        # like for travel, coding, editing), route a fast call to gemini-2.5-flash-lite
        # with <customer_preferences> conditioning, max_output_tokens=128, and response_schema=SpecWinnersSynthesis.
        matrix_fut: Future[tuple[dict[str, str], int, int]] | None = None
        if has_preferences:
            pref_matrix_prompt, _ = self._build_matrix_winners_prompt(
                products, customer_preferences=pref_text
            )
            if pref_matrix_prompt:
                mw_model = resolve_stage_models().get(
                    "stage4_matrix_winners", "gemini-2.5-flash-lite"
                )
                if not mw_model or "pro" in mw_model.lower():
                    mw_model = "gemini-2.5-flash-lite"
                mw_client = client if is_mock_env else self._get_genai_client(model=mw_model)
                mw_thinking_cfg = _build_thinking_config(mw_model)
                matrix_fut = _SPECULATIVE_SYNTH_POOL.submit(
                    self._run_matrix_winners_llm,
                    mw_client,
                    mw_model,
                    pref_matrix_prompt,
                    armor_cfg if is_mock_env else None,
                    mw_thinking_cfg,
                    is_mock_env,
                    _clean_synthesis_json,
                )

        with tracer.start_as_current_span("gemini.synthesize_comparison") as llm_span:
            llm_span.set_attribute("gen_ai.system", "vertexai")
            llm_span.set_attribute("gen_ai.request.model", call_model)
            llm_span.set_attribute("agent.stage4.parallel_agents", bool(matrix_fut is not None))
            try:
                response = self._call_genai_with_failover(
                    client,
                    call_model,
                    prompt,
                    config,
                )
            except Exception as call_err:
                if armor_cfg is not None:
                    logger.warning(
                        "Comparison synthesis with Model Armor failed (%s); retrying without template.",
                        call_err,
                    )
                    armor_cfg = None
                    fallback_config = types.GenerateContentConfig(
                        system_instruction=narrative_sys_inst,
                        response_mime_type="application/json",
                        response_schema=self._NARRATIVE_SYNTHESIS_SCHEMA if is_mock_env else None,
                        temperature=float(getattr(settings, "temperature", 0.1)),
                        max_output_tokens=1024,
                        thinking_config=thinking_cfg,
                    )
                    response = self._call_genai_with_failover(
                        client,
                        call_model,
                        prompt,
                        fallback_config,
                    )
                else:
                    raise call_err

            usage = getattr(response, "usage_metadata", None)
            if usage:
                in_toks = int(getattr(usage, "prompt_token_count", 0) or 0)
                out_toks = int(getattr(usage, "candidates_token_count", 0) or 0)
                self.last_input_tokens += in_toks
                self.last_output_tokens += out_toks
                llm_span.set_attribute("gen_ai.usage.prompt_tokens", in_toks)
                llm_span.set_attribute("gen_ai.usage.completion_tokens", out_toks)

            blocked_reasons = {
                "MODEL_ARMOR",
                "SAFETY",
                "BLOCKLIST",
                "PROHIBITED_CONTENT",
                "SPII",
            }
            prompt_fb = getattr(response, "prompt_feedback", None)
            if prompt_fb is not None:
                fb_reason = str(getattr(prompt_fb, "block_reason", "") or "").upper()
                if any(flag in fb_reason for flag in blocked_reasons):
                    raise SecurityViolationError(
                        f"Stage 3 synthesis blocked by Model Armor / Safety filter ({fb_reason})"
                    )
            if getattr(response, "candidates", None):
                finish_reason = str(
                    getattr(response.candidates[0], "finish_reason", "") or ""
                ).upper()
                if any(flag in finish_reason for flag in blocked_reasons):
                    raise SecurityViolationError(
                        f"Stage 3 synthesis response blocked by Model Armor ({finish_reason})"
                    )

        if response.text:
            resp_ma_fut: Future[tuple[bool, str]] | None = None
            if armor_cfg is None or is_mock_env:
                resp_ma_fut = _SPECULATIVE_SYNTH_POOL.submit(
                    _check_model_armor_response_guard, response.text
                )

            clean_json = _clean_synthesis_json(response.text)
            try:
                synth = ComparisonSynthesis.model_validate_json(clean_json)
            except Exception as parse_err:
                if resp_ma_fut is not None:
                    resp_blocked, resp_reason = resp_ma_fut.result(timeout=8.0)
                    if resp_blocked:
                        raise SecurityViolationError(
                            f"Stage 3 synthesis output blocked by Model Armor response guard: {resp_reason}"
                        ) from parse_err
                logger.warning(
                    "Synthesis JSON validation failed on initial attempt (%s); retrying with max_output_tokens=2048.",
                    parse_err,
                )
                retry_cfg = types.GenerateContentConfig(
                    system_instruction=narrative_sys_inst,
                    response_mime_type="application/json",
                    response_schema=self._NARRATIVE_SYNTHESIS_SCHEMA if is_mock_env else None,
                    temperature=float(getattr(settings, "temperature", 0.1)),
                    max_output_tokens=2048,
                    thinking_config=thinking_cfg,
                )
                retry_resp = self._call_genai_with_failover(
                    client,
                    call_model,
                    prompt,
                    retry_cfg,
                )
                retry_usage = getattr(retry_resp, "usage_metadata", None)
                if retry_usage:
                    self.last_input_tokens += int(
                        getattr(retry_usage, "prompt_token_count", 0) or 0
                    )
                    self.last_output_tokens += int(
                        getattr(retry_usage, "candidates_token_count", 0) or 0
                    )
                synth = ComparisonSynthesis.model_validate_json(
                    _clean_synthesis_json(retry_resp.text or "")
                )

            merged_spec_winners: dict[str, str] = dict(synth.spec_winners or {})
            if matrix_fut is not None:
                try:
                    mw_winners, mw_in_toks, mw_out_toks = matrix_fut.result(timeout=8.0)
                    if not is_mock_env:
                        self.last_input_tokens += mw_in_toks
                        self.last_output_tokens += mw_out_toks
                    if mw_winners:
                        merged_spec_winners.update(mw_winners)
                except Exception as mw_wait_err:
                    logger.debug("Matrix winners parallel future wait failed: %s", mw_wait_err)

            if matrix is not None and (merged_spec_winners or not matrix):
                matrix[:] = self.build_comparison_matrix(
                    products, query=query, spec_winners=merged_spec_winners
                )
            summary_out = self.verify_and_align_claim_citations(synth.summary, products) or ""
            recs_out = self.verify_and_align_claim_citations(synth.recommendations, products)
            if len(products) > 2 and summary_out:
                for p in products:
                    if f"[SKU: {p.sku}]" not in summary_out and p.name not in summary_out:
                        summary_out = f"{summary_out.rstrip()}\n- {self._short_product_label(p)} [SKU: {p.sku}] is priced at ${p.price:,.2f}."
            if len(products) > 2 and recs_out:
                for p in products:
                    if f"[SKU: {p.sku}]" not in recs_out and p.name not in recs_out:
                        recs_out = f"{recs_out.rstrip()}; Best for Balanced Value: {self._short_product_label(p)} [SKU: {p.sku}] — priced at ${p.price:,.2f}"
            if resp_ma_fut is not None:
                resp_blocked, resp_reason = resp_ma_fut.result(timeout=8.0)
                if resp_blocked:
                    raise SecurityViolationError(
                        f"Stage 3 synthesis output blocked by Model Armor response guard: {resp_reason}"
                    )
            return _SynthesisResult(summary_out, recs_out, merged_spec_winners)
        raise RuntimeError("Empty response from Gemini synthesis LLM")

    def synthesize_summary(
        self,
        products: list[ProductSpec],
        matrix: list[MatrixRow],
        synthesis_model: str | None = None,
    ) -> str:
        """Create grounded synthesis narrative strictly citing SKUs."""
        res = self.synthesize_comparison_with_llm(products, matrix, query="", model=synthesis_model)
        summary, _ = _unpack_synthesis_result(res, self, products, "", matrix)
        return summary

    def generate_recommendations(
        self,
        products: list[ProductSpec],
        synthesis_model: str | None = None,
    ) -> str | None:
        """Formulate tailored recommendations grounded in the verified comparison matrix."""
        matrix: list[MatrixRow] = []
        res = self.synthesize_comparison_with_llm(products, matrix, query="", model=synthesis_model)
        _, recs = _unpack_synthesis_result(res, self, products, "", matrix)
        return recs

    def classify_intent_with_llm(
        self, query: str, model: str = settings.gemini_model
    ) -> QueryIntentAnalysis:
        """Use Gemini structured JSON output to semantically classify user query intent."""
        if not query or not query.strip():
            return QueryIntentAnalysis(
                intent_type="OPINION_OR_CHATTER",
                is_comparison_eligible=False,
                reasoning="Empty or blank query.",
            )

        sanitized_query = sanitize_user_prompt(query)
        is_mock_env = self.genai_client is not None or genai.Client is not _DEFAULT_GENAI_CLIENT_CLS
        call_model, _, _ = resolve_model_pair(model=model)
        armor_cfg = get_model_armor_config(
            mode="prompt_only",
            model=call_model,
            is_mock_env=is_mock_env,
        )

        # Fast-path explicit tagged product prompts from buildComparisonPrompt
        tagged = ComparisonOrchestrator.extract_tagged_products(query)
        is_tagged_fast_path = bool(
            len(tagged) >= 2
            or (tagged and re.search(r"\b(?:vs\.?|versus|compare|and)\b", query, re.IGNORECASE))
        )

        run_sync_ma = (
            is_tagged_fast_path
            or is_mock_env
            or self.bq_client is not None
            or _check_model_armor_prompt_guard is not _DEFAULT_MA_PROMPT_GUARD
        )
        if run_sync_ma:
            ma_blocked, ma_reason = _check_model_armor_prompt_guard(query)
            if ma_blocked:
                logger.warning(
                    "Stage 1 prompt blocked by Model Armor (%s): %s",
                    ma_reason,
                    sanitized_query,
                )
                return QueryIntentAnalysis(
                    intent_type="OPINION_OR_CHATTER",
                    is_comparison_eligible=False,
                    reasoning=f"Blocked by Model Armor: {ma_reason}"[:120],
                )

        if is_tagged_fast_path:
            names = [name for name, _sku in tagged if name] or [sku for _name, sku in tagged if sku]
            return QueryIntentAnalysis(
                intent_type="COMPARISON",
                is_comparison_eligible=True,
                detected_category=None,
                target_keywords=names,
                reasoning="Tagged products comparison request.",
            )

        stage1_tpl, _ = get_stage_prompt("stage1")
        prompt = format_stage1_intent_prompt(
            sanitized_query=sanitized_query,
            template=stage1_tpl,
        )

        ma_fut: Future[tuple[bool, str]] | None = None
        if not run_sync_ma and armor_cfg is None:
            ma_fut = _SPECULATIVE_SYNTH_POOL.submit(_check_model_armor_prompt_guard, query)

        client = self._get_genai_client(model=call_model)
        thinking_cfg = _build_thinking_config(call_model)
        intent_sys_inst = self.active_system_instruction if is_mock_env else None
        intent_max_tokens = (
            int(getattr(settings, "max_output_tokens", 2048)) if is_mock_env else 512
        )
        config = types.GenerateContentConfig(
            system_instruction=intent_sys_inst,
            response_mime_type="application/json",
            response_schema=QueryIntentAnalysis,
            model_armor_config=armor_cfg if armor_cfg is not None else None,
            temperature=float(getattr(settings, "temperature", 0.1)),
            max_output_tokens=intent_max_tokens,
            thinking_config=thinking_cfg,
        )

        with tracer.start_as_current_span("gemini.classify_intent") as llm_span:
            llm_span.set_attribute("gen_ai.system", "vertexai")
            llm_span.set_attribute("gen_ai.request.model", call_model)
            try:
                response = self._call_genai_with_failover(
                    client,
                    call_model,
                    prompt,
                    config,
                )
            except Exception as call_err:
                if armor_cfg is not None:
                    logger.warning(
                        "Intent classification with Model Armor failed (%s); retrying without template.",
                        call_err,
                    )
                    fallback_config = types.GenerateContentConfig(
                        system_instruction=intent_sys_inst,
                        response_mime_type="application/json",
                        response_schema=QueryIntentAnalysis,
                        temperature=float(getattr(settings, "temperature", 0.1)),
                        max_output_tokens=intent_max_tokens,
                        thinking_config=thinking_cfg,
                    )
                    response = self._call_genai_with_failover(
                        client,
                        call_model,
                        prompt,
                        fallback_config,
                    )
                else:
                    if ma_fut is not None:
                        ma_blocked, ma_reason = ma_fut.result(timeout=8.0)
                        if ma_blocked:
                            return QueryIntentAnalysis(
                                intent_type="OPINION_OR_CHATTER",
                                is_comparison_eligible=False,
                                reasoning=f"Blocked by Model Armor: {ma_reason}"[:120],
                            )
                    raise call_err

            if ma_fut is not None:
                ma_blocked, ma_reason = ma_fut.result(timeout=8.0)
                if ma_blocked:
                    logger.warning(
                        "Stage 1 prompt blocked by concurrent Model Armor (%s): %s",
                        ma_reason,
                        sanitized_query,
                    )
                    return QueryIntentAnalysis(
                        intent_type="OPINION_OR_CHATTER",
                        is_comparison_eligible=False,
                        reasoning=f"Blocked by Model Armor: {ma_reason}"[:120],
                    )

            usage = getattr(response, "usage_metadata", None)
            if usage:
                in_toks = int(getattr(usage, "prompt_token_count", 0) or 0)
                out_toks = int(getattr(usage, "candidates_token_count", 0) or 0)
                self.last_input_tokens += in_toks
                self.last_output_tokens += out_toks
                llm_span.set_attribute("gen_ai.usage.prompt_tokens", in_toks)
                llm_span.set_attribute("gen_ai.usage.completion_tokens", out_toks)

            if getattr(response, "candidates", None):
                finish_reason = str(getattr(response.candidates[0], "finish_reason", "") or "")
                if finish_reason in {
                    "SAFETY",
                    "MODEL_ARMOR",
                    "BLOCKLIST",
                    "PROHIBITED_CONTENT",
                    "SPII",
                }:
                    logger.warning(
                        "Intent classification query blocked by Model Armor / Safety filter (reason=%s): %s",
                        finish_reason,
                        sanitized_query,
                    )
                    return QueryIntentAnalysis(
                        intent_type="OPINION_OR_CHATTER",
                        is_comparison_eligible=False,
                        reasoning="Blocked by security filter.",
                    )

        def _parse_intent_payload(resp_obj: Any) -> QueryIntentAnalysis:
            text = ""
            try:
                text = (getattr(resp_obj, "text", "") or "").strip()
            except Exception:
                pass
            if not text and getattr(resp_obj, "candidates", None):
                for cand in resp_obj.candidates:
                    content = getattr(cand, "content", None)
                    if content and getattr(content, "parts", None):
                        for part in content.parts:
                            txt = getattr(part, "text", None)
                            if txt:
                                text += txt
            if not text:
                raise RuntimeError("Empty response from Gemini intent classification LLM")
            clean_json = _extract_json_snippet(text)
            return QueryIntentAnalysis.model_validate_json(clean_json)

        parsed_intent: QueryIntentAnalysis | None = None
        try:
            parsed_intent = _parse_intent_payload(response)
        except Exception as parse_err:
            logger.warning(
                "Intent classification JSON parsing failed on initial attempt (%s); retrying generate_content...",
                parse_err,
            )
            retry_response = self._call_genai_with_failover(
                client,
                call_model,
                prompt,
                config,
            )
            retry_usage = getattr(retry_response, "usage_metadata", None)
            if retry_usage:
                in_toks = int(getattr(retry_usage, "prompt_token_count", 0) or 0)
                out_toks = int(getattr(retry_usage, "candidates_token_count", 0) or 0)
                self.last_input_tokens += in_toks
                self.last_output_tokens += out_toks
            if getattr(retry_response, "candidates", None):
                finish_reason = str(
                    getattr(retry_response.candidates[0], "finish_reason", "") or ""
                )
                if finish_reason in {
                    "SAFETY",
                    "MODEL_ARMOR",
                    "BLOCKLIST",
                    "PROHIBITED_CONTENT",
                    "SPII",
                }:
                    logger.warning(
                        "Intent classification query blocked by Model Armor / Safety filter on retry (reason=%s): %s",
                        finish_reason,
                        sanitized_query,
                    )
                    return QueryIntentAnalysis(
                        intent_type="OPINION_OR_CHATTER",
                        is_comparison_eligible=False,
                        reasoning="Blocked by security filter.",
                    )
            parsed_intent = _parse_intent_payload(retry_response)

        # Filter out standalone spec attributes from target_keywords
        if parsed_intent.target_keywords:
            cleaned_kws: list[str] = []
            for kw in parsed_intent.target_keywords:
                raw_kw = kw.strip()
                if not raw_kw:
                    continue
                lower_kw = raw_kw.lower()
                if lower_kw in SPEC_ATTRIBUTES_BLOCKLIST:
                    continue
                cleaned_kws.append(raw_kw)
            parsed_intent.target_keywords = cleaned_kws

        # Normalize non-opinion comparative queries with >= 2 target_keywords to COMPARISON
        comparative_pattern = r"\b(?:vs\.?|versus|compare|comparison|between|difference)\b"
        is_comparative = bool(re.search(comparative_pattern, query, re.IGNORECASE))
        valid_kws = [kw for kw in (parsed_intent.target_keywords or []) if kw.strip()]
        if not self._is_opinion_query(query) and is_comparative and len(valid_kws) >= 2:
            parsed_intent.intent_type = "COMPARISON"
            parsed_intent.is_comparison_eligible = True

        return parsed_intent

    def classify_intent(
        self, query: str, model: str = settings.gemini_model
    ) -> QueryIntentAnalysis:
        """Classify user query intent using Gemini LLM."""
        return self.classify_intent_with_llm(query, model=model)

    @staticmethod
    def _is_opinion_query(query: str) -> bool:
        """Fast lexical helper to detect subjective opinions, complaints, or rants without duplicate LLM calls."""
        lower_q = (query or "").lower().strip()
        if not lower_q:
            return True
        opinion_words = (
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
        )
        comparative_tokens = (
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
        )
        is_opinion = any(re.search(r"\b" + re.escape(w) + r"\b", lower_q) for w in opinion_words)
        has_comparative = any(tok in f" {lower_q} " for tok in comparative_tokens)
        return is_opinion and not has_comparative

    def _balance_entities(
        self, candidates: list[ProductSpec], keywords: list[str]
    ) -> list[ProductSpec]:
        """Balance candidates across distinct brands when comparative query targets multiple brands."""
        if len(candidates) <= 1:
            return candidates

        first_brand = candidates[0].brand.strip().lower()
        kw_text = " ".join(keywords).lower()

        alt_candidate = next(
            (
                p
                for p in candidates[1:]
                if p.brand.strip().lower() != first_brand
                and (
                    p.brand.strip().lower() in kw_text
                    or any(len(tok) >= 2 and tok in kw_text for tok in p.name.lower().split()[:2])
                    or any(
                        len(kw.strip()) >= 2 and tok.startswith(kw.strip().lower())
                        for tok in re.findall(r"[a-z0-9]+", p.name.lower())[:2]
                        for kw in keywords
                    )
                )
            ),
            None,
        )
        if alt_candidate is not None:
            remaining = [p for p in candidates[1:] if p.sku != alt_candidate.sku]
            return [candidates[0], alt_candidate] + remaining

        return candidates

    def _select_best_entity_candidates(
        self,
        candidates: list[ProductSpec],
        keywords: list[str],
        target_count: int,
    ) -> list[ProductSpec]:
        """Select the highest-matching candidate for each keyword entity phrase."""
        if len(candidates) <= target_count or not keywords:
            return self._balance_entities(candidates, keywords)[:target_count]

        selected: list[ProductSpec] = []
        used_skus: set[str] = set()

        for kw in keywords[:target_count]:
            kw_low = kw.strip().lower()
            kw_tokens = [
                t
                for t in re.findall(r"[a-z0-9]+", kw_low)
                if len(t) >= 2 and t not in ("the", "and", "for", "with", "pro")
            ]
            if "pro" in re.findall(r"[a-z0-9]+", kw_low):
                kw_tokens.append("pro")
            best_p: ProductSpec | None = None
            best_score = -1
            for p in candidates:
                if p.sku in used_skus:
                    continue
                hay = f"{p.brand} {p.name}".lower()
                hay_tokens = set(re.findall(r"[a-z0-9]+", hay))
                score = 0
                if kw_low and kw_low in hay:
                    score += 10
                for tok in kw_tokens:
                    if tok in hay_tokens:
                        score += 4
                    elif tok in hay:
                        score += 2
                if score > best_score and score > 0:
                    best_score = score
                    best_p = p
            if best_p is not None:
                selected.append(best_p)
                used_skus.add(best_p.sku)

        for p in self._balance_entities(candidates, keywords):
            if len(selected) >= target_count:
                break
            if p.sku not in used_skus:
                selected.append(p)
                used_skus.add(p.sku)

        return selected[:target_count]

    def compare(
        self,
        query: str | ComparisonRequest,
        category: str | None = None,
        session_id: str | None = None,
        agent_version: str | None = None,
        model: str | None = None,
        synthesis_model: str | None = None,
        user_id: str | None = None,
    ) -> CompareResponse:
        """Execute full end-to-end grounded comparison pipeline with OpenTelemetry tracing."""
        if isinstance(query, ComparisonRequest):
            req_obj = query
            query = req_obj.query
            category = category if category is not None else req_obj.category
            session_id = session_id if session_id is not None else req_obj.session_id
            agent_version = agent_version if agent_version is not None else req_obj.agent_version
            model = model if model is not None else req_obj.model
            synthesis_model = (
                synthesis_model if synthesis_model is not None else req_obj.synthesis_model
            )
            user_id = user_id if user_id is not None else req_obj.user_id

        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self._active_category_hint = category

        resolved_agent_ver = agent_version or settings.agent_version
        version_spec = default_registry.get_version(resolved_agent_ver)
        is_flash = "flash" in resolved_agent_ver.lower()
        target_prompt_ver = (
            version_spec.prompt_version
            if version_spec
            else ("2026.03-v2" if is_flash else settings.prompt_version)
        )
        prompt_text, resolved_prompt_ver = get_active_prompt(version_id=target_prompt_ver)
        self.active_system_instruction = (
            version_spec.system_instruction if version_spec else prompt_text
        )

        base_model = (
            "gemini-2.5-flash" if is_flash else (self._injected_model or settings.gemini_model)
        )
        base_synthesis = self._injected_synthesis_model or self.synthesis_model or base_model

        raw_model = model or base_model
        raw_synthesis = synthesis_model or base_synthesis

        active_routing_model, active_synthesis_model, is_hybrid = resolve_model_pair(
            model=raw_model,
            synthesis_model=raw_synthesis,
            default_model=settings.gemini_model,
        )

        if (raw_model and raw_model.lower() == "tiered-hybrid") or is_hybrid:
            effective_model_version = (
                f"tiered-hybrid({active_routing_model}+{active_synthesis_model})@001"
            )
        elif model or self._injected_model:
            effective_model_version = f"{active_routing_model}@001"
        else:
            effective_model_version = "gemini-2.5-flash@001" if is_flash else settings.model_version

        safe_query = sanitize_user_prompt(query)
        tracer = get_tracer("app.agent")

        with tracer.start_as_current_span("catalog_comparison.orchestrate") as span:
            span.set_attribute("query", safe_query)
            span.set_attribute("category", category or "")
            if session_id:
                span.set_attribute("session_id", session_id)
            if user_id:
                span.set_attribute("user_id", user_id)
            span.set_attribute("ai.agent.version", resolved_agent_ver)
            span.set_attribute("ai.model.name", active_routing_model)
            span.set_attribute("ai.synthesis_model.name", active_synthesis_model)
            span.set_attribute("ai.model.tiered_hybrid", is_hybrid)
            span.set_attribute("ai.model.version", effective_model_version)
            span.set_attribute("ai.prompt.version", resolved_prompt_ver)

            trace_id = get_current_trace_id()
            tagged_pairs = self.extract_tagged_products(query)
            early_tagged_skus = [sku for _, sku in tagged_pairs if sku]
            if not early_tagged_skus:
                early_tagged_skus = re.findall(r"\[SKU:\s*([A-Za-z0-9_-]+)\]", safe_query or "")

            prelim_bq_keywords: list[str]
            prelim_bq_category: str | None = category
            if len(early_tagged_skus) >= 2:
                prelim_bq_keywords = list(early_tagged_skus)
                prelim_bq_category = None
            elif tagged_pairs:
                prelim_bq_keywords = [kw for pair in tagged_pairs for kw in pair if kw]
            else:
                prelim_bq_keywords = self.extract_keywords(query)

            should_prelaunch_bq = bool(early_tagged_skus) or (
                "[BLOCKED_INJECTION]" not in (safe_query or "")
                and not self._is_opinion_query(query)
            )
            stage2_future: Future[list[dict[str, Any]]] | None = None
            if should_prelaunch_bq:
                stage2_future = _SPECULATIVE_SYNTH_POOL.submit(
                    query_catalog,
                    keywords=prelim_bq_keywords,
                    category=prelim_bq_category,
                    client=self.bq_client,
                )

            # Stage 1 (in parallel with Stage 2 at t=0): Query Intent Extraction & Security Sanitization
            with tracer.start_as_current_span("agent.stage_1.query_intent") as intent_span:
                intent_span.set_attribute("agent.model", active_routing_model)
                intent = self.classify_intent(query, model=active_routing_model)
                intent_span.set_attribute("agent.detected_intent", intent.intent_type)
                intent_span.set_attribute(
                    "agent.is_comparison_eligible", intent.is_comparison_eligible
                )
                llm_keywords = [
                    kw.strip() for kw in (intent.target_keywords or []) if kw and kw.strip()
                ]
                keywords = llm_keywords
                intent_span.set_attribute("agent.keywords", str(keywords))
                logger.info("Parsed keywords %s from query: %s", keywords, safe_query)

            intent_reasoning = intent.reasoning or ""
            if intent_reasoning.startswith("Blocked by Model Armor:"):
                if stage2_future is not None:
                    stage2_future.cancel()
                ma_reason = (
                    intent_reasoning.split("Blocked by Model Armor:", 1)[1].strip()
                    or "The prompt violated Model Armor security filters."
                )
                span.set_attribute("ai.safety.blocked", True)
                span.set_attribute("ai.safety.block_reason", "MODEL_ARMOR")
                tmpl_id = settings.model_armor_prompt_template.split("/")[-1]
                refusal_msg = (
                    f"[Model Armor Security Guardrail Activated — Template: {tmpl_id}]\n"
                    f"Request blocked by Google Cloud Model Armor (verdict: MODEL_ARMOR). {ma_reason} "
                    "No catalog tools or database queries were executed."
                )
                return CompareResponse(
                    summary=refusal_msg,
                    products=[],
                    comparison_matrix=[],
                    citations=[],
                    recommendations="Please submit a valid consumer electronics comparison query.",
                    session_id=session_id,
                    trace_id=trace_id,
                    agent_version=resolved_agent_ver,
                    model_version=effective_model_version,
                    synthesis_model=active_synthesis_model,
                    prompt_version=resolved_prompt_ver,
                    status="refused",
                    blocked_by_model_armor=True,
                )

            # Early Gate: If Stage 1 marks query as opinion/chatter or marks a tagged query ineligible,
            # discard parallel Stage 2 BQ results immediately!
            if intent.intent_type == "OPINION_OR_CHATTER" or (
                len(early_tagged_skus) >= 2 and not intent.is_comparison_eligible
            ):
                if stage2_future is not None:
                    stage2_future.cancel()
                span.set_attribute("comparison_matrix_suppressed", True)
                summary = (
                    f"No product comparison matrix was generated for '{safe_query}'. "
                    "The query appears to be an opinion or general comment rather than a product comparison request. "
                    "To compare products side-by-side, please specify two or more models or brands "
                    "(e.g., 'Compare Model A and Model B')."
                )
                return CompareResponse(
                    summary=summary,
                    products=[],
                    comparison_matrix=[],
                    citations=[],
                    recommendations="Specify two or more devices or models to view a detailed comparison matrix.",
                    session_id=session_id,
                    trace_id=trace_id,
                    agent_version=resolved_agent_ver,
                    model_version=effective_model_version,
                    synthesis_model=active_synthesis_model,
                    prompt_version=resolved_prompt_ver,
                )

            # Stage 2: Grounded Catalog Retrieval from BigQuery (resolved from t=0 parallel future)
            with tracer.start_as_current_span("agent.stage_2.catalog_retrieval") as bq_stage_span:
                effective_bq_keywords = (
                    early_tagged_skus
                    if len(early_tagged_skus) >= 2
                    else (keywords or prelim_bq_keywords)
                )
                effective_bq_category = None if len(early_tagged_skus) >= 2 else category
                bq_stage_span.set_attribute("agent.search_keywords", str(effective_bq_keywords))
                bq_stage_span.set_attribute("agent.category_filter", effective_bq_category or "")
                try:
                    if stage2_future is not None:
                        catalog_rows = stage2_future.result()
                        if (
                            not catalog_rows
                            and len(early_tagged_skus) < 2
                            and keywords
                            and keywords != prelim_bq_keywords
                        ):
                            catalog_rows = query_catalog(
                                keywords=keywords,
                                category=effective_bq_category,
                                client=self.bq_client,
                            )
                    else:
                        catalog_rows = query_catalog(
                            keywords=effective_bq_keywords,
                            category=effective_bq_category,
                            client=self.bq_client,
                        )
                except Exception as err:
                    logger.warning("BigQuery catalog query encountered an error: %s", err)
                    catalog_rows = []
                bq_stage_span.set_attribute("agent.raw_products_retrieved", len(catalog_rows))

            if not catalog_rows:
                span.set_attribute("product_count", 0)
                span.set_attribute("target_skus", "")
                return CompareResponse(
                    summary=f"No matching products found in the catalog for query: '{safe_query}'. Please check your search terms.",
                    products=[],
                    comparison_matrix=[],
                    citations=[],
                    recommendations="Try searching for broader model names, brands, or specify a valid product category.",
                    session_id=session_id,
                    trace_id=trace_id,
                    agent_version=resolved_agent_ver,
                    model_version=effective_model_version,
                    synthesis_model=active_synthesis_model,
                    prompt_version=resolved_prompt_ver,
                )

            # Convert retrieved catalog rows into ProductSpec schemas with deduplication and preserve tagged SKU click order
            products = [ProductSpec(**row) for row in catalog_rows]
            seen_skus: set[str] = set()
            unique_products: list[ProductSpec] = []
            for p in products:
                if p.sku and p.sku not in seen_skus:
                    seen_skus.add(p.sku)
                    unique_products.append(p)

            tagged_pairs = self.extract_tagged_products(query or "")
            tagged_skus = [sku for _, sku in tagged_pairs if sku]
            if not tagged_skus:
                tagged_skus = re.findall(r"\[SKU:\s*([A-Za-z0-9_-]+)\]", query or "")
            if tagged_skus:
                sku_to_prod = {p.sku: p for p in unique_products}
                matched_tagged = [sku_to_prod[s] for s in tagged_skus if s in sku_to_prod]
                if len(matched_tagged) >= 2:
                    products = matched_tagged[:5]
                elif len(matched_tagged) == 1 and len(unique_products) > 1:
                    remaining = [p for p in unique_products if p.sku not in tagged_skus]
                    products = [matched_tagged[0], remaining[0]]
            elif keywords and len(keywords) >= 2:
                target_count = min(len(keywords), 5)
                entity_matches = self._select_best_entity_candidates(
                    unique_products, keywords, target_count
                )
                products = (
                    entity_matches if len(entity_matches) >= 2 else unique_products[:target_count]
                )
            else:
                products = unique_products[:5]

            target_skus = [p.sku for p in products]
            span.set_attribute("product_count", len(products))
            span.set_attribute("target_skus", ",".join(target_skus))

            # Gate: If query is not comparison-eligible, is an opinion/rant, or fewer than 2 relevant products exist, suppress comparison matrix!
            if (
                len(products) < 2
                or not intent.is_comparison_eligible
                or intent.intent_type == "OPINION_OR_CHATTER"
            ):
                span.set_attribute("comparison_matrix_suppressed", True)
                if intent.intent_type == "OPINION_OR_CHATTER" or len(products) == 0:
                    summary = (
                        f"No product comparison matrix was generated for '{safe_query}'. "
                        "The query appears to be an opinion or general comment rather than a product comparison request. "
                        "To compare products side-by-side, please specify two or more models or brands "
                        "(e.g., 'Compare Model A and Model B')."
                    )
                    recommendations = "Specify two or more devices or models to view a detailed comparison matrix."
                    products = []
                    matrix = []
                    citations = []
                else:
                    p = products[0]
                    synth_res = self.synthesize_comparison_with_llm(
                        products, [], query=query, model=active_synthesis_model
                    )
                    summary, _ = _unpack_synthesis_result(synth_res, self, products, query, [])
                    recommendations = None
                    matrix = []
                    citations = [
                        Citation(
                            sku=p.sku, url=p.url or f"https://www.techbuy.com/site/sku/{p.sku}.p"
                        )
                    ]

                return CompareResponse(
                    summary=summary,
                    products=products,
                    comparison_matrix=matrix,
                    citations=citations,
                    recommendations=recommendations,
                    session_id=session_id,
                    trace_id=trace_id,
                    agent_version=resolved_agent_ver,
                    model_version=effective_model_version,
                    synthesis_model=active_synthesis_model,
                    prompt_version=resolved_prompt_ver,
                    input_tokens=self.last_input_tokens if self.last_input_tokens > 0 else None,
                    output_tokens=self.last_output_tokens if self.last_output_tokens > 0 else None,
                )

            # Extract strict citations
            citations = [
                Citation(sku=p.sku, url=p.url or f"https://www.techbuy.com/site/sku/{p.sku}.p")
                for p in products
            ]

            # Stage 4: Matrix Building & Spec Synthesis
            with tracer.start_as_current_span("agent.stage_4.spec_synthesis") as synth_stage_span:
                synth_stage_span.set_attribute("ai.synthesis_model.name", active_synthesis_model)
                matrix: list[MatrixRow] = []

                with tracer.start_as_current_span("gemini.synthesize_summary") as synth_span:
                    synth_span.set_attribute("ai.synthesis_model.name", active_synthesis_model)
                    try:
                        synth_res = self.synthesize_comparison_with_llm(
                            products, matrix, query=query, model=active_synthesis_model
                        )
                        with tracer.start_as_current_span("build_comparison_matrix"):
                            summary, recommendations = _unpack_synthesis_result(
                                synth_res, self, products, query, matrix
                            )
                    except SecurityViolationError as sec_err:
                        span.set_attribute("ai.safety.blocked", True)
                        span.set_attribute("ai.safety.block_reason", "MODEL_ARMOR_RESPONSE")
                        tmpl_id = settings.model_armor_response_template.split("/")[-1]
                        refusal_msg = (
                            f"[Model Armor Security Guardrail Activated — Template: {tmpl_id}]\n"
                            f"Response blocked by Google Cloud Model Armor (verdict: MODEL_ARMOR_RESPONSE). {sec_err}"
                        )
                        return CompareResponse(
                            summary=refusal_msg,
                            products=[],
                            comparison_matrix=[],
                            citations=[],
                            recommendations="Please submit a valid consumer electronics comparison query.",
                            session_id=session_id,
                            trace_id=trace_id,
                            agent_version=resolved_agent_ver,
                            model_version=effective_model_version,
                            synthesis_model=active_synthesis_model,
                            prompt_version=resolved_prompt_ver,
                            status="refused",
                            blocked_by_model_armor=True,
                        )
                synth_stage_span.set_attribute("agent.matrix_rows_count", len(matrix))

            return CompareResponse(
                summary=summary,
                products=products,
                comparison_matrix=matrix,
                citations=citations,
                recommendations=recommendations,
                session_id=session_id,
                trace_id=trace_id,
                agent_version=resolved_agent_ver,
                model_version=effective_model_version,
                synthesis_model=active_synthesis_model,
                prompt_version=resolved_prompt_ver,
                input_tokens=self.last_input_tokens if self.last_input_tokens > 0 else None,
                output_tokens=self.last_output_tokens if self.last_output_tokens > 0 else None,
            )

    def _invoke_specialist_via_adk_runner(
        self,
        agent_name: str,
        instruction: str,
        prompt: str,
        model: str | None = None,
        tools: list[Any] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[str, list[Any]]:
        """Invoke a specialist ADK Agent via run_adk_agent_sync."""
        from app.agent.runner import run_adk_agent_sync

        effective_model = model or self.synthesis_model
        adk_llm = CatalogAdkLlm(
            model=effective_model,
            genai_client=self.genai_client,
        )
        bound_agent = Agent(
            name=agent_name,
            model=adk_llm,
            instruction=instruction,
            tools=tools or [],
        )
        final_text, events = run_adk_agent_sync(
            agent=bound_agent,
            prompt=prompt,
            session_id=session_id,
            user_id=user_id or "default_user",
        )
        self.last_input_tokens += adk_llm.last_input_tokens
        self.last_output_tokens += adk_llm.last_output_tokens
        return final_text, events

    def execute_with_adk_runner(
        self,
        query: str,
        category: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> CompareResponse:
        """Execute comparison integrated with Google ADK Runner and VertexAiSessionService."""
        effective_user_id = user_id or "default_user"
        target_session = session_id or f"sess_{int(time.time() * 1000)}"
        safe_query = sanitize_user_prompt(query)

        intent = self.classify_intent(query, model=self.model)
        if intent.intent_type == "OPINION_OR_CHATTER":
            summary = (
                f"No product comparison matrix was generated for '{safe_query}'. "
                "The query appears to be an opinion or general comment rather than a product comparison request. "
                "To compare products side-by-side, please specify two or more models or brands "
                "(e.g., 'Compare Model A and Model B')."
            )
            return CompareResponse(
                summary=summary,
                products=[],
                comparison_matrix=[],
                citations=[],
                recommendations="Specify two or more devices or models to view a detailed comparison matrix.",
                session_id=target_session,
                trace_id=get_current_trace_id(),
                agent_version=settings.agent_version,
                model_version=f"{self.synthesis_model}@001",
                synthesis_model=self.synthesis_model,
                prompt_version=settings.prompt_version,
            )

        extracted_keywords = list(intent.target_keywords or [])
        effective_category = category if category is not None else intent.detected_category

        def query_catalog(
            keywords: list[str] | None = None,
            category: str | None = None,
        ) -> list[dict[str, Any]]:
            """Retrieve grounded product records from BigQuery catalog via ADK tool execution."""
            import app.agent.orchestrator as _orch_mod

            return _orch_mod.query_catalog(
                keywords=extracted_keywords or keywords or [query],
                category=effective_category if effective_category is not None else category,
                client=self.bq_client,
            )

        try:
            _final_text, events = self._invoke_specialist_via_adk_runner(
                agent_name="catalog_comparison_orchestrator",
                instruction=self.active_system_instruction,
                prompt=query,
                model=self.synthesis_model,
                tools=[query_catalog],
                session_id=session_id,
                user_id=effective_user_id,
            )

            # Parse tool results from ADK FunctionResponse events
            retrieved_prods: list[ProductSpec] = []
            seen_skus: set[str] = set()
            for evt in events:
                if evt.content:
                    for p in evt.content.parts:
                        if hasattr(p, "function_response") and p.function_response:
                            resp = p.function_response.response
                            r_items = (
                                resp.get("result")
                                if isinstance(resp, dict) and "result" in resp
                                else (resp if isinstance(resp, list) else [])
                            )
                            if isinstance(r_items, list):
                                for itm in r_items:
                                    if isinstance(itm, dict) and "sku" in itm:
                                        sku_val = str(itm["sku"])
                                        if sku_val not in seen_skus:
                                            seen_skus.add(sku_val)
                                            retrieved_prods.append(ProductSpec(**itm))

            if not retrieved_prods:
                catalog_rows = query_catalog(
                    keywords=extracted_keywords or [query],
                    category=effective_category,
                )
                retrieved_prods = [ProductSpec(**row) for row in catalog_rows]

            if retrieved_prods:
                seen_skus: set[str] = set()
                unique_products: list[ProductSpec] = []
                for p in retrieved_prods:
                    if p.sku and p.sku not in seen_skus:
                        seen_skus.add(p.sku)
                        unique_products.append(p)

                tagged_pairs = self.extract_tagged_products(query or "")
                tagged_skus = [sku for _, sku in tagged_pairs if sku]
                if not tagged_skus:
                    tagged_skus = re.findall(r"\[SKU:\s*([A-Za-z0-9_-]+)\]", query or "")
                if tagged_skus:
                    sku_to_prod = {p.sku: p for p in unique_products}
                    matched_tagged = [sku_to_prod[s] for s in tagged_skus if s in sku_to_prod]
                    if len(matched_tagged) >= 2:
                        products = matched_tagged[:5]
                    elif len(matched_tagged) == 1 and len(unique_products) > 1:
                        remaining = [p for p in unique_products if p.sku not in tagged_skus]
                        products = [matched_tagged[0], remaining[0]]
                elif extracted_keywords and len(extracted_keywords) >= 2:
                    target_count = min(len(extracted_keywords), 5)
                    entity_matches = self._select_best_entity_candidates(
                        unique_products, extracted_keywords, target_count
                    )
                    products = (
                        entity_matches
                        if len(entity_matches) >= 2
                        else unique_products[:target_count]
                    )
                else:
                    products = unique_products[:5]

                if len(products) >= 2 and intent.is_comparison_eligible:
                    spec_winners_map: dict[str, str] | None = None
                    summary = None
                    recommendations = None
                    if _final_text and _final_text.strip():
                        try:
                            clean_text = _final_text.strip()
                            if clean_text.startswith("```"):
                                clean_text = re.sub(r"^```(?:json)?\n?", "", clean_text)
                                clean_text = re.sub(r"\n?```$", "", clean_text).strip()
                            data = json.loads(clean_text)
                            if isinstance(data, dict):
                                summary = data.get("summary")
                                recommendations = data.get("recommendations")
                                raw_sw = data.get("spec_winners")
                                if isinstance(raw_sw, dict):
                                    spec_winners_map = {
                                        str(k): str(v) for k, v in raw_sw.items() if k and v
                                    }
                        except Exception:
                            if len(_final_text.strip()) > 10:
                                summary = _final_text.strip()

                    matrix = self.build_comparison_matrix(
                        products, query=query, spec_winners=spec_winners_map
                    )
                    if not summary:
                        synth_res = self.synthesize_comparison_with_llm(
                            products,
                            matrix,
                            query=query,
                            model=self.synthesis_model,
                        )
                        summary, recommendations = _unpack_synthesis_result(
                            synth_res, self, products, query, matrix
                        )
                    else:
                        summary = self.verify_and_align_claim_citations(summary, products)
                        if recommendations:
                            recommendations = self.verify_and_align_claim_citations(
                                recommendations, products
                            )
                    citations = [
                        Citation(
                            sku=p.sku,
                            url=p.url or f"https://www.techbuy.com/site/sku/{p.sku}.p",
                        )
                        for p in products
                    ]
                    return CompareResponse(
                        summary=summary,
                        products=products,
                        comparison_matrix=matrix,
                        citations=citations,
                        recommendations=recommendations,
                        session_id=target_session,
                        trace_id=get_current_trace_id(),
                        agent_version=settings.agent_version,
                        model_version=f"{self.synthesis_model}@001",
                        synthesis_model=self.synthesis_model,
                        prompt_version=settings.prompt_version,
                        input_tokens=self.last_input_tokens if self.last_input_tokens > 0 else None,
                        output_tokens=self.last_output_tokens
                        if self.last_output_tokens > 0
                        else None,
                    )
        except Exception as adk_err:
            logger.warning(
                "ADK runner execution failed; falling back to direct compare: %s", adk_err
            )

        return self.compare(
            query=query,
            category=category,
            session_id=target_session,
        )

    def chat_with_products(
        self,
        message: str,
        products: list[ProductSpec],
        conversation_history: list[ChatMessage] | None = None,
        comparison_matrix: list[MatrixRow] | None = None,
        session_id: str | None = None,
        model: str | None = None,
        synthesis_model: str | None = None,
        agent_version: str | None = None,
        user_id: str | None = None,
    ) -> ChatResponse:
        """Answer conversational follow-up questions grounded strictly in compared ProductSpecs and matrix."""
        start_time = time.perf_counter()
        clean_message = sanitize_user_prompt(message)
        active_model = synthesis_model or model or self.synthesis_model
        resolved_agent_version = agent_version or settings.agent_version
        resolved_user_id = user_id or "default_user"

        # Preload cross-session memories for authenticated user
        recalled_memories: list[str] = []
        try:
            from app.agent.runner import get_default_memory_service

            memory_service = get_default_memory_service()
            if memory_service is not None and hasattr(memory_service, "search_memory"):

                async def _search() -> Any:
                    return await memory_service.search_memory(
                        app_name="app",
                        user_id=resolved_user_id,
                        query=clean_message or message,
                    )

                raw_memories = _run_async_safely(_search)
                entries = getattr(raw_memories, "memories", raw_memories)
                if isinstance(entries, list):
                    for entry in entries:
                        content = getattr(entry, "content", None)
                        if content and hasattr(content, "parts") and content.parts:
                            for part in content.parts:
                                t = getattr(part, "text", None)
                                if t and isinstance(t, str) and t.strip():
                                    recalled_memories.append(t.strip())
                        elif hasattr(entry, "text") and entry.text:
                            recalled_memories.append(str(entry.text).strip())
                        elif isinstance(entry, str) and entry.strip():
                            recalled_memories.append(entry.strip())
        except Exception as mem_err:
            logger.debug("Cross-session memory search note: %s", mem_err)

        # Build citations for compared products
        citations = [
            Citation(
                sku=p.sku,
                url=p.url or f"https://www.techbuy.com/site/sku/{p.sku}.p",
                description=f"{p.name} (${p.price:,.2f})",
            )
            for p in products
        ]

        def _make_refusal(detail_msg: str, verdict: str = "MODEL_ARMOR") -> ChatResponse:
            clean_detail = (
                detail_msg.strip()
                if detail_msg
                else "The request violated safety or security guardrails."
            )
            tmpl_id = (
                settings.model_armor_response_template.split("/")[-1]
                if "RESPONSE" in verdict
                else settings.model_armor_prompt_template.split("/")[-1]
            )
            refusal_text = (
                f"[Model Armor Security Guardrail Activated — Template: {tmpl_id}]\n"
                f"Request blocked by Google Cloud Model Armor (verdict: {verdict}). {clean_detail} "
                "No catalog tools or database queries were executed. Please submit a valid consumer electronics comparison query."
            )
            return ChatResponse(
                reply=refusal_text,
                citations=citations,
                suggested_followups=[
                    "Which laptops have the best battery life?",
                    "Compare lightweight tablets under $500",
                ],
                latency_ms=round((time.perf_counter() - start_time) * 1000.0, 2),
                session_id=session_id,
                trace_id=get_current_trace_id(),
                agent_version=resolved_agent_version,
                model_version=f"{active_model}@001",
            )

        # (2) Run _check_model_armor_prompt_guard on message and user history turns
        def _run_ma_guard() -> tuple[bool, str]:
            b_main, r_main = _check_model_armor_prompt_guard(clean_message or message)
            if b_main:
                return True, r_main or "The prompt violated Model Armor security filters."
            if conversation_history:
                for msg in conversation_history:
                    if msg.role.lower() in ("user", "customer"):
                        b_hist, r_hist = _check_model_armor_prompt_guard(msg.content)
                        if b_hist:
                            return (
                                True,
                                r_hist or "The prompt violated Model Armor security filters.",
                            )
            return False, ""

        call_model = active_model
        client = self._get_genai_client(model=call_model)
        is_mock_chat_env = (
            self.genai_client is not None or genai.Client is not _DEFAULT_GENAI_CLIENT_CLS
        )
        armor_cfg = get_model_armor_config(
            mode="both", model=call_model, is_mock_env=is_mock_chat_env
        )
        is_ma_blocked, ma_block_detail = _run_ma_guard()
        if is_ma_blocked:
            return _make_refusal(ma_block_detail)

        # Context lines for products
        product_blocks: list[str] = []
        for p in products:
            specs_str = ", ".join(f"{k}: {v}" for k, v in (p.specifications or {}).items())
            product_blocks.append(
                f"- Product: {p.name} [SKU: {p.sku}], Brand: {p.brand}, Price: ${p.price:,.2f}\n"
                f"  Specs: {specs_str}"
            )

        matrix_lines: list[str] = []
        for row in comparison_matrix or []:
            vals = ", ".join(f"[SKU: {sku}]={val}" for sku, val in row.values.items())
            matrix_lines.append(
                f"- Feature '{row.feature}': {vals} (Winner: {row.winner_sku or 'Tie/None'})"
            )

        # (1) Sanitize all conversation_history message contents with sanitize_user_prompt
        history_lines: list[str] = []
        for msg in conversation_history or []:
            sanitized_content = sanitize_user_prompt(msg.content or "")
            history_lines.append(f"{msg.role.upper()}: {sanitized_content}")

        reply_text = ""
        suggested: list[str] = []

        memory_section = ""
        if recalled_memories:
            memory_lines = "\n".join(f"- {mem}" for mem in recalled_memories)
            memory_section = (
                f"<recalled_user_memories>\n{memory_lines}</recalled_user_memories>\n\n"
            )

        matrix_section = (
            "<comparison_matrix>\n" + "\n".join(matrix_lines) + "\n</comparison_matrix>\n\n"
            if matrix_lines
            else ""
        )
        history_section = (
            "<conversation_history>\n" + "\n".join(history_lines) + "\n</conversation_history>\n\n"
            if history_lines
            else ""
        )
        chat_tpl, _ = get_stage_prompt("chat")
        prompt = format_followup_chat_prompt(
            memory_section=memory_section,
            products_block="\n".join(product_blocks),
            matrix_section=matrix_section,
            history_section=history_section,
            clean_message=clean_message,
            template=chat_tpl,
        )

        # (3) Attach model_armor_config=get_model_armor_config(mode="both") to types.GenerateContentConfig
        config = types.GenerateContentConfig(
            system_instruction="You are a helpful electronics comparison assistant. Output valid JSON only.",
            response_mime_type="application/json",
            temperature=0.2,
            max_output_tokens=500,
            model_armor_config=armor_cfg,
            thinking_config=_build_thinking_config(call_model),
        )
        with tracer.start_as_current_span("gemini.chat_followup") as chat_span:
            chat_span.set_attribute("gen_ai.system", "vertexai")
            chat_span.set_attribute("gen_ai.request.model", call_model)
            resp = None
            try:
                resp = self._call_genai_with_failover(
                    client,
                    call_model,
                    prompt,
                    config,
                )
            except Exception as call_err:
                err_msg = str(call_err).lower()
                if armor_cfg is not None and (
                    "model_armor" in err_msg
                    or "template" in err_msg
                    or "not found" in err_msg
                    or "400" in err_msg
                ):
                    logger.warning(
                        "Model Armor template lookup failed in region (%s); retrying without template.",
                        call_err,
                    )
                    armor_cfg = None
                    ma_blocked, ma_reason = _check_model_armor_prompt_guard(
                        clean_message or message
                    )
                    if ma_blocked:
                        return _make_refusal(
                            ma_reason or "The prompt violated Model Armor security filters."
                        )
                    fallback_config = types.GenerateContentConfig(
                        system_instruction="You are a helpful electronics comparison assistant. Output valid JSON only.",
                        response_mime_type="application/json",
                        temperature=0.2,
                        max_output_tokens=500,
                        thinking_config=_build_thinking_config(call_model),
                    )
                    try:
                        resp = self._call_genai_with_failover(
                            client,
                            call_model,
                            prompt,
                            fallback_config,
                        )
                    except Exception as retry_err:
                        logger.error("Fallback chat generation failed: %s", retry_err)
                        raise RuntimeError(
                            f"Live chat generation failed after Model Armor fallback: {retry_err}"
                        ) from retry_err
                else:
                    logger.error("Live chat generation failed: %s", call_err)
                    raise RuntimeError(f"Live chat generation failed: {call_err}") from call_err

            # (4) Inspect resp.prompt_feedback.block_reason and resp.candidates[0].finish_reason
            blocked_reasons = {
                "MODEL_ARMOR",
                "SAFETY",
                "BLOCKLIST",
                "PROHIBITED_CONTENT",
                "SPII",
            }
            is_resp_blocked = False
            resp_block_detail = ""
            resp_verdict = "MODEL_ARMOR"

            if resp is not None:
                prompt_feedback = getattr(resp, "prompt_feedback", None)
                if prompt_feedback is not None:
                    fb_reason = str(getattr(prompt_feedback, "block_reason", "") or "")
                    if fb_reason in blocked_reasons:
                        is_resp_blocked = True
                        resp_verdict = fb_reason
                        fb_msg = getattr(prompt_feedback, "block_reason_message", "")
                        resp_block_detail = (
                            f"Blocked by {fb_reason}: {fb_msg}"
                            if fb_msg
                            else f"Blocked by {fb_reason}."
                        )

                if not is_resp_blocked and getattr(resp, "candidates", None):
                    cand = resp.candidates[0]
                    finish_reason = str(getattr(cand, "finish_reason", "") or "")
                    if finish_reason in blocked_reasons:
                        is_resp_blocked = True
                        resp_verdict = finish_reason
                        resp_block_detail = f"Blocked by {finish_reason}."

            if is_resp_blocked:
                logger.warning(
                    "Chat generation blocked by Model Armor / Safety filter: %s",
                    resp_block_detail,
                )
                return _make_refusal(resp_block_detail, verdict=resp_verdict)

            if resp is not None and getattr(resp, "text", None):
                try:
                    parsed = json.loads(resp.text)
                    reply_text = parsed.get("reply", "")
                    suggested = parsed.get("suggested_followups", [])
                except Exception:
                    reply_text = resp.text

            if not reply_text:
                raise RuntimeError("Empty response from Gemini chat follow-up LLM")

            if armor_cfg is None or is_mock_chat_env:
                out_blocked, out_reason = _check_model_armor_response_guard(reply_text)
                if out_blocked:
                    return _make_refusal(out_reason, verdict="MODEL_ARMOR_RESPONSE")

        # Ensure deterministic claim-to-SKU citation alignment
        reply_scrubbed = self.verify_and_align_claim_citations(reply_text, products) or reply_text

        # Persist follow-up chat interaction in Vertex AI Session Service and Memory Bank
        _persist_chat_session_and_memory(
            session_id=session_id,
            user_message=clean_message or message,
            model_reply=reply_scrubbed,
            user_id=resolved_user_id,
        )

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        trace_id = get_current_trace_id()

        return ChatResponse(
            reply=reply_scrubbed,
            citations=citations,
            suggested_followups=suggested[:3],
            latency_ms=latency_ms,
            session_id=session_id,
            trace_id=trace_id,
            agent_version=resolved_agent_version,
            model_version=f"{active_model}@001",
        )


_ASYNC_SAFE_POOL = ThreadPoolExecutor(max_workers=64, thread_name_prefix="async-safe")
_ASYNC_LOOP_LOCAL = threading.local()


def _run_in_thread_loop(coro_fn: Any) -> Any:
    """Reuse a persistent per-thread event loop to avoid socketpair/FD churn under high concurrency."""
    loop = getattr(_ASYNC_LOOP_LOCAL, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _ASYNC_LOOP_LOCAL.loop = loop
    return loop.run_until_complete(coro_fn())


def _run_async_safely(coro_fn: Any) -> Any:
    """Execute an async coroutine function safely whether an event loop is active or not."""
    try:
        asyncio.get_running_loop()
        return _ASYNC_SAFE_POOL.submit(_run_in_thread_loop, coro_fn).result(timeout=8.0)
    except RuntimeError:
        return _run_in_thread_loop(coro_fn)


def _persist_chat_session_and_memory(
    session_id: str | None,
    user_message: str,
    model_reply: str,
    user_id: str | None = None,
) -> None:
    """Persist follow-up chat turns in VertexAiSessionService and commit to VertexAiMemoryBankService."""
    if not session_id:
        return

    effective_user_id = user_id or "default_user"

    async def _persist() -> None:
        from google.adk.events import Event
        from google.genai import types as genai_types

        from app.agent.runner import (
            get_default_memory_service,
            get_default_session_service,
        )

        session_service = get_default_session_service()
        memory_service = get_default_memory_service()

        sess = await session_service.get_session(
            app_name="app",
            user_id=effective_user_id,
            session_id=session_id,
        )
        if sess is None:
            sess = await session_service.create_session(
                app_name="app",
                user_id=effective_user_id,
                session_id=session_id,
                state={"last_query": user_message},
            )

        user_event = Event(
            author="user",
            content=genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=user_message)],
            ),
        )
        model_event = Event(
            author="catalog_comparison_orchestrator",
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part.from_text(text=model_reply)],
            ),
        )
        await session_service.append_event(session=sess, event=user_event)
        await session_service.append_event(session=sess, event=model_event)

        # Tier 1 deterministic stale tool-output pruning
        from app.agent.compaction import prune_tool_outputs

        try:
            prune_tool_outputs(sess)
        except Exception as p_exc:
            logger.debug("Tier 1 tool-output pruning note: %s", p_exc)

        # ADK token-threshold compaction check
        from google.adk.apps.compaction import _run_compaction_for_token_threshold

        from app.agent.runner import catalog_app

        try:
            await _run_compaction_for_token_threshold(
                app=catalog_app,
                session=sess,
                session_service=session_service,
            )
        except Exception as c_exc:
            logger.debug("ADK token-threshold compaction check note: %s", c_exc)

        # Ingest session into memory bank
        await memory_service.add_session_to_memory(sess)

    try:
        _run_async_safely(_persist)
    except Exception as exc:
        logger.debug("Chat session and memory persistence note: %s", exc)
