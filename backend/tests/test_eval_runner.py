"""Unit tests for evals.runner evaluation harness."""

from pathlib import Path

import pytest
from evals.runner import (
    compute_citation_faithfulness,
    compute_spec_accuracy,
    create_hermetic_bq_client,
    evaluate_semantic_coherence,
    export_evaluation_to_bigquery,
    normalize_value,
    run_benchmark,
)

from app.models.responses import Citation, CompareResponse, ProductSpec


def test_normalize_value():
    """Verify normalization of specs, units, and numbers."""
    assert normalize_value(None) == ""
    assert normalize_value(16) == 16.0
    assert normalize_value("16 GB") == 16.0
    assert normalize_value("512GB") == 512.0
    assert normalize_value("$1,099.00") == 1099.0
    assert normalize_value("Up to 18.0 hours") == 18.0
    assert normalize_value("Apple M3 8-core") == "apple m3 8-core"


def test_compute_spec_accuracy():
    """Verify spec accuracy calculation with exact matches and discrepancies."""
    p1 = ProductSpec(
        sku="123",
        name="Laptop A",
        brand="BrandA",
        price=1000.0,
        specifications={"processor": "Chip X", "ram_gb": 16, "battery_life_hours": 10.0},
    )
    p2 = ProductSpec(
        sku="456",
        name="Laptop B",
        brand="BrandB",
        price=1200.0,
        specifications={"processor": "Chip Y", "ram_gb": 16, "battery_life_hours": 12.0},
    )
    resp = CompareResponse(
        summary="Compare Laptop A and B",
        products=[p1, p2],
        comparison_matrix=[],
        citations=[Citation(sku="123", url="u1"), Citation(sku="456", url="u2")],
    )

    ground_truth = {
        "123": {"price": 1000.0, "processor": "Chip X", "ram_gb": 16},
        "456": {"price": 1200.0, "processor": "Chip Y", "ram_gb": 16},
    }

    acc, errs = compute_spec_accuracy(["123", "456"], ground_truth, resp)
    assert acc == 1.0
    assert len(errs) == 0

    # With discrepancy
    mismatched_gt = {
        "123": {"price": 900.0, "processor": "Chip Z"},
        "456": {"price": 1200.0, "processor": "Chip Y"},
    }
    acc_bad, errs_bad = compute_spec_accuracy(["123", "456"], mismatched_gt, resp)
    assert acc_bad < 1.0
    assert len(errs_bad) >= 1

    # Empty products
    empty_resp = CompareResponse(summary="None", products=[], comparison_matrix=[], citations=[])
    acc_empty, _ = compute_spec_accuracy(["123"], ground_truth, empty_resp)
    assert acc_empty == 0.0


def test_compute_citation_faithfulness():
    """Verify citation faithfulness scoring and hallucination detection."""
    p1 = ProductSpec(sku="6534606", name="Prod A", brand="BrandA", price=500.0)
    p2 = ProductSpec(sku="6575132", name="Prod B", brand="BrandB", price=600.0)

    # 1. Perfect citations
    resp_perfect = CompareResponse(
        summary="Comparison between Prod A [SKU: 6534606] and Prod B [SKU: 6575132].",
        products=[p1, p2],
        comparison_matrix=[],
        citations=[
            Citation(sku="6534606", url="https://bestbuy.com/6534606"),
            Citation(sku="6575132", url="https://bestbuy.com/6575132"),
        ],
        recommendations="Choose Prod A [SKU: 6534606] for best value.",
    )
    score, errs = compute_citation_faithfulness(["6534606", "6575132"], resp_perfect)
    assert score == 1.0
    assert len(errs) == 0

    # 2. Hallucinated SKU
    resp_hallucinated = CompareResponse(
        summary="Comparison with fake [SKU: 9999999].",
        products=[p1, p2],
        comparison_matrix=[],
        citations=[Citation(sku="6534606", url="u1")],
    )
    score_hal, errs_hal = compute_citation_faithfulness(["6534606", "6575132"], resp_hallucinated)
    assert score_hal < 0.5
    assert any("Hallucinated citations" in e for e in errs_hal)

    # 3. Missing citations list
    resp_no_cit = CompareResponse(
        summary="No citations.",
        products=[p1, p2],
        comparison_matrix=[],
        citations=[],
    )
    score_no_cit, _ = compute_citation_faithfulness(["6534606", "6575132"], resp_no_cit)
    assert score_no_cit == 0.0


def test_evaluate_semantic_coherence():
    """Verify semantic contradiction detection between summary and product prices."""
    p1 = ProductSpec(sku="1", name="Cheap Laptop", brand="A", price=500.0)
    p2 = ProductSpec(sku="2", name="Expensive Laptop", brand="B", price=1500.0)

    # Coherent summary
    resp_good = CompareResponse(
        summary="Cheap Laptop [SKU: 1] is cheaper than Expensive Laptop [SKU: 2].",
        products=[p1, p2],
        comparison_matrix=[],
        citations=[],
    )
    score_good, errs_good = evaluate_semantic_coherence(resp_good)
    assert score_good == 1.0
    assert len(errs_good) == 0

    # Contradictory summary (claiming expensive is cheaper)
    resp_bad = CompareResponse(
        summary="Expensive Laptop is cheaper and more affordable.",
        products=[p1, p2],
        comparison_matrix=[],
        citations=[],
    )
    score_bad, errs_bad = evaluate_semantic_coherence(resp_bad)
    assert score_bad < 1.0
    assert any("Contradiction" in e for e in errs_bad)


def test_create_hermetic_bq_client():
    """Verify hermetic mock BigQuery client query filtering."""
    catalog_path = (
        Path(__file__).resolve().parent.parent / "src" / "app" / "data" / "catalog_seed.json"
    )
    client = create_hermetic_bq_client(catalog_path)

    # Query with category
    from google.cloud import bigquery

    params = [
        bigquery.ArrayQueryParameter("product_patterns", "STRING", ["%macbook%"]),
        bigquery.ScalarQueryParameter("category", "STRING", "Laptops"),
    ]
    job_cfg = bigquery.QueryJobConfig(query_parameters=params)
    res = client.query("SELECT *", job_config=job_cfg).result()
    assert len(res) >= 1
    assert any("macbook" in r["name"].lower() for r in res)


def test_evaluate_semantic_coherence_live_with_judge(monkeypatch):
    """Verify live semantic coherence evaluation routes through evaluate_comparison_faithfulness."""
    from evals.judge import FaithfulnessResult

    p1 = ProductSpec(sku="1", name="Laptop A", brand="A", price=500.0)
    p2 = ProductSpec(sku="2", name="Laptop B", brand="B", price=1000.0)
    resp = CompareResponse(
        summary="Laptop A [SKU: 1] is cheaper than Laptop B [SKU: 2].",
        products=[p1, p2],
        comparison_matrix=[],
        citations=[],
    )

    mock_result = FaithfulnessResult(
        is_faithful=True,
        score=5,
        has_contradiction=False,
        reasoning="Faithful reflection of specs.",
    )

    import evals.judge

    monkeypatch.setattr(
        evals.judge, "evaluate_comparison_faithfulness", lambda **kwargs: mock_result
    )

    score, errs = evaluate_semantic_coherence(resp, query="Laptop A vs Laptop B", live=True)
    assert score == 1.0
    assert len(errs) == 0

    # Test failure case
    mock_bad_result = FaithfulnessResult(
        is_faithful=False,
        score=1,
        has_contradiction=True,
        reasoning="Inverted price winner.",
    )
    monkeypatch.setattr(
        evals.judge, "evaluate_comparison_faithfulness", lambda **kwargs: mock_bad_result
    )

    score_bad, errs_bad = evaluate_semantic_coherence(resp, query="Laptop A vs Laptop B", live=True)
    assert score_bad == 0.2
    assert any("Faithfulness issue" in e for e in errs_bad)


def test_run_benchmark_limit_and_category_filter():
    """Verify benchmark run with category filter and limit."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    dataset_path = repo_root / "evals" / "dataset" / "benchmark_catalog.evalset.json"
    catalog_path = repo_root / "backend" / "src" / "app" / "data" / "catalog_seed.json"

    report = run_benchmark(
        dataset_path=dataset_path,
        catalog_path=catalog_path,
        category="Headphones",
        limit=3,
    )

    assert report["metadata"]["total_cases"] == 3
    assert len(report["details"]) == 3
    for d in report["details"]:
        assert d["category"] == "Headphones"
    assert report["summary"]["target_threshold_met"] is True


def test_run_benchmark_missing_dataset_raises():
    """Verify FileNotFoundError when dataset path does not exist."""
    fake_path = Path("/nonexistent/benchmark.json")
    with pytest.raises(FileNotFoundError):
        run_benchmark(dataset_path=fake_path, catalog_path=Path("nonexistent.json"))


def test_export_evaluation_to_bigquery_success():
    """Verify export_evaluation_to_bigquery formats row and calls BigQuery insert_rows_json."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = []  # Empty list indicates no errors

    sample_report = {
        "metadata": {
            "timestamp": "2026-09-17T02:00:00Z",
            "total_cases": 80,
            "passed_cases": 78,
            "failed_cases": 2,
        },
        "summary": {
            "mean_data_accuracy": 0.99,
            "mean_citation_faithfulness": 0.97,
            "mean_semantic_score": 0.98,
            "latency_p50_seconds": 1.5,
            "latency_p95_seconds": 2.8,
            "target_threshold_met": True,
        },
        "details": [
            {"id": "c1", "query": "q1", "status": "PASS"},
            {"id": "c2", "query": "q2", "status": "FAIL", "errors": ["Spec mismatch"]},
        ],
    }

    success = export_evaluation_to_bigquery(
        sample_report,
        project_id="test-project",
        dataset_id="test-telemetry",
        table_id="evaluation_runs",
        trigger_source="cloud_scheduler",
        bq_client=mock_client,
    )

    assert success is True
    mock_client.insert_rows_json.assert_called_once()
    call_args = mock_client.insert_rows_json.call_args
    table_ref, rows = call_args[0]
    assert table_ref == "test-project.test-telemetry.evaluation_runs"
    assert len(rows) == 1
    row = rows[0]
    assert row["total_cases"] == 80
    assert row["passed_cases"] == 78
    assert row["avg_spec_accuracy"] == 0.99
    assert row["avg_citation_faithfulness"] == 0.97
    assert row["target_threshold_met"] is True
    assert row["status"] == "PASS"
    assert row["trigger_source"] == "cloud_scheduler"
    assert row["failure_count"] == 1


def test_export_evaluation_to_bigquery_handles_errors():
    """Verify export_evaluation_to_bigquery handles BigQuery insertion errors gracefully."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = [{"index": 0, "errors": ["Access denied"]}]

    sample_report = {
        "metadata": {"timestamp": "2026-09-17T02:00:00Z"},
        "summary": {"target_threshold_met": False},
        "details": [],
    }

    success = export_evaluation_to_bigquery(
        sample_report,
        project_id="test-project",
        dataset_id="test-telemetry",
        bq_client=mock_client,
    )
    assert success is False

    # Also test exception handling
    mock_client.insert_rows_json.side_effect = RuntimeError("Connection timeout")
    success_exc = export_evaluation_to_bigquery(
        sample_report,
        project_id="test-project",
        dataset_id="test-telemetry",
        bq_client=mock_client,
    )
    assert success_exc is False


def test_run_benchmark_computes_tool_trajectory():
    """Verify run_benchmark records and grades tool trajectories."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    dataset_path = repo_root / "evals" / "dataset" / "fixtures" / "simple_test.evalset.json"
    catalog_path = repo_root / "backend" / "src" / "app" / "data" / "catalog_seed.json"

    report = run_benchmark(
        dataset_path=dataset_path,
        catalog_path=catalog_path,
        target_trajectory=0.95,
    )

    summary = report["summary"]
    assert "mean_tool_trajectory_score" in summary
    assert "adk_tool_trajectory_score" in summary
    assert summary["mean_tool_trajectory_score"] == 1.0
    assert summary["adk_tool_trajectory_score"] == 1.0

    details = report["details"]
    assert len(details) == 1
    assert details[0]["tool_trajectory_score"] == 1.0
    assert details[0]["tool_trajectory_passed"] is True
    assert details[0]["tool_trajectory_match_type"] == "FUZZY_SEMANTIC"
