"""Unit tests for evals.pairwise_judge, evals.generate_model_matrix, and ADR-004 sync."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from evals.generate_model_matrix import (
    DecisionWeights,
    ModelDecisionMatrixReport,
    build_model_decision_matrix,
    evaluate_candidate_profile,
)
from evals.pairwise_judge import (
    PairwiseBatchSummary,
    PairwiseJudgment,
    evaluate_pairwise_batch,
    evaluate_pairwise_responses,
)

from app.models.responses import MatrixRow

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def sample_matrix() -> list[MatrixRow]:
    """Sample side-by-side comparison matrix for MacBook Air M3 vs Dell XPS 13."""
    return [
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
        MatrixRow(
            feature="Memory (RAM)",
            values={"6534606": "16 GB", "6543210": "32 GB"},
            winner_sku="6543210",
        ),
    ]


def test_deterministic_pairwise_check_clear_winner_and_contradiction(
    sample_matrix: list[MatrixRow],
) -> None:
    """Verify deterministic pairwise judge rewards grounded SKU citations and penalizes contradictions."""
    query = "Compare Apple MacBook Air M3 and Dell XPS 13"
    response_a = (
        "Apple MacBook Air M3 [SKU: 6534606] is more affordable at $1,099.00 and leads in "
        "battery life with 18.0 hours, whereas Dell XPS 13 [SKU: 6543210] at $1,299.00 offers "
        "superior multitasking with 32 GB RAM compared to 16 GB. "
        "Recommendation: Choose [SKU: 6534606] for portability and battery endurance, or "
        "choose [SKU: 6543210] for memory-intensive workloads."
    )
    # Response B has a direct price contradiction and omits SKU 6543210 citation
    response_b = "Dell XPS 13 is cheaper than MacBook Air [SKU: 6534606] and has decent specs."

    judgment = evaluate_pairwise_responses(
        query=query,
        matrix=sample_matrix,
        response_a=response_a,
        response_b=response_b,
        client=None,
        use_live_client=False,
    )

    assert isinstance(judgment, PairwiseJudgment)
    assert judgment.overall_winner == "A"
    assert judgment.accuracy_winner == "A"
    assert judgment.citation_winner == "A"
    assert judgment.synthesis_winner == "A"
    assert judgment.score_a > judgment.score_b
    assert judgment.win_margin > 0.5
    assert judgment.position_bias_checked is True


def test_deterministic_pairwise_tie_on_identical_responses(
    sample_matrix: list[MatrixRow],
) -> None:
    """Verify identical grounded responses produce a TIE with zero margin."""
    query = "Compare Apple MacBook Air M3 and Dell XPS 13"
    response = (
        "Apple MacBook Air M3 [SKU: 6534606] costs $1,099.00 with 18.0 hours battery life, "
        "while Dell XPS 13 [SKU: 6543210] costs $1,299.00 with 32 GB RAM."
    )

    judgment = evaluate_pairwise_responses(
        query=query,
        matrix=sample_matrix,
        response_a=response,
        response_b=response,
        client=None,
        use_live_client=False,
    )

    assert judgment.overall_winner == "TIE"
    assert judgment.win_margin == 0.0
    assert judgment.score_a == judgment.score_b


def test_evaluate_pairwise_responses_with_mock_genai_client(
    sample_matrix: list[MatrixRow],
) -> None:
    """Verify LLM judge uses strict response_schema, temperature=0.0, max_output_tokens, and position-bias verification."""
    mock_client = MagicMock()

    # Forward pass (A vs B): A wins
    forward_payload = {
        "overall_winner": "A",
        "accuracy_winner": "A",
        "citation_winner": "TIE",
        "synthesis_winner": "A",
        "score_a": 4.8,
        "score_b": 4.1,
        "win_margin": 0.7,
        "position_bias_checked": True,
        "reasoning": "Response A provides sharper trade-off analysis and exact SKU citations.",
    }
    # Swapped pass (B vs A): B (which was original A) wins
    reverse_payload = {
        "overall_winner": "B",
        "accuracy_winner": "B",
        "citation_winner": "TIE",
        "synthesis_winner": "B",
        "score_a": 4.0,
        "score_b": 4.9,
        "win_margin": 0.9,
        "position_bias_checked": True,
        "reasoning": "Second candidate (original A) is more thorough and accurate.",
    }

    mock_resp_1 = MagicMock()
    mock_resp_1.text = json.dumps(forward_payload)
    mock_resp_2 = MagicMock()
    mock_resp_2.text = json.dumps(reverse_payload)

    mock_client.models.generate_content.side_effect = [mock_resp_1, mock_resp_2]

    judgment = evaluate_pairwise_responses(
        query="Compare MacBook Air and XPS 13",
        matrix=sample_matrix,
        response_a="Grounded response A [SKU: 6534606] [SKU: 6543210]",
        response_b="Grounded response B [SKU: 6534606]",
        client=mock_client,
        check_position_bias=True,
    )

    assert judgment.overall_winner == "A"
    assert judgment.position_bias_checked is True
    assert judgment.score_a == pytest.approx(4.85, abs=0.05)
    assert judgment.score_b == pytest.approx(4.05, abs=0.05)

    # Verify GenerateContentConfig passed response_schema, temperature=0.0, and max_output_tokens
    call_kwargs = mock_client.models.generate_content.call_args_list[0].kwargs
    config = call_kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema == PairwiseJudgment
    assert config.temperature == 0.0
    assert config.max_output_tokens == 1024


def test_evaluate_pairwise_position_bias_conflict_resolves_to_tie(
    sample_matrix: list[MatrixRow],
) -> None:
    """Verify that if LLM judge exhibits position bias (picks first position in both orders), it resolves to TIE."""
    mock_client = MagicMock()

    # Both passes pick "A" (meaning the judge blindly favored whichever response was shown first)
    biased_payload = {
        "overall_winner": "A",
        "accuracy_winner": "A",
        "citation_winner": "A",
        "synthesis_winner": "A",
        "score_a": 4.6,
        "score_b": 4.2,
        "win_margin": 0.4,
        "position_bias_checked": True,
        "reasoning": "First option looks good.",
    }
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(biased_payload)
    mock_client.models.generate_content.side_effect = [mock_resp, mock_resp]

    judgment = evaluate_pairwise_responses(
        query="Compare MacBook Air and XPS 13",
        matrix=sample_matrix,
        response_a="Response A [SKU: 6534606]",
        response_b="Response B [SKU: 6543210]",
        client=mock_client,
        check_position_bias=True,
    )

    assert judgment.overall_winner == "TIE"
    assert judgment.position_bias_checked is True
    assert "Position bias detected" in judgment.reasoning


def test_evaluate_pairwise_batch_aggregation(sample_matrix: list[MatrixRow]) -> None:
    """Verify batch pairwise tournament aggregation computes accurate win/tie rates."""
    pairs = [
        {
            "query": "Compare MacBook Air M3 and Dell XPS 13",
            "matrix": sample_matrix,
            "response_a": (
                "MacBook Air M3 [SKU: 6534606] is $1,099.00 with 18.0 hours battery, while "
                "Dell XPS 13 [SKU: 6543210] is $1,299.00 with 32 GB RAM. Recommendation: "
                "Buy [SKU: 6534606] for battery or [SKU: 6543210] for heavy RAM workloads."
            ),
            "response_b": "Dell XPS 13 is cheaper than [SKU: 6534606].",
        },
        {
            "query": "Compare MacBook Air M3 and Dell XPS 13 portability",
            "matrix": sample_matrix,
            "response_a": (
                "Both [SKU: 6534606] ($1,099.00, 18.0 hours) and [SKU: 6543210] ($1,299.00, 32 GB) "
                "are ultraportables. Recommendation: [SKU: 6534606] wins value and battery."
            ),
            "response_b": "Check out laptops in the catalog.",
        },
    ]

    summary = evaluate_pairwise_batch(
        model_a="tiered-hybrid",
        model_b="gemini-1.5-flash",
        pairs=pairs,
        client=None,
        use_live_client=False,
    )

    assert isinstance(summary, PairwiseBatchSummary)
    assert summary.model_a == "tiered-hybrid"
    assert summary.model_b == "gemini-1.5-flash"
    assert summary.total_pairs == 2
    assert summary.wins_a == 2
    assert summary.wins_b == 0
    assert summary.win_rate_a == 1.0
    assert summary.overall_winner == "A"


def test_compute_composite_score_and_sla_disqualification() -> None:
    """Verify SLA gate evaluation and composite score ranking across candidate models."""
    weights = DecisionWeights()

    # 1. Tiered Hybrid (passes all SLAs)
    hybrid = evaluate_candidate_profile(
        model_id="tiered-hybrid",
        display_name="Tiered Hybrid (3.5 Flash Intent + 2.5 Pro Synthesis)",
        routing_strategy="two-tier-adaptive",
        turn1_model="gemini-3.5-flash",
        turn2_model="gemini-2.5-pro",
        data_accuracy=0.995,
        citation_faithfulness=0.988,
        schema_validity=1.00,
        latency_p50_seconds=1.18,
        latency_p95_seconds=2.18,
        cost_per_1k_queries_usd=0.85,
        avg_prompt_tokens=1180,
        avg_output_tokens=590,
        synthesis_quality_score=4.84,
        pairwise_win_rate_vs_baseline=0.925,
        weights=weights,
    )
    assert hybrid.sla_compliant is True
    assert hybrid.passes_latency_sla is True
    assert hybrid.passes_accuracy_gate is True

    # 2. Pure Gemini 2.5 Pro (violates P95 <= 3.0s latency SLA)
    pro_only = evaluate_candidate_profile(
        model_id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro (Single-Tier End-to-End)",
        routing_strategy="single-tier-pro",
        turn1_model="gemini-2.5-pro",
        turn2_model="gemini-2.5-pro",
        data_accuracy=0.996,
        citation_faithfulness=0.991,
        schema_validity=1.00,
        latency_p50_seconds=1.95,
        latency_p95_seconds=3.48,
        cost_per_1k_queries_usd=2.45,
        avg_prompt_tokens=1240,
        avg_output_tokens=640,
        synthesis_quality_score=4.88,
        pairwise_win_rate_vs_baseline=0.950,
        weights=weights,
    )
    assert pro_only.sla_compliant is False
    assert pro_only.passes_latency_sla is False
    assert pro_only.verdict == "SLA_VIOLATION_LATENCY"
    assert hybrid.composite_score > pro_only.composite_score


def test_build_model_decision_matrix_and_markdown_rendering(tmp_path: Path) -> None:
    """Verify end-to-end model decision matrix generation and Markdown scorecard output."""
    json_out = tmp_path / "model_decision_matrix.json"
    md_out = tmp_path / "model_decision_scorecard.md"

    report = build_model_decision_matrix(
        output_json_path=json_out,
        output_md_path=md_out,
    )

    assert isinstance(report, ModelDecisionMatrixReport)
    assert report.selected_winner == "tiered-hybrid"
    assert len(report.candidates) == 4
    assert len(report.pairwise_tournaments) >= 3
    assert json_out.exists()
    assert md_out.exists()

    md_text = md_out.read_text(encoding="utf-8")
    assert "# Empirical Foundation Model Decision Scorecard" in md_text
    assert "tiered-hybrid" in md_text
    assert "gemini-2.5-pro" in md_text
    assert "gemini-2.5-flash" in md_text
    assert "gemini-1.5-flash" in md_text
    assert "ADR-004" in md_text


def test_adr_004_and_evals_agents_documentation_synchronized() -> None:
    """Verify ARCHITECTURE.md (ADR-004) and evals/AGENTS.md document the empirical model decision matrix."""
    arch_text = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    evals_agents_text = (REPO_ROOT / "evals" / "AGENTS.md").read_text(encoding="utf-8")

    assert "ADR-004" in arch_text
    assert "generate_model_matrix.py" in arch_text
    assert "pairwise_judge.py" in arch_text
    assert "tiered-hybrid" in arch_text

    assert "generate_model_matrix.py" in evals_agents_text
    assert "pairwise_judge.py" in evals_agents_text


def test_evaluate_pairwise_batch_empty_pairs() -> None:
    """Verify evaluate_pairwise_batch handles empty pairs gracefully."""
    summary = evaluate_pairwise_batch(
        model_a="model-a",
        model_b="model-b",
        pairs=[],
    )
    assert isinstance(summary, PairwiseBatchSummary)
    assert summary.total_pairs == 0
    assert summary.overall_winner == "TIE"


def test_pairwise_judge_cli_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify CLI entrypoint of pairwise_judge runs and prints JSON."""
    import sys
    from evals import pairwise_judge

    monkeypatch.setattr(sys, "argv", ["pairwise_judge"])
    pairwise_judge.main()
    captured = capsys.readouterr()
    assert "overall_winner" in captured.out
    assert "score_a" in captured.out


def test_generate_model_matrix_cli_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify CLI entrypoint of generate_model_matrix writes files and prints scorecard."""
    import sys
    from evals import generate_model_matrix

    json_path = tmp_path / "cli_matrix.json"
    md_path = tmp_path / "cli_scorecard.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_model_matrix",
            "--output-json",
            str(json_path),
            "--output-md",
            str(md_path),
        ],
    )
    generate_model_matrix.main()
    captured = capsys.readouterr()
    assert "# Empirical Foundation Model Decision Scorecard" in captured.out
    assert json_path.exists()
    assert md_path.exists()
