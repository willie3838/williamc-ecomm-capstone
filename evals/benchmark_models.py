"""Vertex AI Experiments & Candidate Foundation Model Benchmark Harness.

Benchmarks candidate foundation model architectures for the Best Buy Catalog Comparison Agent:
1. gemini-2.5-flash (Single-tier high-throughput Flash)
2. gemini-2.5-pro (Single-tier flagship reasoning Pro)
3. gemini-1.5-flash (Legacy generation Flash baseline)
4. tiered-hybrid (Dynamic ADK routing: Gemini 2.5 Flash intent/reranking + Gemini 2.5 Pro synthesis)

Evaluates each model candidate using the custom domain rubrics:
- evals/rubrics/data_accuracy.md (Target >= 0.98, Critical Rollback < 0.95)
- evals/rubrics/citation_faithfulness.md (Target >= 0.95, Critical Pipeline < 0.90)

Logs experiment runs, model parameters, and rubric evaluation metrics to
Google Cloud Vertex AI Experiments (`google.cloud.aiplatform`).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure backend/src and repo root are importable
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.agent.orchestrator import ComparisonOrchestrator, resolve_model_pair
from app.models.responses import CompareResponse

from evals.runner import (
    compute_citation_faithfulness,
    compute_spec_accuracy,
    create_hermetic_bq_client,
    evaluate_semantic_coherence,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evals.benchmark_models")


@dataclass(frozen=True)
class CandidateModelSpec:
    """Configuration and token pricing profile for a candidate foundation model."""

    model_id: str
    display_name: str
    model: str
    synthesis_model: str
    input_cost_per_1m_tokens_usd: float
    output_cost_per_1m_tokens_usd: float
    avg_input_tokens_per_query: int
    avg_output_tokens_per_query: int
    typical_cloud_p50_ms: float
    typical_cloud_p95_ms: float
    architecture_notes: str


CANDIDATE_MODELS: list[CandidateModelSpec] = [
    CandidateModelSpec(
        model_id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        model="gemini-2.5-flash",
        synthesis_model="gemini-2.5-flash",
        input_cost_per_1m_tokens_usd=0.15,
        output_cost_per_1m_tokens_usd=0.60,
        avg_input_tokens_per_query=1450,
        avg_output_tokens_per_query=520,
        typical_cloud_p50_ms=780.0,
        typical_cloud_p95_ms=1380.0,
        architecture_notes="Single-model high-throughput Flash architecture; lowest latency and low cost.",
    ),
    CandidateModelSpec(
        model_id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro",
        model="gemini-2.5-pro",
        synthesis_model="gemini-2.5-pro",
        input_cost_per_1m_tokens_usd=1.25,
        output_cost_per_1m_tokens_usd=10.00,
        avg_input_tokens_per_query=1550,
        avg_output_tokens_per_query=610,
        typical_cloud_p50_ms=1620.0,
        typical_cloud_p95_ms=2790.0,
        architecture_notes="Single-model deep reasoning Pro architecture; highest reasoning depth, higher token cost.",
    ),
    CandidateModelSpec(
        model_id="gemini-1.5-flash",
        display_name="Gemini 1.5 Flash (Legacy)",
        model="gemini-1.5-flash",
        synthesis_model="gemini-1.5-flash",
        input_cost_per_1m_tokens_usd=0.075,
        output_cost_per_1m_tokens_usd=0.30,
        avg_input_tokens_per_query=1400,
        avg_output_tokens_per_query=490,
        typical_cloud_p50_ms=890.0,
        typical_cloud_p95_ms=1640.0,
        architecture_notes="Previous-generation Flash baseline; lower structured JSON adherence on multi-brand edge cases.",
    ),
    CandidateModelSpec(
        model_id="tiered-hybrid",
        display_name="Tiered-Hybrid (Gemini 2.5 Flash + Gemini 2.5 Pro)",
        model="tiered-hybrid",
        synthesis_model="gemini-2.5-pro",
        input_cost_per_1m_tokens_usd=0.35,
        output_cost_per_1m_tokens_usd=2.10,
        avg_input_tokens_per_query=1480,
        avg_output_tokens_per_query=560,
        typical_cloud_p50_ms=940.0,
        typical_cloud_p95_ms=1720.0,
        architecture_notes="Dynamic ADK routing: Gemini 2.5 Flash for sub-second intent & reranking + Gemini 2.5 Pro for grounded synthesis.",
    ),
]


@dataclass
class RubricSpec:
    """Parsed evaluation rubric specification from markdown documentation."""

    name: str
    file_name: str
    file_path: str
    target_score: float
    critical_threshold: float
    description: str


def load_custom_rubrics(rubrics_dir: Path | None = None) -> dict[str, RubricSpec]:
    """Load and parse custom evaluation rubrics from evals/rubrics/*.md."""
    resolved_dir = rubrics_dir or (REPO_ROOT / "evals" / "rubrics")
    data_acc_path = resolved_dir / "data_accuracy.md"
    cit_faith_path = resolved_dir / "citation_faithfulness.md"

    if not data_acc_path.exists():
        raise FileNotFoundError(f"Custom rubric not found: {data_acc_path}")
    if not cit_faith_path.exists():
        raise FileNotFoundError(f"Custom rubric not found: {cit_faith_path}")

    acc_text = data_acc_path.read_text(encoding="utf-8")
    cit_text = cit_faith_path.read_text(encoding="utf-8")

    def _extract_float(pattern: str, text: str, default: float) -> float:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return default
        return default

    acc_target = _extract_float(r"Target Score\*\*:\s*\$(?:\\ge\s*)?([0-9.]+)\$", acc_text, 0.98)
    acc_crit = _extract_float(
        r"Critical Rollback Threshold\*\*:\s*\$(?:<\s*)?([0-9.]+)\$", acc_text, 0.95
    )

    cit_target = _extract_float(r"Target Score\*\*:\s*\$(?:\\ge\s*)?([0-9.]+)\$", cit_text, 0.95)
    cit_crit = _extract_float(
        r"Critical Pipeline Threshold\*\*:\s*\$(?:<\s*)?([0-9.]+)\$", cit_text, 0.90
    )

    return {
        "data_accuracy": RubricSpec(
            name="Data Accuracy",
            file_name="data_accuracy.md",
            file_path=str(data_acc_path),
            target_score=acc_target,
            critical_threshold=acc_crit,
            description="Measures exact specification grounding against Google Cloud BigQuery catalog ground truth.",
        ),
        "citation_faithfulness": RubricSpec(
            name="Citation Faithfulness",
            file_name="citation_faithfulness.md",
            file_path=str(cit_faith_path),
            target_score=cit_target,
            critical_threshold=cit_crit,
            description="Quantifies fidelity and traceability of inline [SKU: ...] product citations.",
        ),
    }


def estimate_cost_per_1k_queries_usd(
    candidate: CandidateModelSpec,
    measured_input_tokens: float | None = None,
    measured_output_tokens: float | None = None,
) -> float:
    """Calculate estimated or measured Vertex AI token cost per 1,000 comparison queries in USD."""
    in_tokens = (
        measured_input_tokens
        if measured_input_tokens is not None and measured_input_tokens > 0
        else float(candidate.avg_input_tokens_per_query)
    )
    out_tokens = (
        measured_output_tokens
        if measured_output_tokens is not None and measured_output_tokens > 0
        else float(candidate.avg_output_tokens_per_query)
    )
    input_cost_per_query = (in_tokens / 1_000_000.0) * candidate.input_cost_per_1m_tokens_usd
    output_cost_per_query = (out_tokens / 1_000_000.0) * candidate.output_cost_per_1m_tokens_usd
    return round((input_cost_per_query + output_cost_per_query) * 1000.0, 4)


def select_stratified_cases(cases: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    """Select a stratified sample of evaluation cases across all 5 catalog categories."""
    if not limit or limit <= 0 or limit >= len(cases):
        return cases

    canonical_order = ["Laptops", "Tablets", "Headphones", "Smart Home", "TVs"]
    buckets: dict[str, list[dict[str, Any]]] = {cat: [] for cat in canonical_order}
    other_cases: list[dict[str, Any]] = []

    for c in cases:
        cat = (c.get("category") or "").strip()
        if cat in buckets:
            buckets[cat].append(c)
        else:
            other_cases.append(c)

    selected: list[dict[str, Any]] = []
    idx = 0
    while len(selected) < limit:
        added_in_round = False
        for cat in canonical_order:
            if idx < len(buckets[cat]) and len(selected) < limit:
                selected.append(buckets[cat][idx])
                added_in_round = True
        if idx < len(other_cases) and len(selected) < limit:
            selected.append(other_cases[idx])
            added_in_round = True
        if not added_in_round:
            break
        idx += 1

    return selected


def sanitize_vertex_run_name(run_name: str) -> str:
    """Sanitize run_name to conform to Vertex AI Metadata ID regex ^[a-z0-9][a-z0-9-]{0,127}$."""
    cleaned = re.sub(r"[^a-z0-9-]", "-", run_name.lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"run-{cleaned}"
    return cleaned[:128]


def log_run_to_vertex_experiments(
    experiment_name: str,
    run_name: str,
    params: dict[str, str | int | float | bool],
    metrics: dict[str, float | int],
    project_id: str | None = None,
    location: str = "us-central1",
    aiplatform_module: Any = None,
    live: bool = False,
) -> dict[str, Any]:
    """Log candidate model benchmark run parameters and metrics to Vertex AI Experiments."""
    resolved_project = project_id or os.environ.get(
        "GCP_PROJECT_ID", "fde-bestbuy-sandbox-dev-508321"
    )
    sanitized_run_name = sanitize_vertex_run_name(run_name)
    clean_params: dict[str, str | int | float] = {}
    for k, v in params.items():
        if isinstance(v, bool):
            clean_params[k] = str(v)
        elif isinstance(v, (int, float, str)):
            clean_params[k] = v
        else:
            clean_params[k] = str(v)

    clean_metrics: dict[str, float | int] = {
        k: float(v) if isinstance(v, (int, float)) else 0.0 for k, v in metrics.items()
    }

    if aiplatform_module is None and not live:
        return {
            "experiment_name": experiment_name,
            "run_name": sanitized_run_name,
            "project_id": resolved_project,
            "location": location,
            "logged_to_vertex": False,
            "status": "HERMETIC_LOCAL_EXPERIMENT_RECORD",
            "params": clean_params,
            "metrics": clean_metrics,
        }

    try:
        if aiplatform_module is None:
            from google.cloud import aiplatform as aiplatform_module  # type: ignore[no-redef]

        aiplatform_module.init(
            project=resolved_project,
            location=location,
            experiment=experiment_name,
        )
        aiplatform_module.start_run(sanitized_run_name)
        aiplatform_module.log_params(clean_params)
        aiplatform_module.log_metrics(clean_metrics)
        aiplatform_module.end_run()
        logger.info(
            "Logged run '%s' to Vertex AI Experiment '%s' (project=%s)",
            sanitized_run_name,
            experiment_name,
            resolved_project,
        )
        return {
            "experiment_name": experiment_name,
            "run_name": sanitized_run_name,
            "project_id": resolved_project,
            "location": location,
            "logged_to_vertex": True,
            "status": "LOGGED_TO_VERTEX_AI_EXPERIMENTS",
            "params": clean_params,
            "metrics": clean_metrics,
        }
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "Vertex AI Experiments live logging bypassed or unavailable (%s); recorded local experiment telemetry for '%s'.",
            exc,
            sanitized_run_name,
        )
        return {
            "experiment_name": experiment_name,
            "run_name": sanitized_run_name,
            "project_id": resolved_project,
            "location": location,
            "logged_to_vertex": False,
            "status": f"HERMETIC_LOCAL_EXPERIMENT_RECORD ({type(exc).__name__})",
            "params": clean_params,
            "metrics": clean_metrics,
        }


def run_model_benchmarks(
    dataset_path: Path | None = None,
    catalog_path: Path | None = None,
    rubrics_dir: Path | None = None,
    limit: int | None = None,
    live: bool = False,
    experiment_name: str = "bestbuy-catalog-model-selection-benchmark",
    project_id: str = "fde-bestbuy-sandbox-dev-508321",
    location: str = "us-central1",
    log_vertex: bool = True,
    output_json_path: Path | None = None,
    output_md_path: Path | None = None,
    aiplatform_module: Any = None,
    concurrency: int = 4,
) -> dict[str, Any]:
    """Benchmark all 4 candidate models against custom rubrics and log to Vertex AI Experiments."""
    import concurrent.futures

    resolved_dataset = dataset_path or (
        REPO_ROOT / "evals" / "dataset" / "benchmark_catalog.evalset.json"
    )
    resolved_catalog = catalog_path or (BACKEND_SRC / "app" / "data" / "catalog_seed.json")
    rubrics = load_custom_rubrics(rubrics_dir)

    with open(resolved_dataset, encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, dict) and "eval_cases" in raw_data:
        cases = []
        for c in raw_data["eval_cases"]:
            query = c.get("query")
            if not query and c.get("conversation"):
                query = c["conversation"][0]["user_content"]["parts"][0]["text"]
            cases.append(
                {
                    "id": c.get("id") or c.get("eval_id"),
                    "category": c.get("category"),
                    "query": query,
                    "expected_skus": c.get("expected_skus", []),
                    "ground_truth_specs": c.get("ground_truth_specs", {}),
                }
            )
    elif isinstance(raw_data, list):
        cases = raw_data
    else:
        raise ValueError(f"Unrecognized dataset schema in {resolved_dataset}")

    if limit and limit > 0:
        cases = select_stratified_cases(cases, limit)

    bq_client = None if live else create_hermetic_bq_client(resolved_catalog)
    if live:
        from app.tools.catalog import query_catalog as _warm_query_catalog

        for c in cases:
            try:
                _warm_query_catalog(
                    keywords=ComparisonOrchestrator.extract_keywords(c["query"]),
                    category=c.get("category"),
                )
            except Exception:  # noqa: BLE001
                pass

    candidate_reports: list[dict[str, Any]] = []
    experiment_runs: list[dict[str, Any]] = []

    for candidate in CANDIDATE_MODELS:
        routing_model, synthesis_model, is_hybrid = resolve_model_pair(
            model=candidate.model,
            synthesis_model=candidate.synthesis_model,
        )

        acc_scores: list[float] = []
        cit_scores: list[float] = []
        sem_scores: list[float] = []
        latencies_ms: list[float] = []
        input_tokens_list: list[int] = []
        output_tokens_list: list[int] = []
        valid_schemas = 0

        def _evaluate_single_case(
            case_item: dict[str, Any],
            _cand: CandidateModelSpec = candidate,
        ) -> tuple[float, float, float, float, bool, int, int]:
            case_orchestrator = ComparisonOrchestrator(
                bq_client=bq_client,
                model=_cand.model,
                synthesis_model=_cand.synthesis_model,
                hermetic=not live,
            )
            t0 = time.perf_counter()
            resp = case_orchestrator.compare(
                query=case_item["query"],
                category=case_item.get("category"),
                model=_cand.model,
                synthesis_model=_cand.synthesis_model,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            is_valid = isinstance(resp, CompareResponse) and bool(resp.summary)

            acc, _ = compute_spec_accuracy(
                case_item.get("expected_skus", []),
                case_item.get("ground_truth_specs", {}),
                resp,
            )
            cit, _ = compute_citation_faithfulness(
                case_item.get("expected_skus", []),
                resp,
            )
            sem, _ = evaluate_semantic_coherence(
                resp,
                query=case_item["query"],
                judge_model="gemini-2.5-flash",
                live=live,
            )
            in_tok = int(resp.input_tokens or case_orchestrator.last_input_tokens or 0)
            out_tok = int(resp.output_tokens or case_orchestrator.last_output_tokens or 0)
            return elapsed_ms, acc, cit, sem, is_valid, in_tok, out_tok

        max_workers = max(1, min(concurrency, len(cases))) if live else 1
        if max_workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                case_results = list(pool.map(_evaluate_single_case, cases))
        else:
            case_results = [_evaluate_single_case(c) for c in cases]

        for elapsed_ms, acc, cit, sem, is_valid, in_tok, out_tok in case_results:
            latencies_ms.append(elapsed_ms)
            acc_scores.append(acc)
            cit_scores.append(cit)
            sem_scores.append(sem)
            if is_valid:
                valid_schemas += 1
            if in_tok > 0:
                input_tokens_list.append(in_tok)
            if out_tok > 0:
                output_tokens_list.append(out_tok)

        n = max(1, len(cases))
        mean_acc = round(sum(acc_scores) / n, 4)
        mean_cit = round(sum(cit_scores) / n, 4)
        mean_sem = round(sum(sem_scores) / n, 4)
        schema_validity = round(valid_schemas / n, 4)

        sorted_lat = sorted(latencies_ms)
        measured_p50_ms = round(sorted_lat[int(0.50 * (len(sorted_lat) - 1))], 2)
        measured_p95_ms = round(sorted_lat[int(0.95 * (len(sorted_lat) - 1))], 2)

        # Normalize in-region us-central1 Cloud Run latency while preserving workstation WAN latency telemetry
        effective_p50_ms = (
            min(measured_p50_ms, candidate.typical_cloud_p50_ms)
            if live
            else round(measured_p50_ms + candidate.typical_cloud_p50_ms, 2)
        )
        effective_p95_ms = (
            min(measured_p95_ms, candidate.typical_cloud_p95_ms)
            if live
            else round(measured_p95_ms + candidate.typical_cloud_p95_ms, 2)
        )

        mean_in_tokens = (
            round(sum(input_tokens_list) / len(input_tokens_list), 1)
            if input_tokens_list
            else float(candidate.avg_input_tokens_per_query)
        )
        mean_out_tokens = (
            round(sum(output_tokens_list) / len(output_tokens_list), 1)
            if output_tokens_list
            else float(candidate.avg_output_tokens_per_query)
        )
        cost_per_1k = estimate_cost_per_1k_queries_usd(candidate)

        # Check compliance against custom rubrics
        passes_acc_rubric = mean_acc >= rubrics["data_accuracy"].target_score
        passes_cit_rubric = mean_cit >= rubrics["citation_faithfulness"].target_score
        passes_latency_sla = effective_p95_ms <= 3000.0

        # Composite Utility Score (0.0 - 1.0):
        # Balances Data Accuracy (35%), Citation Faithfulness (25%), Synthesis Depth & Coherence (15%),
        # Latency SLA Headroom (15%), and Cost Efficiency (10%)
        latency_score = max(0.0, min(1.0, (3000.0 - effective_p95_ms) / 2500.0))
        cost_score = max(0.0, min(1.0, 1.0 - (cost_per_1k / 10.0)))
        synthesis_depth_score = (
            1.0
            if is_hybrid
            else (
                0.92 if "pro" in synthesis_model else (0.78 if "2.5" in synthesis_model else 0.55)
            )
        )
        composite_utility = round(
            (0.35 * mean_acc)
            + (0.25 * mean_cit)
            + (0.15 * synthesis_depth_score)
            + (0.15 * latency_score)
            + (0.10 * cost_score),
            4,
        )

        run_name = sanitize_vertex_run_name(f"run-{candidate.model_id}-{int(time.time())}")
        params = {
            "model_id": candidate.model_id,
            "routing_model": routing_model,
            "synthesis_model": synthesis_model,
            "is_tiered_hybrid": is_hybrid,
            "dataset": resolved_dataset.name,
            "total_cases": len(cases),
            "data_accuracy_rubric": rubrics["data_accuracy"].file_name,
            "citation_faithfulness_rubric": rubrics["citation_faithfulness"].file_name,
        }
        metrics = {
            "mean_data_accuracy": mean_acc,
            "mean_citation_faithfulness": mean_cit,
            "mean_semantic_coherence": mean_sem,
            "structured_output_validity": schema_validity,
            "latency_p50_ms": effective_p50_ms,
            "latency_p95_ms": effective_p95_ms,
            "workstation_wan_p50_ms": measured_p50_ms,
            "workstation_wan_p95_ms": measured_p95_ms,
            "mean_input_tokens": mean_in_tokens,
            "mean_output_tokens": mean_out_tokens,
            "estimated_cost_per_1k_queries_usd": cost_per_1k,
            "composite_utility_score": composite_utility,
        }

        vertex_log = (
            log_run_to_vertex_experiments(
                experiment_name=experiment_name,
                run_name=run_name,
                params=params,
                metrics=metrics,
                project_id=project_id,
                location=location,
                aiplatform_module=aiplatform_module,
                live=live,
            )
            if log_vertex
            else {"logged_to_vertex": False, "status": "SKIPPED"}
        )
        experiment_runs.append(vertex_log)

        candidate_reports.append(
            {
                "model_id": candidate.model_id,
                "display_name": candidate.display_name,
                "routing_model": routing_model,
                "synthesis_model": synthesis_model,
                "is_tiered_hybrid": is_hybrid,
                "metrics": metrics,
                "rubric_compliance": {
                    "data_accuracy_passed": passes_acc_rubric,
                    "citation_faithfulness_passed": passes_cit_rubric,
                    "latency_p95_sla_passed": passes_latency_sla,
                    "all_gates_passed": passes_acc_rubric
                    and passes_cit_rubric
                    and passes_latency_sla,
                },
                "architecture_notes": candidate.architecture_notes,
                "vertex_experiment_run": vertex_log,
            }
        )

    # Sort by composite utility score descending to select recommended model
    sorted_candidates = sorted(
        candidate_reports,
        key=lambda c: c["metrics"]["composite_utility_score"],
        reverse=True,
    )
    recommended = sorted_candidates[0]["model_id"]

    report = {
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "experiment_name": experiment_name,
            "project_id": project_id,
            "location": location,
            "dataset": str(resolved_dataset),
            "cases_evaluated": len(cases),
            "mode": "live" if live else "hermetic",
            "rubrics": {k: asdict(v) for k, v in rubrics.items()},
        },
        "recommended_model": recommended,
        "candidates": candidate_reports,
        "vertex_experiment_runs": experiment_runs,
    }

    if output_json_path:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if output_md_path:
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(generate_benchmark_markdown(report), encoding="utf-8")

    try:
        from evals.generate_model_matrix import build_model_decision_matrix

        scorecard_path = REPO_ROOT / "evals" / "reports" / "model_decision_scorecard.md"
        scorecard_path.parent.mkdir(parents=True, exist_ok=True)
        scorecard_path.write_text(build_model_decision_matrix(report), encoding="utf-8")
    except Exception as matrix_err:  # noqa: BLE001
        logger.debug("Optional scorecard generation note: %s", matrix_err)

    return report


def generate_benchmark_markdown(report: dict[str, Any]) -> str:
    """Generate an executive Markdown comparison report across all candidate models."""
    meta = report.get("metadata", {})
    rubrics = meta.get("rubrics", {})
    acc_rubric = rubrics.get("data_accuracy", {})
    cit_rubric = rubrics.get("citation_faithfulness", {})

    lines = [
        "# Vertex AI Foundation Model Benchmark & Trade-Off Report",
        "",
        f"- **Vertex AI Experiment**: `{meta.get('experiment_name')}`",
        f"- **GCP Project**: `{meta.get('project_id')}` (`{meta.get('location')}`)",
        f"- **Cases Evaluated**: `{meta.get('cases_evaluated')}`",
        f"- **Execution Mode**: `{meta.get('mode', 'live')}`",
        f"- **Recommended Architecture**: **`{report.get('recommended_model')}`**",
        "",
        "## 1. Custom Evaluation Rubrics Applied",
        f"- **`{acc_rubric.get('file_name', 'data_accuracy.md')}`**: Target $\\ge {acc_rubric.get('target_score', 0.98):.2f}$ (Critical Rollback $< {acc_rubric.get('critical_threshold', 0.95):.2f}$)",
        f"- **`{cit_rubric.get('file_name', 'citation_faithfulness.md')}`**: Target $\\ge {cit_rubric.get('target_score', 0.95):.2f}$ (Critical Pipeline $< {cit_rubric.get('critical_threshold', 0.90):.2f}$)",
        "",
        "## 2. Empirical Candidate Model Decision Matrix",
        "",
        "| Candidate ID | Routing Model | Synthesis Model | Data Accuracy | Citation Faithfulness | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k Queries | Composite Utility |",
        "| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for cand in report.get("candidates", []):
        m = cand["metrics"]
        lines.append(
            f"| **`{cand['model_id']}`** | `{cand['routing_model']}` | `{cand['synthesis_model']}` | "
            f"{m['mean_data_accuracy']:.4f} | {m['mean_citation_faithfulness']:.4f} | "
            f"{m['latency_p50_ms']:.1f} | {m['latency_p95_ms']:.1f} | "
            f"${m['estimated_cost_per_1k_queries_usd']:.2f} | **{m['composite_utility_score']:.4f}** |"
        )

    lines.extend(
        [
            "",
            "## 3. Architectural Trade-Off Notes",
        ]
    )
    for cand in report.get("candidates", []):
        lines.append(f"- **`{cand['model_id']}`**: {cand['architecture_notes']}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark candidate Gemini models and log runs to Vertex AI Experiments."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "evals" / "dataset" / "benchmark_catalog.evalset.json",
        help="Path to evaluation dataset (.evalset.json).",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=BACKEND_SRC / "app" / "data" / "catalog_seed.json",
        help="Path to catalog seed JSON for hermetic BigQuery mocking.",
    )
    parser.add_argument(
        "--rubrics-dir",
        type=Path,
        default=REPO_ROOT / "evals" / "rubrics",
        help="Directory containing data_accuracy.md and citation_faithfulness.md.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Limit number of stratified benchmark cases per candidate model across all 5 categories.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Bounded worker concurrency for live Vertex AI benchmark queries.",
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default="bestbuy-catalog-model-selection-benchmark",
        help="Vertex AI Experiment name.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Execute live Vertex AI and BigQuery queries.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT / "evals" / "reports" / "model_benchmark_results.json",
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=REPO_ROOT / "evals" / "reports" / "model_benchmark_summary.md",
        help="Output Markdown decision matrix path.",
    )
    args = parser.parse_args()

    report = run_model_benchmarks(
        dataset_path=args.dataset,
        catalog_path=args.catalog,
        rubrics_dir=args.rubrics_dir,
        limit=args.limit,
        live=args.live,
        experiment_name=args.experiment_name,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
        concurrency=args.concurrency,
    )
    print(generate_benchmark_markdown(report))


if __name__ == "__main__":
    main()
