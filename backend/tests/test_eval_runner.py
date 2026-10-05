"""Unit tests for evals.runner evaluation harness."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from evals.runner import (
    compute_citation_faithfulness,
    compute_spec_accuracy,
    evaluate_semantic_coherence,
    export_evaluation_to_bigquery,
    normalize_value,
    run_benchmark,
)

from app.models.responses import Citation, CompareResponse, MatrixRow, ProductSpec


def _build_mock_orchestrator_for_dataset(dataset_path: Path, catalog_path: Path) -> MagicMock:
    """Create a unittest.mock orchestrator that returns grounded CompareResponses for dataset cases."""
    raw_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = raw_data.get("eval_cases", raw_data) if isinstance(raw_data, dict) else raw_data
    catalog_items = {
        item["sku"]: item for item in json.loads(catalog_path.read_text(encoding="utf-8"))
    }
    case_by_query = {}
    for c in cases:
        q = c.get("query") or c["conversation"][0]["user_content"]["parts"][0]["text"]
        case_by_query[q] = c

    def _fake_compare(query: str, category: str | None = None, **kwargs) -> CompareResponse:
        case = case_by_query.get(query, cases[0])
        skus = case.get("expected_skus", [])
        gt = case.get("ground_truth_specs", {})
        prods = []
        for sku in skus:
            cat_item = dict(
                catalog_items.get(
                    sku,
                    {
                        "sku": sku,
                        "name": f"Product {sku}",
                        "brand": "Brand",
                        "category": category or "Laptops",
                        "price": 999.0,
                        "specifications": {},
                    },
                )
            )
            if sku in gt:
                specs = dict(cat_item.get("specifications", {}))
                for k, v in gt[sku].items():
                    if k in ("name", "brand", "category", "price", "rating"):
                        cat_item[k] = v
                    else:
                        specs[k] = v
                cat_item["specifications"] = specs
            prods.append(ProductSpec(**cat_item))
        citations_str = " vs ".join(f"{p.name} [SKU: {p.sku}] (${p.price:,.2f})" for p in prods)
        return CompareResponse(
            summary=f"Grounded comparison of {citations_str}.",
            products=prods,
            comparison_matrix=[
                MatrixRow(
                    feature="Price",
                    values={p.sku: f"${p.price:,.2f}" for p in prods},
                    winner_sku=min(prods, key=lambda x: x.price).sku if prods else None,
                )
            ],
            citations=[
                Citation(sku=p.sku, url=p.url or f"https://techbuy.com/{p.sku}") for p in prods
            ],
            recommendations=f"Recommended: {prods[0].name} [SKU: {prods[0].sku}]."
            if prods
            else None,
        )

    mock_orch = MagicMock()
    mock_orch.compare.side_effect = _fake_compare
    mock_orch.execute_with_adk_runner.side_effect = _fake_compare
    return mock_orch


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
            Citation(sku="6534606", url="https://techbuy.com/6534606"),
            Citation(sku="6575132", url="https://techbuy.com/6575132"),
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
    mock_orch = _build_mock_orchestrator_for_dataset(dataset_path, catalog_path)

    report = run_benchmark(
        dataset_path=dataset_path,
        catalog_path=catalog_path,
        category="Headphones",
        limit=3,
        live=False,
        orchestrator=mock_orch,
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


def test_run_benchmark_excludes_tool_trajectory_metrics():
    """Verify run_benchmark omits tool trajectory metrics since Node 2 is a deterministic SQL step."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    dataset_path = repo_root / "evals" / "dataset" / "fixtures" / "simple_test.evalset.json"
    catalog_path = repo_root / "backend" / "src" / "app" / "data" / "catalog_seed.json"
    mock_orch = _build_mock_orchestrator_for_dataset(dataset_path, catalog_path)

    report = run_benchmark(
        dataset_path=dataset_path,
        catalog_path=catalog_path,
        live=False,
        orchestrator=mock_orch,
    )

    summary = report["summary"]
    assert "mean_tool_trajectory_score" not in summary
    assert "adk_tool_trajectory_score" not in summary
    assert "target_trajectory" not in summary.get("targets", {})

    details = report["details"]
    assert len(details) == 1
    assert "tool_trajectory_score" not in details[0]
    assert "tool_trajectory_passed" not in details[0]
    assert "tool_trajectory_match_type" not in details[0]
    assert "trajectory_diagnosis" not in details[0]

    for cat_data in report.get("category_metrics", {}).values():
        assert "mean_tool_trajectory_score" not in cat_data


def test_runner_main_cli(tmp_path, monkeypatch):
    """Verify runner.main CLI executes without --target-trajectory and saves report."""
    import evals.runner as runner_mod
    from evals.runner import main as runner_main

    repo_root = Path(__file__).resolve().parent.parent.parent
    dataset_path = repo_root / "evals" / "dataset" / "fixtures" / "simple_test.evalset.json"
    catalog_path = repo_root / "backend" / "src" / "app" / "data" / "catalog_seed.json"
    out_path = tmp_path / "eval_out.json"
    mock_orch = _build_mock_orchestrator_for_dataset(dataset_path, catalog_path)
    monkeypatch.setattr(runner_mod, "ComparisonOrchestrator", lambda **kw: mock_orch)

    monkeypatch.setattr(
        "sys.argv",
        [
            "evals.runner",
            "--dataset",
            str(dataset_path),
            "--catalog",
            str(catalog_path),
            "--output",
            str(out_path),
        ],
    )
    runner_main()
    assert out_path.exists()
