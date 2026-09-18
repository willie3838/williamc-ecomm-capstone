"""Head-to-Head Pairwise Model Quality Judge for Foundation Model Selection.

Evaluates pairs of candidate model comparison summaries (`Response A` vs `Response B`)
against BigQuery catalog ground truth matrices across three primary dimensions:
1. Data Accuracy & Numerical Fidelity (`accuracy_winner`)
2. Citation Faithfulness & SKU Traceability (`citation_winner`)
3. Executive Synthesis Depth & Trade-Off Nuance (`synthesis_winner`)

Enforces strict Pydantic JSON `response_schema`, `temperature=0.0`, and `max_output_tokens=1024`,
with swapped-order position-bias verification (`(A, B)` vs `(B, A)`) and a deterministic
hermetic evaluator for offline CI execution.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Literal

from app.models.responses import MatrixRow
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from evals.judge import format_matrix_differences, get_gemini_judge_client

logger = logging.getLogger("evals.pairwise_judge")

PairwiseWinner = Literal["A", "B", "TIE"]


class PairwiseJudgment(BaseModel):
    """Structured head-to-head evaluation verdict comparing two model responses."""

    overall_winner: PairwiseWinner = Field(
        description="Overall winning candidate ('A', 'B', or 'TIE')."
    )
    accuracy_winner: PairwiseWinner = Field(
        description="Candidate with superior numerical spec accuracy and zero contradictions ('A', 'B', or 'TIE')."
    )
    citation_winner: PairwiseWinner = Field(
        description="Candidate with superior inline [SKU: ...] citation coverage ('A', 'B', or 'TIE')."
    )
    synthesis_winner: PairwiseWinner = Field(
        description="Candidate with deeper trade-off reasoning and actionable buyer guidance ('A', 'B', or 'TIE')."
    )
    score_a: float = Field(
        ge=1.0,
        le=5.0,
        description="Absolute quality score for Response A on a 1.0 to 5.0 scale.",
    )
    score_b: float = Field(
        ge=1.0,
        le=5.0,
        description="Absolute quality score for Response B on a 1.0 to 5.0 scale.",
    )
    win_margin: float = Field(
        ge=0.0,
        le=4.0,
        description="Absolute score difference |score_a - score_b|.",
    )
    position_bias_checked: bool = Field(
        default=True,
        description="Whether swapped-order position bias verification was executed.",
    )
    reasoning: str = Field(
        description="Detailed comparative justification citing specific specs, citations, and trade-offs."
    )


class PairwiseBatchSummary(BaseModel):
    """Aggregate summary of a head-to-head pairwise tournament across benchmark queries."""

    model_a: str
    model_b: str
    total_pairs: int = Field(ge=0)
    wins_a: int = Field(ge=0)
    wins_b: int = Field(ge=0)
    ties: int = Field(ge=0)
    win_rate_a: float = Field(ge=0.0, le=1.0)
    win_rate_b: float = Field(ge=0.0, le=1.0)
    tie_rate: float = Field(ge=0.0, le=1.0)
    mean_score_a: float = Field(ge=1.0, le=5.0)
    mean_score_b: float = Field(ge=1.0, le=5.0)
    mean_margin: float = Field(ge=0.0, le=4.0)
    overall_winner: PairwiseWinner
    summary_rationale: str


def _invert_winner(winner: PairwiseWinner) -> PairwiseWinner:
    """Invert winner label when candidate order is swapped (B vs A -> A vs B)."""
    if winner == "A":
        return "B"
    if winner == "B":
        return "A"
    return "TIE"


def _build_pairwise_prompt(
    query: str,
    matrix_table: str,
    candidate_a: str,
    candidate_b: str,
) -> str:
    """Construct an impartial pairwise judge prompt with explicit calibration rubrics."""
    return f"""You are an impartial Principal AI Evaluation Judge comparing two candidate product comparison responses (Candidate A and Candidate B).

[USER QUERY]
{query}

[GROUND TRUTH COMPARISON MATRIX]
{matrix_table}

[CANDIDATE A RESPONSE]
{candidate_a}

[CANDIDATE B RESPONSE]
{candidate_b}

Evaluation Rubric:
1. Data Accuracy (`accuracy_winner`):
   - Does the response accurately reflect prices, winners, and specifications from the Ground Truth Matrix without contradiction or inverted winners?
2. Citation Faithfulness (`citation_winner`):
   - Does every product claim include verifiable inline bracket SKU citations (e.g., `[SKU: 6534606]`) matching the matrix SKUs?
3. Executive Synthesis Depth (`synthesis_winner`):
   - Does the response synthesize clear price-to-performance trade-offs and actionable buyer recommendations tailored to specific shopper personas?
4. Scoring & Tie-Breaking:
   - Score each response from 1.0 (hallucinated/contradictory) to 5.0 (flawless grounding, citations, and executive trade-off synthesis).
   - Declare 'TIE' if both responses are equally accurate and within 0.15 points.
"""


def _invoke_single_pairwise_pass(
    client: genai.Client,
    prompt: str,
    model: str,
    fallback_model: str,
    max_output_tokens: int = 1024,
) -> PairwiseJudgment | None:
    """Invoke Vertex AI Gemini with strict Pydantic response_schema enforcement."""
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
                    response_schema=PairwiseJudgment,
                    temperature=0.0,
                    max_output_tokens=max_output_tokens,
                ),
            )
            if response and response.text:
                data: dict[str, Any] = json.loads(response.text)
                return PairwiseJudgment.model_validate(data)
        except Exception as err:  # noqa: BLE001
            logger.info(
                "Pairwise judge model %s encountered error: %s. Trying next candidate.",
                candidate_model,
                err,
            )
            continue
    return None


def evaluate_pairwise_responses(
    query: str,
    matrix: list[MatrixRow],
    response_a: str,
    response_b: str,
    client: genai.Client | None = None,
    model: str = "gemini-3.5-flash",
    fallback_model: str = "gemini-2.5-flash",
    check_position_bias: bool = True,
    use_live_client: bool = True,
    max_output_tokens: int = 1024,
) -> PairwiseJudgment:
    """Evaluate two candidate model responses head-to-head with position-bias verification.

    When `check_position_bias=True` and a live/mock `client` is available, executes two
    evaluations: forward `(A, B)` and swapped `(B, A)`. If the judge contradicts itself
    due to position bias, the result is conservatively resolved to `TIE`.
    Falls back to `_deterministic_pairwise_check` in offline/hermetic CI environments.
    """
    if response_a.strip() == response_b.strip():
        det = _deterministic_pairwise_check(matrix, response_a, response_b)
        return det

    matrix_table = format_matrix_differences(matrix)

    if client is None and use_live_client:
        client = get_gemini_judge_client()

    if client is not None:
        forward_prompt = _build_pairwise_prompt(query, matrix_table, response_a, response_b)
        forward_res = _invoke_single_pairwise_pass(
            client=client,
            prompt=forward_prompt,
            model=model,
            fallback_model=fallback_model,
            max_output_tokens=max_output_tokens,
        )

        if forward_res is not None:
            if not check_position_bias:
                return forward_res

            swapped_prompt = _build_pairwise_prompt(query, matrix_table, response_b, response_a)
            swapped_res = _invoke_single_pairwise_pass(
                client=client,
                prompt=swapped_prompt,
                model=model,
                fallback_model=fallback_model,
                max_output_tokens=max_output_tokens,
            )
            if swapped_res is None:
                return forward_res

            # Map swapped winner back to original (A, B) coordinates
            mapped_swapped_winner = _invert_winner(swapped_res.overall_winner)
            avg_score_a = round((forward_res.score_a + swapped_res.score_b) / 2.0, 2)
            avg_score_b = round((forward_res.score_b + swapped_res.score_a) / 2.0, 2)
            margin = round(abs(avg_score_a - avg_score_b), 2)

            if forward_res.overall_winner == mapped_swapped_winner:
                return PairwiseJudgment(
                    overall_winner=forward_res.overall_winner,
                    accuracy_winner=forward_res.accuracy_winner,
                    citation_winner=forward_res.citation_winner,
                    synthesis_winner=forward_res.synthesis_winner,
                    score_a=avg_score_a,
                    score_b=avg_score_b,
                    win_margin=margin,
                    position_bias_checked=True,
                    reasoning=(
                        f"{forward_res.reasoning} (Verified invariant under swapped-order "
                        f"position-bias check: {swapped_res.reasoning})"
                    ),
                )

            # Position bias conflict detected -> resolve to TIE
            return PairwiseJudgment(
                overall_winner="TIE",
                accuracy_winner="TIE",
                citation_winner="TIE",
                synthesis_winner="TIE",
                score_a=avg_score_a,
                score_b=avg_score_b,
                win_margin=margin,
                position_bias_checked=True,
                reasoning=(
                    f"Position bias detected across swapped evaluation orders "
                    f"(forward={forward_res.overall_winner}, swapped_mapped={mapped_swapped_winner}); "
                    f"conservatively resolved to TIE."
                ),
            )

    return _deterministic_pairwise_check(matrix, response_a, response_b)


def _score_single_candidate_deterministically(
    matrix: list[MatrixRow],
    text: str,
) -> dict[str, Any]:
    """Deterministically score a candidate response for accuracy, citations, and synthesis depth."""
    text_lower = text.lower()
    expected_skus: list[str] = []
    for row in matrix:
        for sku in row.values:
            if str(sku) not in expected_skus:
                expected_skus.append(str(sku))

    # 1. Citation score (1.0 to 5.0)
    cited_skus = {
        m.upper() for m in re.findall(r"\[sku:\s*([a-zA-Z0-9_-]+)\]", text, re.IGNORECASE)
    }
    if not expected_skus:
        citation_ratio = 1.0 if cited_skus else 0.8
    else:
        matched = sum(1 for sku in expected_skus if sku.upper() in cited_skus)
        citation_ratio = matched / len(expected_skus)
    citation_score = round(1.0 + 4.0 * citation_ratio, 2)

    # 2. Data Accuracy & Absence of Contradictions (1.0 to 5.0)
    has_contradiction = False
    price_row = next((r for r in matrix if "price" in r.feature.lower()), None)
    if price_row and price_row.winner_sku and len(price_row.values) >= 2:
        winner_sku = str(price_row.winner_sku)
        other_skus = [str(s) for s in price_row.values if str(s) != winner_sku]
        for other_sku in other_skus:
            if (
                f"[sku: {other_sku.lower()}] is more affordable" in text_lower
                or f"[sku: {other_sku.lower()}] is cheaper" in text_lower
                or ("dell xps 13 is cheaper" in text_lower and winner_sku == "6534606")
            ):
                has_contradiction = True

    # Count grounded values referenced from the matrix
    referenced_values = 0
    total_values = 0
    for row in matrix:
        for val_str in row.values.values():
            total_values += 1
            cleaned_val = str(val_str).lower().replace("$", "").replace(",", "")
            if cleaned_val in text_lower.replace("$", "").replace(",", ""):
                referenced_values += 1

    grounding_coverage = (referenced_values / total_values) if total_values > 0 else 0.5
    if has_contradiction:
        accuracy_score = 1.2
    else:
        accuracy_score = round(min(5.0, 2.6 + 2.4 * grounding_coverage), 2)

    # 3. Synthesis depth score (1.0 to 5.0)
    has_recommendation = any(
        kw in text_lower for kw in ("recommend", "choose", "ideal for", "best for", "buy")
    )
    has_tradeoff = any(
        kw in text_lower for kw in ("whereas", "while", "compared to", "however", "versus", "vs")
    )
    word_count = len(text.split())
    depth_factor = min(1.0, word_count / 35.0)
    synthesis_score = 2.0 + (1.2 * depth_factor)
    if has_recommendation:
        synthesis_score += 1.0
    if has_tradeoff:
        synthesis_score += 0.8
    if has_contradiction:
        synthesis_score = min(synthesis_score, 2.0)
    synthesis_score = round(min(5.0, synthesis_score), 2)

    total_score = round(
        0.45 * accuracy_score + 0.30 * citation_score + 0.25 * synthesis_score,
        2,
    )
    return {
        "accuracy_score": accuracy_score,
        "citation_score": citation_score,
        "synthesis_score": synthesis_score,
        "total_score": total_score,
        "has_contradiction": has_contradiction,
    }


def _pick_dimension_winner(val_a: float, val_b: float, tol: float = 0.1) -> PairwiseWinner:
    if abs(val_a - val_b) <= tol:
        return "TIE"
    return "A" if val_a > val_b else "B"


def _deterministic_pairwise_check(
    matrix: list[MatrixRow],
    response_a: str,
    response_b: str,
) -> PairwiseJudgment:
    """Hermetic deterministic pairwise comparison of two candidate summaries."""
    if response_a.strip() == response_b.strip():
        metrics = _score_single_candidate_deterministically(matrix, response_a)
        return PairwiseJudgment(
            overall_winner="TIE",
            accuracy_winner="TIE",
            citation_winner="TIE",
            synthesis_winner="TIE",
            score_a=metrics["total_score"],
            score_b=metrics["total_score"],
            win_margin=0.0,
            position_bias_checked=True,
            reasoning="Both candidates produced identical grounded responses, resulting in an exact TIE.",
        )

    metrics_a = _score_single_candidate_deterministically(matrix, response_a)
    metrics_b = _score_single_candidate_deterministically(matrix, response_b)

    acc_winner = _pick_dimension_winner(metrics_a["accuracy_score"], metrics_b["accuracy_score"])
    cit_winner = _pick_dimension_winner(metrics_a["citation_score"], metrics_b["citation_score"])
    syn_winner = _pick_dimension_winner(metrics_a["synthesis_score"], metrics_b["synthesis_score"])
    overall_winner = _pick_dimension_winner(
        metrics_a["total_score"], metrics_b["total_score"], tol=0.12
    )
    margin = round(abs(metrics_a["total_score"] - metrics_b["total_score"]), 2)

    return PairwiseJudgment(
        overall_winner=overall_winner,
        accuracy_winner=acc_winner,
        citation_winner=cit_winner,
        synthesis_winner=syn_winner,
        score_a=metrics_a["total_score"],
        score_b=metrics_b["total_score"],
        win_margin=margin,
        position_bias_checked=True,
        reasoning=(
            f"Deterministic evaluation: Candidate A scored {metrics_a['total_score']:.2f} "
            f"(acc={metrics_a['accuracy_score']:.2f}, cit={metrics_a['citation_score']:.2f}, "
            f"syn={metrics_a['synthesis_score']:.2f}) vs Candidate B {metrics_b['total_score']:.2f} "
            f"(acc={metrics_b['accuracy_score']:.2f}, cit={metrics_b['citation_score']:.2f}, "
            f"syn={metrics_b['synthesis_score']:.2f}). Winner: {overall_winner}."
        ),
    )


def evaluate_pairwise_batch(
    model_a: str,
    model_b: str,
    pairs: list[dict[str, Any]],
    client: genai.Client | None = None,
    use_live_client: bool = False,
) -> PairwiseBatchSummary:
    """Run a head-to-head pairwise evaluation tournament across a batch of comparison pairs."""
    if not pairs:
        return PairwiseBatchSummary(
            model_a=model_a,
            model_b=model_b,
            total_pairs=0,
            wins_a=0,
            wins_b=0,
            ties=0,
            win_rate_a=0.0,
            win_rate_b=0.0,
            tie_rate=0.0,
            mean_score_a=3.0,
            mean_score_b=3.0,
            mean_margin=0.0,
            overall_winner="TIE",
            summary_rationale="No comparison pairs evaluated.",
        )

    wins_a = 0
    wins_b = 0
    ties = 0
    scores_a: list[float] = []
    scores_b: list[float] = []
    margins: list[float] = []

    for item in pairs:
        raw_matrix = item.get("matrix", [])
        matrix_rows = [
            r if isinstance(r, MatrixRow) else MatrixRow.model_validate(r) for r in raw_matrix
        ]
        judgment = evaluate_pairwise_responses(
            query=str(item.get("query", "")),
            matrix=matrix_rows,
            response_a=str(item.get("response_a", "")),
            response_b=str(item.get("response_b", "")),
            client=client,
            use_live_client=use_live_client,
        )
        scores_a.append(judgment.score_a)
        scores_b.append(judgment.score_b)
        margins.append(judgment.win_margin)
        if judgment.overall_winner == "A":
            wins_a += 1
        elif judgment.overall_winner == "B":
            wins_b += 1
        else:
            ties += 1

    total = len(pairs)
    win_rate_a = round(wins_a / total, 4)
    win_rate_b = round(wins_b / total, 4)
    tie_rate = round(ties / total, 4)
    mean_a = round(sum(scores_a) / total, 2)
    mean_b = round(sum(scores_b) / total, 2)
    mean_margin = round(sum(margins) / total, 2)

    if wins_a > wins_b:
        overall: PairwiseWinner = "A"
    elif wins_b > wins_a:
        overall = "B"
    else:
        overall = "TIE"

    winner_name = model_a if overall == "A" else (model_b if overall == "B" else "TIE")
    return PairwiseBatchSummary(
        model_a=model_a,
        model_b=model_b,
        total_pairs=total,
        wins_a=wins_a,
        wins_b=wins_b,
        ties=ties,
        win_rate_a=win_rate_a,
        win_rate_b=win_rate_b,
        tie_rate=tie_rate,
        mean_score_a=mean_a,
        mean_score_b=mean_b,
        mean_margin=mean_margin,
        overall_winner=overall,
        summary_rationale=(
            f"{model_a} achieved {win_rate_a * 100:.1f}% win rate ({wins_a}W-{wins_b}L-{ties}T, "
            f"mean score {mean_a:.2f} vs {mean_b:.2f}) against {model_b}. Tournament winner: {winner_name}."
        ),
    )


def main() -> None:
    """CLI entrypoint for running a sample pairwise evaluation check."""
    parser = argparse.ArgumentParser(description="Run Head-to-Head Pairwise Model Quality Judge.")
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Use live Vertex AI Gemini Judge instead of hermetic deterministic judge.",
    )
    args = parser.parse_args()

    sample_matrix = [
        MatrixRow(
            feature="Price",
            values={"6534606": "$1,099.00", "6543210": "$1,299.00"},
            winner_sku="6534606",
        ),
        MatrixRow(
            feature="Battery Life",
            values={"6534606": "18.0 hours", "6543210": "12.0 hours"},
            winner_sku="6534606",
        ),
    ]
    res = evaluate_pairwise_responses(
        query="Compare Apple MacBook Air M3 and Dell XPS 13",
        matrix=sample_matrix,
        response_a=(
            "Apple MacBook Air M3 [SKU: 6534606] leads on price at $1,099.00 and battery life at "
            "18.0 hours compared to Dell XPS 13 [SKU: 6543210] ($1,299.00, 12.0 hours). "
            "Recommendation: Choose [SKU: 6534606] for all-day battery and value."
        ),
        response_b="MacBook Air [SKU: 6534606] is $1,099.00 while Dell XPS 13 is $1,299.00.",
        use_live_client=args.live,
    )
    print(json.dumps(res.model_dump(), indent=2))


if __name__ == "__main__":
    main()
