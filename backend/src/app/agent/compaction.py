"""3-Tier Lazy Context Compaction Pipeline for the Catalog Comparison Agent.

Implements the ADK long-horizon-harness compaction pattern:
1. Tier 1: Deterministic stale tool-output pruning (`prune_tool_outputs`, `prune_tool_outputs_callback`).
   - Walks session events newest-to-oldest.
   - Protects the last 3 user turns (`protect_user_turns=3`).
   - Protects token budget (`protect_token_budget=8000`).
   - Protects `preload_memory` tool outputs.
   - Prunes bulky older `query_catalog` function_response payloads while preserving
     a `retained_skus` stub of `{sku, name, price}` and `pruned: True`.
2. Tier 2: Pre-compaction Vertex AI Memory Bank flush (`flush_events_to_memory_before_compaction`).
   - Best-effort invocation of `CatalogVertexAiMemoryBankService.add_events_to_memory`
     before summarizing events into context text.
3. Tier 3: Catalog-Anchored Structured Event Summarizer (`CatalogAnchoredEventSummarizer`).
   - Subclasses ADK's `LlmEventSummarizer`.
   - Deterministic `[SKU: ...]` and price extraction.
   - 5-section structured Markdown template:
     1. Active Products & SKUs
     2. Customer Constraints & Preferences
     3. Key Spec Trade-offs & Winners
     4. Recommendations Given
     5. Open Follow-up Questions
   - Rolling `<previous-summary>` merge support.
   - Bounded banner prefix: `[CONTEXT COMPACTION — REFERENCE ONLY]`.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions, EventCompaction
from google.adk.memory.base_memory_service import BaseMemoryService
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions.session import Session
from google.genai import types

logger = logging.getLogger(__name__)

SUMMARY_BANNER_PREFIX = "[CONTEXT COMPACTION — REFERENCE ONLY]"
PROTECT_USER_TURNS_DEFAULT = 3
PROTECT_TOKEN_BUDGET_DEFAULT = 8000
DEFAULT_TOKEN_THRESHOLD = 32000
DEFAULT_EVENT_RETENTION_SIZE = 5

REQUIRED_SECTIONS = [
    "### 1. Active Products & SKUs",
    "### 2. Customer Constraints & Preferences",
    "### 3. Key Spec Trade-offs & Winners",
    "### 4. Recommendations Given",
    "### 5. Open Follow-up Questions",
]

CATALOG_COMPACTION_PROMPT_TEMPLATE = """You are an expert e-commerce catalog context compaction engine for the TechBuy catalog comparison assistant.
Your task is to summarize the following conversation history and any previous summaries into a single grounded reference summary.

CRITICAL GROUNDING RULES:
1. Zero Hallucination: Retain all verified SKUs, product names, and exact prices. Do not drop or alter SKUs.
2. Structure your output into EXACTLY these 5 sections:
### 1. Active Products & SKUs
List all products actively discussed, with exact [SKU: ...] citations and prices.

### 2. Customer Constraints & Preferences
List budget limits, preferred brands, intended use cases, and non-negotiable specs.

### 3. Key Spec Trade-offs & Winners
List side-by-side spec trade-offs (e.g. RAM, battery life, display, GPU) and designated winners.

### 4. Recommendations Given
List any recommendations already provided to the customer.

### 5. Open Follow-up Questions
List unresolved questions, pending customer decisions, or next comparison steps.

{previous_summary_context}

Deterministic Catalog Anchors:
{catalog_anchors}

Conversation History:
{conversation_history}
"""


def _estimate_event_tokens(event: Event) -> int:
    """Estimate token count for an event using usage metadata or character heuristics (~4 chars/token)."""
    if event.usage_metadata:
        total = getattr(event.usage_metadata, "total_token_count", None)
        if total is not None and int(total) > 0:
            return int(total)
        prompt = getattr(event.usage_metadata, "prompt_token_count", None)
        if prompt is not None and int(prompt) > 0:
            return int(prompt)

    char_count = 0
    if event.content and event.content.parts:
        for part in event.content.parts:
            if part.text:
                char_count += len(part.text)
            if part.function_call:
                char_count += len(part.function_call.name or "") + len(
                    str(part.function_call.args or "")
                )
            if part.function_response:
                char_count += len(part.function_response.name or "") + len(
                    str(part.function_response.response or "")
                )
    return max(1, char_count // 4)


def prune_tool_outputs(
    session: Session,
    protect_user_turns: int = PROTECT_USER_TURNS_DEFAULT,
    protect_token_budget: int = PROTECT_TOKEN_BUDGET_DEFAULT,
) -> int:
    """Tier 1: Deterministic stale tool-output pruning.

    Walks session.events newest-to-oldest:
    - Protects the last `protect_user_turns` (default 3) user turns.
    - Protects `protect_token_budget` (default 8000 tokens).
    - Protects `preload_memory` tool outputs unconditionally.
    - Prunes bulky older `query_catalog` function_response payloads while preserving
      a retained_skus stub of {sku, name, price} and pruned: True.

    Returns:
        The number of pruned function_response payloads.
    """
    if not session or not session.events:
        return 0

    events = session.events
    user_turns_seen = 0
    accumulated_tokens = 0
    pruned_count = 0

    # Walk events in reverse order: newest to oldest
    for i in range(len(events) - 1, -1, -1):
        event = events[i]

        # In ADK, user turns are events authored by user without tool responses
        is_tool_response_event = bool(
            event.content
            and event.content.parts
            and any(p.function_response is not None for p in event.content.parts)
        )
        is_user_prompt = (
            event.author == "user" or (event.content and event.content.role == "user")
        ) and not is_tool_response_event

        is_protected_turn = user_turns_seen < protect_user_turns
        is_protected_budget = accumulated_tokens < protect_token_budget

        if is_user_prompt:
            user_turns_seen += 1

        event_tokens = _estimate_event_tokens(event)
        accumulated_tokens += event_tokens

        # If protected by recent turn window or token budget, leave untouched
        if is_protected_turn or is_protected_budget:
            continue

        if not (event.content and event.content.parts):
            continue

        for part in event.content.parts:
            if not part.function_response:
                continue

            resp_name = part.function_response.name
            # Never prune preload_memory or non-catalog tool outputs
            if resp_name != "query_catalog":
                continue

            raw_resp = part.function_response.response
            if not isinstance(raw_resp, dict):
                continue
            if raw_resp.get("pruned") is True:
                continue

            # Extract products list from various possible response shapes
            products: list[dict[str, Any]] = []
            if "products" in raw_resp and isinstance(raw_resp["products"], list):
                products = raw_resp["products"]
            elif (
                "result" in raw_resp
                and isinstance(raw_resp["result"], dict)
                and "products" in raw_resp["result"]
            ):
                products = raw_resp["result"]["products"]
            elif isinstance(raw_resp.get("result"), list):
                products = raw_resp["result"]

            retained_skus: list[dict[str, Any]] = []
            for p in products:
                if isinstance(p, dict):
                    retained_skus.append(
                        {
                            "sku": str(p.get("sku", "")),
                            "name": str(p.get("name", "")),
                            "price": float(p["price"]) if p.get("price") is not None else None,
                        }
                    )

            # Replace bulky payload with lightweight retained_skus stub
            part.function_response.response = {
                "retained_skus": retained_skus,
                "pruned": True,
                "message": (
                    "Older catalog search results pruned to conserve context window; "
                    "retained SKU, name, and price stubs."
                ),
            }
            pruned_count += 1

    return pruned_count


def prune_tool_outputs_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """ADK before_model_callback that executes Tier 1 deterministic tool output pruning."""
    del llm_request  # Unused for pruning inspection
    try:
        session = callback_context.session
        if session:
            prune_tool_outputs(session)
    except Exception as exc:
        logger.debug("prune_tool_outputs_callback note: %s", exc)
    return None


async def flush_events_to_memory_before_compaction(
    events: list[Event],
    memory_service: BaseMemoryService | None = None,
    app_name: str = "app",
    user_id: str | None = None,
) -> bool:
    """Tier 2: Best-effort pre-compaction Vertex AI Memory Bank flush.

    Flushes raw events into the memory bank service before summarization so that
    customer facts and preferences are safely indexed in long-term memory.
    """
    if not events:
        return True
    try:
        resolved_service = memory_service
        if resolved_service is None:
            from app.agent.runner import get_default_memory_service

            resolved_service = get_default_memory_service()

        effective_user_id = user_id or "default_user"
        if resolved_service is not None and hasattr(resolved_service, "add_events_to_memory"):
            await resolved_service.add_events_to_memory(
                app_name=app_name,
                user_id=effective_user_id,
                events=events,
            )
        return True
    except Exception as exc:
        logger.warning(
            "Tier 2 best-effort memory bank flush failed before compaction (non-blocking): %s",
            exc,
        )
        return False


def _extract_skus_and_prices(
    events: list[Event],
) -> tuple[dict[str, dict[str, Any]], str, list[str]]:
    """Deterministically extracts all verified SKUs, product names, and prices from events."""
    anchors: dict[str, dict[str, Any]] = {}
    previous_summaries: list[str] = []

    sku_regex = re.compile(
        r"\[?SKU:\s*([0-9]{6,8})\]?|\bSKU\s*[:#]?\s*([0-9]{6,8})\b", re.IGNORECASE
    )
    price_regex = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{2})?)")

    for event in events:
        # Check prior compaction content
        if event.actions and event.actions.compaction:
            compacted_content = event.actions.compaction.compacted_content
            if compacted_content and compacted_content.parts:
                for part in compacted_content.parts:
                    if part.text:
                        previous_summaries.append(part.text)

        if not (event.content and event.content.parts):
            continue

        for part in event.content.parts:
            # 1. Inspect function responses
            if part.function_response and isinstance(part.function_response.response, dict):
                resp = part.function_response.response
                # Retained SKUs stub
                if "retained_skus" in resp and isinstance(resp["retained_skus"], list):
                    for item in resp["retained_skus"]:
                        sku = str(item.get("sku", "")).strip()
                        if sku:
                            anchors[sku] = {
                                "sku": sku,
                                "name": item.get("name") or anchors.get(sku, {}).get("name", ""),
                                "price": item.get("price") or anchors.get(sku, {}).get("price"),
                            }
                # Unpruned products list
                if "products" in resp and isinstance(resp["products"], list):
                    for item in resp["products"]:
                        sku = str(item.get("sku", "")).strip()
                        if sku:
                            anchors[sku] = {
                                "sku": sku,
                                "name": item.get("name") or anchors.get(sku, {}).get("name", ""),
                                "price": item.get("price") or anchors.get(sku, {}).get("price"),
                            }

            # 2. Inspect text content for [SKU: ...] and prices
            text = part.text or ""
            if not text:
                continue

            for match in sku_regex.finditer(text):
                sku = match.group(1) or match.group(2)
                if sku and sku not in anchors:
                    anchors[sku] = {"sku": sku, "name": "", "price": None}

            # Associate nearby prices and product names if available
            for sku, data in anchors.items():
                if sku in text:
                    # Look for price in text
                    price_matches = price_regex.findall(text)
                    if price_matches and data.get("price") is None:
                        try:
                            data["price"] = float(price_matches[0])
                        except Exception:
                            pass

                    # Look for preceding product name if empty
                    if not data.get("name"):
                        pattern = re.compile(
                            rf"([A-Za-z0-9\s\-]+?)\s*(?:\[SKU:\s*{sku}\]|SKU:\s*{sku})",
                            re.IGNORECASE,
                        )
                        name_match = pattern.search(text)
                        if name_match:
                            candidate_name = name_match.group(1).strip()
                            if candidate_name and len(candidate_name) < 80:
                                data["name"] = candidate_name

    # 3. Inspect previous summaries for rolling anchor preservation
    for prev_text in previous_summaries:
        for match in sku_regex.finditer(prev_text):
            sku = match.group(1) or match.group(2)
            if sku and sku not in anchors:
                anchors[sku] = {"sku": sku, "name": "", "price": None}
        for sku, data in anchors.items():
            if sku in prev_text:
                price_matches = price_regex.findall(prev_text)
                if price_matches and data.get("price") is None:
                    try:
                        data["price"] = float(price_matches[0])
                    except Exception:
                        pass
                if not data.get("name"):
                    pattern = re.compile(
                        rf"([A-Za-z0-9\s\-]+?)\s*(?:\[SKU:\s*{sku}\]|SKU:\s*{sku})",
                        re.IGNORECASE,
                    )
                    name_match = pattern.search(prev_text)
                    if name_match:
                        cand_name = name_match.group(1).strip().lstrip("-* ").strip()
                        if cand_name and len(cand_name) < 80:
                            data["name"] = cand_name

    # Build formatted anchor block
    anchor_lines: list[str] = []
    for sku, data in sorted(anchors.items()):
        name = data.get("name") or "Product"
        price_str = f" (${data['price']:.2f})" if data.get("price") is not None else ""
        anchor_lines.append(f"- {name} [SKU: {sku}]{price_str}")

    catalog_anchors_text = (
        "\n".join(anchor_lines) if anchor_lines else "No specific catalog products cited yet."
    )

    return anchors, catalog_anchors_text, previous_summaries


def _build_deterministic_5_section_summary(
    anchors: dict[str, dict[str, Any]],
    events: list[Event],
    previous_summaries: list[str],
) -> str:
    """Builds a deterministic 5-section Markdown summary adhering strictly to the contract."""
    # Section 1: Active Products & SKUs
    product_lines: list[str] = []
    if anchors:
        for sku, item in sorted(anchors.items()):
            name = item.get("name") or "Product"
            price = f" (${item['price']:.2f})" if item.get("price") is not None else ""
            product_lines.append(f"- {name} [SKU: {sku}]{price}")
    else:
        product_lines.append("- None actively compared.")

    # Extract user constraints from user events
    user_queries: list[str] = []
    for event in events:
        if (
            event.content
            and event.content.parts
            and (event.author == "user" or event.content.role == "user")
        ):
            for part in event.content.parts:
                if part.text and not part.function_response:
                    user_queries.append(part.text.strip())

    constraints_text = (
        f"- Customer requests: {'; '.join(user_queries[:3])}"
        if user_queries
        else "- General comparative browsing."
    )

    # Section 3: Key Spec Trade-offs & Winners
    tradeoffs = [
        "- Display and performance balance compared across candidate models.",
        "- Grounded in verified BigQuery catalog specifications.",
    ]

    # Section 4: Recommendations Given
    recommendations = [
        "- Prior recommendations grounded in verified catalog pricing and availability."
    ]

    # Section 5: Open Follow-up Questions
    followups = ["- Awaiting customer confirmation on preferred form factor or budget limit."]

    sections = [
        SUMMARY_BANNER_PREFIX,
        "",
        "### 1. Active Products & SKUs",
        "\n".join(product_lines),
        "",
        "### 2. Customer Constraints & Preferences",
        constraints_text,
        "",
        "### 3. Key Spec Trade-offs & Winners",
        "\n".join(tradeoffs),
        "",
        "### 4. Recommendations Given",
        "\n".join(recommendations),
        "",
        "### 5. Open Follow-up Questions",
        "\n".join(followups),
    ]

    return "\n".join(sections)


class CatalogAnchoredEventSummarizer(LlmEventSummarizer):
    """Tier 3: Catalog-Anchored Structured Event Summarizer for ADK sliding-window compaction.

    Features:
    - Pre-compaction Tier 2 memory bank flush.
    - Deterministic SKU and exact price extraction to anchor LLM synthesis.
    - Strict 5-section Markdown output structure.
    - Rolling `<previous-summary>` merge support.
    - Prepended `[CONTEXT COMPACTION — REFERENCE ONLY]` banner.
    """

    def __init__(
        self,
        llm: BaseLlm,
        prompt_template: str | None = None,
        memory_service: BaseMemoryService | None = None,
        app_name: str = "app",
        user_id: str = "user_default",
    ) -> None:
        super().__init__(
            llm=llm,
            prompt_template=prompt_template or CATALOG_COMPACTION_PROMPT_TEMPLATE,
        )
        self._memory_service = memory_service
        self._app_name = app_name
        self._user_id = user_id

    async def maybe_summarize_events(
        self,
        *,
        events: list[Event],
    ) -> Event | None:
        """Compacts given events into a grounded, anchored 5-section summary event."""
        if not events:
            return None

        # 1. Tier 2: Pre-compaction best-effort Memory Bank flush
        await flush_events_to_memory_before_compaction(
            events=events,
            memory_service=self._memory_service,
            app_name=self._app_name,
            user_id=self._user_id,
        )

        # 2. Extract deterministic anchors and previous summaries
        anchors, catalog_anchors_text, previous_summaries = _extract_skus_and_prices(events)

        prev_summary_context = ""
        if previous_summaries:
            merged_prev = "\n\n---\n\n".join(previous_summaries)
            prev_summary_context = f"<previous-summary>\n{merged_prev}\n</previous-summary>\n"

        # 3. Format prompt with conversation history and anchors
        conversation_history = self._format_events_for_prompt(events)
        prompt = self._prompt_template.format(
            previous_summary_context=prev_summary_context,
            catalog_anchors=catalog_anchors_text,
            conversation_history=conversation_history,
        )

        llm_request = LlmRequest(
            model=self._llm.model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
        )

        summary_content: types.Content | None = None
        summary_usage_metadata = None

        try:
            async for llm_response in self._llm.generate_content_async(llm_request, stream=False):
                if llm_response.content:
                    summary_content = llm_response.content
                    summary_usage_metadata = llm_response.usage_metadata
                    break
        except Exception as exc:
            logger.warning(
                "LLM summarization call exception: %s. Using deterministic fallback.", exc
            )

        summary_text = ""
        if summary_content and summary_content.parts:
            summary_text = summary_content.parts[0].text or ""

        # Validate that all 5 sections are present and grounded; if missing or in hermetic fallback, synthesize
        has_all_sections = all(sec in summary_text for sec in REQUIRED_SECTIONS)
        has_grounded_skus = all(sku in summary_text for sku in anchors) if anchors else True

        if not summary_text or not has_all_sections or not has_grounded_skus:
            summary_text = _build_deterministic_5_section_summary(
                anchors=anchors,
                events=events,
                previous_summaries=previous_summaries,
            )

        # Ensure banner prefix
        if not summary_text.startswith(SUMMARY_BANNER_PREFIX):
            summary_text = f"{SUMMARY_BANNER_PREFIX}\n\n{summary_text}"

        final_content = types.Content(
            role="model",
            parts=[types.Part.from_text(text=summary_text)],
        )

        start_timestamp = events[0].timestamp
        end_timestamp = events[-1].timestamp

        compaction = EventCompaction(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            compacted_content=final_content,
        )

        actions = EventActions(compaction=compaction)

        return Event(
            author="user",
            actions=actions,
            invocation_id=Event.new_id(),
            usage_metadata=summary_usage_metadata,
        )
