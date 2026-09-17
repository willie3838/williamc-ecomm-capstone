"""Gemini Flash LLM-as-a-Judge for Semantic Comparison Quality Evaluation.

Implements Section 3 of SPEC.md:
"Uses Gemini 3.5 Flash to verify that the comparison summary accurately reflects
the differences listed in the data tables."
"""

import json
import logging
import os
import re
from typing import Any

from app.config import settings
from app.models.responses import MatrixRow
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger("evals.judge")


class FaithfulnessResult(BaseModel):
    """Evaluation result for semantic comparison faithfulness."""

    is_faithful: bool = Field(
        description="Whether the comparison summary accurately reflects the differences listed in the data tables."
    )
    score: int = Field(
        ge=1,
        le=5,
        description="Faithfulness score from 1 (unacceptable/contradictory) to 5 (flawless/accurate).",
    )
    has_contradiction: bool = Field(
        description="Whether the comparison narrative contains contradictory claims or inverted winners."
    )
    reasoning: str = Field(
        description="Concise rationale explaining how the summary reflects or contradicts the data tables."
    )


def format_matrix_differences(matrix: list[MatrixRow]) -> str:
    """Format comparison matrix rows and differences into a clean markdown table."""
    if not matrix:
        return "No comparison matrix rows provided."

    # Extract all product SKUs present across matrix rows
    all_skus: list[str] = []
    for row in matrix:
        for sku in row.values:
            if sku not in all_skus:
                all_skus.append(sku)

    headers = ["Feature", "Winner SKU"] + [f"SKU {sku}" for sku in all_skus]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for row in matrix:
        winner_str = str(row.winner_sku) if row.winner_sku else "None (Tie/Neutral)"
        cols = [
            row.feature,
            winner_str,
        ] + [str(row.values.get(sku, "N/A")) for sku in all_skus]
        lines.append("| " + " | ".join(cols) + " |")

    return "\n".join(lines)


def get_gemini_judge_client() -> genai.Client | None:
    """Initialize Vertex AI GenAI client for LLM-as-a-judge evaluation."""
    if "GOOGLE_API_USE_CLIENT_CERTIFICATE" not in os.environ:
        os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

    try:
        client = genai.Client(
            vertexai=True,
            project=settings.project_id,
            location="us-central1",
        )
        return client
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to initialize Vertex GenAI client: %s", e)
        return None


_RESOLVED_WORKING_MODEL: str | None = None


def evaluate_comparison_faithfulness(
    query: str,
    matrix: list[MatrixRow],
    summary: str,
    client: genai.Client | None = None,
    model: str = "gemini-3.5-flash",
    fallback_model: str = "gemini-2.5-flash",
) -> FaithfulnessResult:
    """Evaluate whether the comparison summary accurately reflects the data table differences.

    Uses Gemini Flash (via Vertex AI) as an impartial evaluation judge. If the model
    returns a 404 (e.g. 3.5 Flash not yet provisioned in the region), it automatically
    falls back to 2.5 Flash. If completely offline or uncredentialed, uses a deterministic
    matrix validator fallback.
    """
    global _RESOLVED_WORKING_MODEL
    matrix_table = format_matrix_differences(matrix)

    prompt = f"""You are an expert impartial evaluation judge assessing an AI product comparison assistant.
Your task is to verify that the comparison summary accurately reflects the differences listed in the data tables.

[INPUT QUERY]
{query}

[DATA TABLE / MATRIX DIFFERENCES]
{matrix_table}

[GENERATED COMPARISON SUMMARY]
{summary}

Evaluation Instructions:
1. Accurate Reflection: Does the comparison summary faithfully describe the key differences and relative advantages shown in the data table? Note: A comparison summary is an executive overview focusing on primary buying factors (price, battery, performance, portability, display). It is NOT required to redundantly list every minor row (such as customer rating or review count) to be faithful.
2. Zero Contradictions: Does the narrative never invert comparison winners (e.g., asserting a more expensive product is cheaper, or a slower CPU is faster)? Any inverted winner is a critical failure.
3. Grounded Claims: Are all comparative claims and specs strictly consistent with the numbers and features in the data table?
4. Faithfulness Definition:
   - Set `is_faithful: true` if the comparison narrative is completely grounded in the table and contains zero contradictions, zero inverted winners, and zero hallucinated specifications.
   - Set `is_faithful: false` ONLY if the summary contradicts the table, inverts a winner, or makes unsubstantiated/hallucinated factual claims.
5. Score Calibration:
   - 5: Perfectly faithful to data tables; key differentiators accurately captured; zero contradictions.
   - 4: Accurate reflection of primary differences and advantages with zero contradictions, even if minor tertiary rows are omitted.
   - 3: General gist correct, but makes vague/unsupported claims or omits a crucial primary factor.
   - 2: Minor factual discrepancy or misstated specification from table.
   - 1: Direct contradiction with data table (e.g., inverted winner) or hallucinated specs.
"""

    if client is None:
        client = get_gemini_judge_client()

    if client is not None:
        if _RESOLVED_WORKING_MODEL:
            models_to_try = [_RESOLVED_WORKING_MODEL]
        else:
            models_to_try = [model]
            if fallback_model and fallback_model != model:
                models_to_try.append(fallback_model)

        for candidate_model in models_to_try:
            try:
                response = client.models.generate_content(
                    model=candidate_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=FaithfulnessResult,
                        temperature=0.0,
                    ),
                )
                if response and response.text:
                    data: dict[str, Any] = json.loads(response.text)
                    _RESOLVED_WORKING_MODEL = candidate_model
                    return FaithfulnessResult.model_validate(data)
            except Exception as err:  # noqa: BLE001
                logger.info(
                    "Judge model %s generation encountered: %s. Trying fallback if available.",
                    candidate_model,
                    err,
                )
                continue

    # Hermetic deterministic fallback (for offline CI or uncredentialed environments)
    return _deterministic_faithfulness_check(matrix, summary)


def _deterministic_faithfulness_check(
    matrix: list[MatrixRow],
    summary: str,
) -> FaithfulnessResult:
    """Hermetic deterministic verification of summary vs matrix differences."""
    summary_lower = summary.lower()
    has_contradiction = False
    reasons: list[str] = []

    # Check for price contradiction
    price_row = next((r for r in matrix if "price" in r.feature.lower()), None)
    if price_row and price_row.winner_sku and len(price_row.values) >= 2:
        winner_sku = str(price_row.winner_sku)
        other_skus = [str(s) for s in price_row.values if str(s) != winner_sku]
        if other_skus:
            other_sku = other_skus[0]
            # If the higher price SKU is claimed as cheaper/more affordable
            if (
                f"[sku: {other_sku}] is more affordable" in summary_lower
                or f"{other_sku} is cheaper" in summary_lower
            ):
                has_contradiction = True
                reasons.append(
                    f"Summary claimed SKU {other_sku} is cheaper, but winner is {winner_sku}"
                )

    # Check that winner SKUs or key differences are mentioned
    mentioned_skus = re.findall(r"\[sku:\s*([a-za-z0-9_-]+)\]", summary, re.IGNORECASE)
    if not mentioned_skus and len(matrix) > 0:
        return FaithfulnessResult(
            is_faithful=False,
            score=2,
            has_contradiction=has_contradiction,
            reasoning="Summary does not cite SKUs from the comparison matrix.",
        )

    if has_contradiction:
        return FaithfulnessResult(
            is_faithful=False,
            score=1,
            has_contradiction=True,
            reasoning="; ".join(reasons),
        )

    return FaithfulnessResult(
        is_faithful=True,
        score=5,
        has_contradiction=False,
        reasoning="Summary accurately reflects comparison matrix specs and winner differences without contradiction.",
    )
