# Design: Stage 4 LLM Spec Winners & Complete Removal of Offline/Hermetic Fallbacks

**Date:** 2026-10-05
**Repository:** `williamc-ecomm-capstone`

## 1. Problem Statement

1. **Brittle Hardcoded `CATEGORY_SPEC_REGISTRY` for Spec Winners**:
   - `ComparisonOrchestrator.build_comparison_matrix` in `backend/src/app/agent/orchestrator.py` currently relies on a hardcoded `CATEGORY_SPEC_REGISTRY` dictionary (`tuple[str, bool]`) and `parse_numeric()` regex extraction.
   - Any spec key not explicitly listed in `CATEGORY_SPEC_REGISTRY` (such as `weight_oz` when only `weight_lbs` was registered, or `bluetooth_version`) or stored as a version/tier string (`"5.3"` vs `"5.2"`, `"Wi-Fi 6E"` vs `"Wi-Fi 6"`, processor/GPU tiers) receives `winner=None`.
2. **Undesired Silent Offline/Hermetic Fallbacks (`hermetic_adapter.py`)**:
   - Production code (`backend/src/app/tools/catalog.py`, `backend/src/app/routes/compare.py`, `backend/src/app/agent/orchestrator.py`, `backend/src/app/agent/runner.py`, `backend/src/app/data/analytics.py`) and evaluation scripts (`evals/runner.py`, `evals/run_pipeline.py`, `evals/pairwise_judge.py`, `evals/benchmark_models.py`) contain silent fallback logic that swaps out live BigQuery and Vertex AI Gemini for `create_hermetic_bq_client()` (reading local `catalog_seed.json`) and `HermeticModelAdapter` (regex string heuristics) when credentials fail or `HERMETIC_EVAL=true` / `PYTEST_CURRENT_TEST` is set.
   - CI pipelines (`deployment/cloudbuild.yaml`, `deployment/cloudbuild-pr.yaml`, `.github/workflows/ci.yml`) were running `evals/runner.py` in offline hermetic mode instead of authenticated live mode with `--limit 10`.

## 2. Architecture & Design

### 2.1 Piggyback `spec_winners` on Stage 4 `ComparisonSynthesis` LLM Call
- **Zero Extra LLM Calls / Zero Added Latency**:
  - Extend `ComparisonSynthesis` in `backend/src/app/models/comparison.py` with:
    ```python
    spec_winners: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of specification key (plus 'price') to the winning product identifier: "
            "for 2-product comparisons use 'product_a', 'product_b', 'tie', or 'none'; "
            "for 3+ product comparisons use 'product_1'..'product_N' (or SKU), 'tie', or 'none'. "
            "Evaluate numeric values, version strings (e.g., bluetooth_version '5.3' > '5.2'), "
            "unit variants (e.g., lower weight_oz / weight_lbs is better; higher battery_life_hours is better), "
            "and objective hardware tiers. Use 'none' for purely subjective attributes like color."
        ),
    )
    ```
  - Delete `CATEGORY_SPEC_REGISTRY` from `backend/src/app/agent/orchestrator.py`.
  - Pass the union of candidate specification keys and values into the Stage 4 synthesis prompt and instruct Gemini to populate `spec_winners` for all comparable specs.
  - Update `ComparisonOrchestrator.build_comparison_matrix` to accept `spec_winners: dict[str, str] | None = None` from the Stage 4 `ComparisonSynthesis` response, normalizing SKU / `product_a` / `product_b` / `product_1..N` labels and falling back to objective numeric/version comparison only when a specific key is omitted from the dictionary.

### 2.2 Complete Removal of `hermetic_adapter.py` and Offline Fallbacks
- **Extract Live ADK Wrapper to `backend/src/app/agent/adk_llm.py` & Delete `hermetic_adapter.py`**:
  - Move the live production classes/functions (`CatalogAdkLlm`, `_get_shared_vertex_client`, `_get_vertex_client_for_model`, `_warm_vertex_client_and_auth`, `verify_and_scrub_synthesis_claims`, and Model Armor live sanitization helpers) into `backend/src/app/agent/adk_llm.py` with **all** `hermetic`, `HERMETIC_EVAL`, `PYTEST_CURRENT_TEST`, `HermeticModelAdapter`, `create_hermetic_bq_client`, and `create_hermetic_genai_client` code removed.
  - Delete `backend/src/app/agent/hermetic_adapter.py`.
- **Fail Fast in Production Modules (`backend/src/app/`)**:
  - `backend/src/app/tools/catalog.py`: Remove `create_hermetic_bq_client()` fallbacks; raise explicit runtime/service errors if BigQuery client initialization or query execution fails.
  - `backend/src/app/routes/compare.py`: Remove `catalog_seed.json` fallback in `list_catalog`; raise HTTP 503 if `query_catalog` fails.
  - `backend/src/app/agent/orchestrator.py`, `runner.py`, `multi_agent.py`, `compaction.py`, `data/analytics.py`: Remove all `hermetic` parameters, `_is_hermetic_or_test()`, and `HERMETIC_EVAL` branches.
- **Live-Only Evals & CI (`--limit 10` in CI, 80 in Nightly)**:
  - Update `evals/runner.py`, `evals/run_pipeline.py`, `evals/pairwise_judge.py`, and `evals/benchmark_models.py` to always run against live BigQuery and Vertex AI (retaining `--live` as a default-True / backwards-compatible CLI flag so `deployment/terraform/eval_job.tf` continues to work unchanged).
  - Update `deployment/cloudbuild.yaml`, `deployment/cloudbuild-pr.yaml`, and `.github/workflows/ci.yml` to remove `HERMETIC_EVAL=true`, authenticate via GCP Workload Identity Federation in GitHub Actions before tests/evals, and execute `evals/runner.py --live --limit 10`.
- **Test Suite Cleanup (`backend/tests/`)**:
  - Delete the 13 tests that existed solely to test `HermeticModelAdapter`, `create_hermetic_bq_client`, `create_hermetic_genai_client`, and `hermetic=True` flag plumbing.
  - Keep `unittest.mock` strictly for failure-simulation tests (`429` rate limits, `503` service unavailable, Model Armor blocks) and unit-level isolated component tests.
