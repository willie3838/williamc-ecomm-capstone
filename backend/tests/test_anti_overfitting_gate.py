"""Unit tests for the Counterfactual Anti-Overfitting Gate."""

import json
from pathlib import Path

from evals.anti_overfitting_gate import (
    AntiOverfittingConfig,
    AntiOverfittingGate,
    AntiOverfittingResult,
    compute_generalization_gap,
    evaluate_counterfactual_fidelity,
    evaluate_negative_chatter_robustness,
)

from app.models.responses import CompareResponse, ProductSpec


def test_compute_generalization_gap():
    """Verify calculation of generalization gap between benchmark and holdout scores."""
    # When benchmark and holdout are identical, gap is 0
    gap_acc, gap_cit = compute_generalization_gap(
        benchmark_acc=0.98,
        holdout_acc=0.98,
        benchmark_cit=0.96,
        holdout_cit=0.96,
    )
    assert gap_acc == 0.0
    assert gap_cit == 0.0

    # When benchmark is higher than holdout, gap is positive difference
    gap_acc, gap_cit = compute_generalization_gap(
        benchmark_acc=0.99,
        holdout_acc=0.91,
        benchmark_cit=0.95,
        holdout_cit=0.88,
    )
    assert round(gap_acc, 4) == 0.08
    assert round(gap_cit, 4) == 0.07

    # When holdout is higher than benchmark, gap is 0.0 (no overfitting)
    gap_acc, gap_cit = compute_generalization_gap(
        benchmark_acc=0.95,
        holdout_acc=0.98,
        benchmark_cit=0.92,
        holdout_cit=0.95,
    )
    assert gap_acc == 0.0
    assert gap_cit == 0.0


def test_gate_passes_healthy_run():
    """Verify that gate passes when holdout metrics are within acceptable generalization bounds."""
    config = AntiOverfittingConfig(
        max_generalization_gap=0.05,
        min_holdout_accuracy=0.95,
        min_holdout_citation=0.90,
        min_counterfactual_fidelity=0.95,
    )
    gate = AntiOverfittingGate(config=config)

    result = gate.evaluate_metrics(
        benchmark_summary={
            "mean_data_accuracy": 0.99,
            "mean_citation_faithfulness": 0.97,
            "latency_p95_seconds": 0.05,
        },
        holdout_summary={
            "mean_data_accuracy": 0.97,  # gap is 0.02 <= 0.05
            "mean_citation_faithfulness": 0.95,  # gap is 0.02 <= 0.05
            "latency_p95_seconds": 0.06,
        },
        counterfactual_fidelity=0.98,
        negative_suppression_rate=1.0,
    )

    assert result.gate_passed is True
    assert result.accuracy_gap == 0.02
    assert result.citation_gap == 0.02
    assert not result.failure_reasons


def test_gate_detects_overfitting_regression():
    """Verify that gate fails when generalization gap exceeds max threshold."""
    config = AntiOverfittingConfig(
        max_generalization_gap=0.05,
        min_holdout_accuracy=0.90,
        min_holdout_citation=0.85,
    )
    gate = AntiOverfittingGate(config=config)

    result = gate.evaluate_metrics(
        benchmark_summary={
            "mean_data_accuracy": 0.99,
            "mean_citation_faithfulness": 0.98,
        },
        holdout_summary={
            "mean_data_accuracy": 0.91,  # gap is 0.08 > 0.05 -> OVERFITTING
            "mean_citation_faithfulness": 0.96,
        },
        counterfactual_fidelity=0.98,
        negative_suppression_rate=1.0,
    )

    assert result.gate_passed is False
    assert any("Accuracy generalization gap" in r for r in result.failure_reasons)


def test_gate_fails_when_holdout_accuracy_below_floor():
    """Verify that gate fails when holdout accuracy drops below absolute minimum floor."""
    config = AntiOverfittingConfig(
        max_generalization_gap=0.10,
        min_holdout_accuracy=0.95,
    )
    gate = AntiOverfittingGate(config=config)

    result = gate.evaluate_metrics(
        benchmark_summary={
            "mean_data_accuracy": 0.95,
            "mean_citation_faithfulness": 0.95,
        },
        holdout_summary={
            "mean_data_accuracy": 0.92,  # gap is 0.03 <= 0.10, but 0.92 < 0.95 floor
            "mean_citation_faithfulness": 0.94,
        },
        counterfactual_fidelity=0.98,
        negative_suppression_rate=1.0,
    )

    assert result.gate_passed is False
    assert any("Holdout data accuracy" in r for r in result.failure_reasons)


def test_evaluate_counterfactual_fidelity():
    """Verify counterfactual spec fidelity check scores perturbed catalog specs correctly."""
    # When agent returns perturbed specs that match the counterfactual ground truth
    cf_case = {
        "eval_id": "cf-laptop-001",
        "expected_skus": ["6534606"],
        "ground_truth_specs": {
            "6534606": {
                "price": 849.0,  # Counterfactual promo price (standard is 1099.0)
                "ram_gb": 32,  # Counterfactual RAM upgrade (standard is 16)
            }
        },
    }

    # Agent correctly grounded in tool output:
    grounded_prod = ProductSpec(
        sku="6534606",
        name="Apple MacBook Air 13 M3 Custom",
        brand="Apple",
        category="Laptops",
        price=849.0,
        specifications={"ram_gb": 32},
    )
    resp_pass = CompareResponse(
        products=[grounded_prod],
        summary="Apple MacBook Air 13 [SKU: 6534606] priced at $849 with 32GB RAM.",
    )

    score_pass, errs_pass = evaluate_counterfactual_fidelity(cf_case, resp_pass)
    assert score_pass == 1.0
    assert not errs_pass

    # Agent suffered from parametric leakage (used pre-trained prices/specs):
    leaked_prod = ProductSpec(
        sku="6534606",
        name="Apple MacBook Air 13 M3 Standard",
        brand="Apple",
        category="Laptops",
        price=1099.0,  # Leaked standard price!
        specifications={"ram_gb": 16},  # Leaked standard RAM!
    )
    resp_fail = CompareResponse(
        products=[leaked_prod],
        summary="Apple MacBook Air 13 [SKU: 6534606] priced at $1099 with 16GB RAM.",
    )

    score_fail, errs_fail = evaluate_counterfactual_fidelity(cf_case, resp_fail)
    assert score_fail == 0.0
    assert len(errs_fail) >= 1


def test_evaluate_negative_chatter_robustness():
    """Verify negative chatter cases pass when zero products/SKUs are hallucinated."""
    # Proper refusal / guidance on rant without hallucinated products
    proper_response = CompareResponse(
        products=[],
        citations=[],
        summary="I am a comparison assistant for consumer electronics. For customer service or return policies, please visit techbuy.com/support.",
    )
    score, errs = evaluate_negative_chatter_robustness(proper_response)
    assert score == 1.0
    assert not errs

    # Hallucinated product or citation during negative query
    hallucinated_response = CompareResponse(
        products=[
            ProductSpec(
                sku="6534606",
                name="Apple MacBook Air",
                brand="Apple",
                category="Laptops",
                price=1099.0,
            )
        ],
        citations=[],
        summary="Here is a MacBook Air [SKU: 6534606] comparison.",
    )
    score_hallucinated, errs_hallucinated = evaluate_negative_chatter_robustness(
        hallucinated_response
    )
    assert score_hallucinated == 0.0
    assert len(errs_hallucinated) >= 1


def test_gate_save_and_load_report(tmp_path: Path):
    """Verify gate generates structured report file and serializes properly."""
    config = AntiOverfittingConfig(max_generalization_gap=0.05)
    gate = AntiOverfittingGate(config=config)

    result = AntiOverfittingResult(
        timestamp="2026-09-18T20:00:00Z",
        gate_passed=True,
        benchmark_metrics={"mean_data_accuracy": 0.99, "mean_citation_faithfulness": 0.98},
        holdout_metrics={"mean_data_accuracy": 0.97, "mean_citation_faithfulness": 0.96},
        accuracy_gap=0.02,
        citation_gap=0.02,
        counterfactual_fidelity=1.0,
        negative_chatter_suppression=1.0,
        failure_reasons=[],
    )

    report_file = tmp_path / "anti_overfitting_report.json"
    gate.save_report(result, report_file)
    assert report_file.exists()

    with open(report_file, encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["gate_passed"] is True
    assert loaded["accuracy_gap"] == 0.02
