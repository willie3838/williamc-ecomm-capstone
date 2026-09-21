"""Unit tests for ADK Dynamic Model Swappability and Vertex AI Experiments Benchmark Harness."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.agent.multi_agent import MultiAgentCoordinator
from app.agent.orchestrator import (
    ComparisonOrchestrator,
    create_adk_agent,
    resolve_model_pair,
)
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _build_mock_bq_client_with_two_laptops() -> MagicMock:
    sample_products = [
        {
            "sku": "6534606",
            "name": 'Apple MacBook Air 13.6" - M3 - 16GB RAM - 512GB SSD',
            "brand": "Apple",
            "category": "Laptops",
            "price": 1099.0,
            "rating": 4.8,
            "review_count": 520,
            "specifications": json.dumps(
                {
                    "processor": "Apple M3 8-core",
                    "ram_gb": 16,
                    "storage_gb": 512,
                    "battery_life_hours": 18.0,
                    "weight_lbs": 2.7,
                }
            ),
            "url": "https://www.techbuy.com/site/sku/6534606.p",
            "in_stock": True,
        },
        {
            "sku": "6575132",
            "name": 'Dell XPS 13" - Intel Core Ultra 7 - 16GB RAM - 512GB SSD',
            "brand": "Dell",
            "category": "Laptops",
            "price": 1199.0,
            "rating": 4.5,
            "review_count": 210,
            "specifications": json.dumps(
                {
                    "processor": "Intel Core Ultra 7 155H",
                    "ram_gb": 16,
                    "storage_gb": 512,
                    "battery_life_hours": 14.0,
                    "weight_lbs": 2.6,
                }
            ),
            "url": "https://www.techbuy.com/site/sku/6575132.p",
            "in_stock": True,
        },
    ]
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = sample_products
    mock_client.query.return_value = mock_job
    return mock_client


def test_resolve_model_pair_variants() -> None:
    """Verify resolve_model_pair handles single models, explicit pairs, and tiered-hybrid."""
    # 1. Default single model
    routing, synthesis, is_hybrid = resolve_model_pair("gemini-2.5-flash", None)
    assert routing == "gemini-2.5-flash"
    assert synthesis == "gemini-2.5-flash"
    assert is_hybrid is False

    # 2. Explicit dual-model injection
    routing, synthesis, is_hybrid = resolve_model_pair("gemini-2.5-flash", "gemini-2.5-pro")
    assert routing == "gemini-2.5-flash"
    assert synthesis == "gemini-2.5-pro"
    assert is_hybrid is True

    # 3. Tiered-hybrid shorthand profile
    routing, synthesis, is_hybrid = resolve_model_pair("tiered-hybrid", None)
    assert routing == "gemini-2.5-flash"
    assert synthesis == "gemini-2.5-pro"
    assert is_hybrid is True

    # 4. Tiered-hybrid with custom synthesis override
    routing, synthesis, is_hybrid = resolve_model_pair("tiered-hybrid", "gemini-1.5-pro")
    assert routing == "gemini-2.5-flash"
    assert synthesis == "gemini-1.5-pro"
    assert is_hybrid is True


def test_create_adk_agent_dynamic_model() -> None:
    """Verify create_adk_agent instantiates an ADK Agent with the injected model."""
    agent_flash = create_adk_agent(model="gemini-2.5-flash")
    assert agent_flash.model == "gemini-2.5-flash"

    agent_hybrid = create_adk_agent(model="tiered-hybrid")
    assert agent_hybrid.model == "gemini-2.5-pro"


def test_orchestrator_dynamic_model_and_synthesis_model_injection() -> None:
    """Verify ComparisonOrchestrator supports constructor and runtime model & synthesis_model injection."""
    mock_bq = _build_mock_bq_client_with_two_laptops()

    # 1. Constructor injection of tiered-hybrid
    orchestrator = ComparisonOrchestrator(
        bq_client=mock_bq,
        model="tiered-hybrid",
        hermetic=True,
    )
    assert orchestrator.configured_model_id == "tiered-hybrid"
    assert orchestrator.model == "gemini-2.5-flash"
    assert orchestrator.synthesis_model == "gemini-2.5-pro"
    assert orchestrator.is_tiered_hybrid is True

    resp = orchestrator.compare("Compare MacBook Air M3 and Dell XPS 13", category="Laptops")
    assert resp.synthesis_model == "gemini-2.5-pro"
    assert "tiered-hybrid" in (resp.model_version or "")
    assert len(resp.products) == 2

    # 2. Runtime override in compare()
    resp_override = orchestrator.compare(
        "Compare MacBook Air M3 and Dell XPS 13",
        category="Laptops",
        model="gemini-1.5-flash",
        synthesis_model="gemini-2.5-flash",
    )
    assert resp_override.synthesis_model == "gemini-2.5-flash"
    assert "gemini-1.5-flash" in (resp_override.model_version or "")


def test_multi_agent_coordinator_dynamic_model_swapping() -> None:
    """Verify MultiAgentCoordinator propagates model and synthesis_model across specialist agents."""
    mock_bq = _build_mock_bq_client_with_two_laptops()
    coordinator = MultiAgentCoordinator(
        bq_client=mock_bq,
        model="gemini-2.5-flash",
        synthesis_model="gemini-2.5-pro",
    )
    assert coordinator.intent_agent.model == "gemini-2.5-flash"
    assert coordinator.retrieval_agent.model == "gemini-2.5-flash"
    assert coordinator.relevance_agent.model == "gemini-2.5-flash"
    assert coordinator.comparison_agent.synthesis_model == "gemini-2.5-pro"

    result = coordinator.execute("Compare MacBook Air M3 and Dell XPS 13", category="Laptops")
    assert len(result.products) == 2
    assert result.synthesis_model == "gemini-2.5-pro"


def test_api_dynamic_model_swapping() -> None:
    """Verify /api/compare model and synthesis_model overrides."""
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/compare",
        json={
            "query": "Compare Apple MacBook Air M3 and Dell XPS 13",
            "model": "gemini-2.5-flash",
            "synthesis_model": "gemini-2.5-pro",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["synthesis_model"] == "gemini-2.5-pro"
    assert "gemini-2.5-flash" in payload["model_version"]


def test_load_custom_rubrics() -> None:
    """Verify custom rubrics (data_accuracy.md and citation_faithfulness.md) are loaded and parsed."""
    from evals.benchmark_models import load_custom_rubrics

    rubrics_dir = REPO_ROOT / "evals" / "rubrics"
    rubrics = load_custom_rubrics(rubrics_dir)

    assert "data_accuracy" in rubrics
    assert "citation_faithfulness" in rubrics
    assert rubrics["data_accuracy"].target_score == 0.98
    assert rubrics["data_accuracy"].critical_threshold == 0.95
    assert rubrics["citation_faithfulness"].target_score == 0.95
    assert rubrics["citation_faithfulness"].critical_threshold == 0.90


def test_benchmark_models_and_vertex_experiments_logging(tmp_path: Path) -> None:
    """Verify benchmark_models evaluates all 4 candidate models and logs runs to Vertex AI Experiments."""
    from evals.benchmark_models import (
        CANDIDATE_MODELS,
        generate_benchmark_markdown,
        log_run_to_vertex_experiments,
        run_model_benchmarks,
    )

    candidate_ids = [c.model_id for c in CANDIDATE_MODELS]
    assert "gemini-2.5-flash" in candidate_ids
    assert "gemini-2.5-pro" in candidate_ids
    assert "gemini-1.5-flash" in candidate_ids
    assert "tiered-hybrid" in candidate_ids

    # Verify Vertex AI Experiments logging with mocked google.cloud.aiplatform
    mock_aiplatform = MagicMock()
    with patch.dict("sys.modules", {"google.cloud.aiplatform": mock_aiplatform}):
        log_result = log_run_to_vertex_experiments(
            experiment_name="catalog-model-benchmark-test",
            run_name="run-tiered-hybrid",
            params={"model_id": "tiered-hybrid", "routing_model": "gemini-2.5-flash"},
            metrics={"mean_data_accuracy": 1.0, "mean_citation_faithfulness": 1.0},
            project_id="fde-bestbuy-sandbox-dev-508321",
            location="us-central1",
            aiplatform_module=mock_aiplatform,
        )
        assert log_result["logged_to_vertex"] is True
        mock_aiplatform.init.assert_called_once()
        mock_aiplatform.start_run.assert_called_once_with("run-tiered-hybrid")
        mock_aiplatform.log_params.assert_called_once()
        mock_aiplatform.log_metrics.assert_called_once()
        mock_aiplatform.end_run.assert_called_once()

    # Run benchmark across all 4 candidates with limit=4 for fast unit test verification
    output_json = tmp_path / "model_benchmark_results.json"
    output_md = tmp_path / "model_benchmark_summary.md"
    report = run_model_benchmarks(
        dataset_path=REPO_ROOT / "evals" / "dataset" / "benchmark_catalog.evalset.json",
        catalog_path=REPO_ROOT / "backend" / "src" / "app" / "data" / "catalog_seed.json",
        rubrics_dir=REPO_ROOT / "evals" / "rubrics",
        limit=4,
        output_json_path=output_json,
        output_md_path=output_md,
        log_vertex=True,
        aiplatform_module=mock_aiplatform,
    )

    assert len(report["candidates"]) == len(CANDIDATE_MODELS)
    assert "recommended_model" in report
    assert "per_stage_benchmarks" in report
    assert output_json.exists()
    assert output_md.exists()

    md_text = generate_benchmark_markdown(report)
    assert "gemini-2.5-flash" in md_text
    assert "gemini-2.5-pro" in md_text
    assert "gemini-1.5-flash" in md_text
    assert "tiered-hybrid" in md_text
    assert "data_accuracy.md" in md_text
    assert "citation_faithfulness.md" in md_text


def test_vertex_run_name_sanitization_and_stratified_sampling() -> None:
    """Verify Vertex AI Experiment run IDs sanitize periods and stratified sampling covers all 5 categories."""
    from evals.benchmark_models import sanitize_vertex_run_name, select_stratified_cases

    assert (
        sanitize_vertex_run_name("run-gemini-2.5-flash-1750000000")
        == "run-gemini-2-5-flash-1750000000"
    )
    assert (
        sanitize_vertex_run_name("run-gemini-1.5-flash-1750000000")
        == "run-gemini-1-5-flash-1750000000"
    )

    sample_cases = [
        {"id": f"c_{cat}_{i}", "category": cat, "query": f"Compare {cat} {i}"}
        for cat in ["Laptops", "Tablets", "Headphones", "Smart Home", "TVs"]
        for i in range(4)
    ]
    stratified = select_stratified_cases(sample_cases, limit=10)
    assert len(stratified) == 10
    categories_selected = {c["category"] for c in stratified}
    assert categories_selected == {"Laptops", "Tablets", "Headphones", "Smart Home", "TVs"}
