# Evaluation & Quality Flywheel Agent Guide

Welcome to the evaluation engine of the **Best Buy Catalog Comparison Agent**. This module implements the Quality Flywheel and quantitative evaluation harness to ensure zero hallucination, strict factual grounding, and high-fidelity citations.

---

## 1. Directory Structure

```
evals/
├── AGENTS.md                  # This file (evaluation harness guide)
├── adk_eval_config.json       # Official ADK EvalConfig (hallucinations_v1, trajectory)
├── trajectory_grader.py       # Deterministic & semantic tool trajectory grading engine
├── runner.py                  # Hermetic in-memory SQL + GenAI evaluation runner (mocks BigQuery & Vertex AI in hermetic mode)
├── analyze.py                 # Report analysis, metric visualization, and trajectory regression checks
├── anti_overfitting_gate.py   # Counterfactual Anti-Overfitting Gate & Generalization analyzer
├── judge.py                   # Single-response Faithfulness LLM-as-a-Judge
├── pairwise_judge.py          # Head-to-head Pairwise Judge with position-bias swap checks
├── generate_model_matrix.py   # Empirical Foundation Model Decision Scorecard generator (ADR-004)
├── dataset/
│   ├── benchmark_catalog.evalset.json # Canonical 80-pair ADK EvalSet
│   ├── holdout_catalog.evalset.json   # Curated Holdout & Counterfactual ADK EvalSet
│   ├── benchmark_queries.json # Legacy 80-pair comparison test cases
│   └── fixtures/
│       └── simple_test.evalset.json   # 1-case integration fixture for Pytest
├── rubrics/
│   ├── data_accuracy.md       # Ground truth accuracy criteria
│   ├── citation_faithfulness.md # Citation validity criteria
│   ├── semantic_coherence.md  # Semantic coherence and hallucination criteria
│   ├── tool_trajectory.md     # Tool trajectory and argument criteria
│   └── counterfactual_anti_overfitting.md # Anti-overfitting and counterfactual rubric
└── reports/                   # Output artifacts from eval runs
    ├── model_decision_matrix.json     # Empirical model decision scorecard JSON
    ├── model_decision_scorecard.md    # Executive Markdown scorecard for ADR-004
    └── .gitkeep
```

---

## 2. Core Evaluation Metrics

| Metric | Target | Assessment Engine | Description |
| :--- | :--- | :--- | :--- |
| **Grounding / Hallucination** | $\ge 0.95$ | ADK `hallucinations_v1` (Segmenter + Sentence Validator) | Closed-domain sentence entailment against BigQuery tool outputs |
| **Tool Trajectory Quality** | $1.00$ | ADK `tool_trajectory_avg_score` | Validates that `query_catalog` was invoked with correct arguments |
| **Data Accuracy** | $\ge 0.98$ | Spec matcher against catalog ground truth | $< 0.95$ triggers immediate rollback |
| **Citation Faithfulness** | $\ge 0.95$ | Inline `[SKU: ...]` citation validator | Hallucinated SKUs score 0.0 |
| **Generalization Gap ($\Delta$)** | $\le 0.05$ | `evals.anti_overfitting_gate` | Performance drop between benchmark and holdout dataset |
| **Counterfactual Fidelity** | $\ge 0.95$ | `evals.anti_overfitting_gate` | Factual adherence to perturbed catalog specs over parametric memory |
| **Negative Query Suppression**| $100.0\%$ | `evals.anti_overfitting_gate` | Asserts 0 hallucinated products/citations on rants/chatter |
| **End-to-End P95 Latency** | $\le 3.0$s | 95th percentile request duration | $> 3.0$s requires optimization |
| **Structured Output Validity**| $1.00$ | Pydantic `CompareResponse` schema validation | Any validation error is fatal |
| **Pairwise Synthesis Win Rate**| $\ge 0.85$ | `evals/pairwise_judge.py` (`PairwiseJudgment` schema) | Position-bias-checked head-to-head comparison against baseline models |

---

## 3. ADK Evaluation Workflows

### A. Programmatic Pytest Integration (adk.dev/evaluate pattern)
Runs a fast integration test using ADK's `AgentEvaluator.evaluate()`:
```bash
pytest backend/tests/integration/test_agent_evaluation.py -v
```

### B. Command-Line Evaluation (`adk eval`)
Run the complete 80-pair benchmark via ADK CLI:
```bash
adk eval backend/src/app/agent \
  evals/dataset/benchmark_catalog.evalset.json \
  --config_file_path=evals/adk_eval_config.json \
  --print_detailed_results
```

### C. Conformance Testing (`adk conformance test`)
Run conformance tests against baseline files to gate PRs and generate markdown reports:
```bash
adk conformance test evals/ --generate_report --report_dir=reports/conformance
```

### D. Interactive Trace Debugger (`adk web`)
Launch the visual web debugger to inspect Event, Request, Response, and Graph tabs:
```bash
adk web backend/src/app/agent
```

### E. Hermetic Fast-Path Runner (Zero-Cloud Cost)
For instant local iteration without GCP API quota:
```bash
python3 -m evals.runner \
  --dataset evals/dataset/benchmark_catalog.evalset.json \
  --output evals/reports/eval_results.json
```
`run_benchmark()` defaults `catalog_path` to `backend/src/app/data/catalog_seed.json` for ergonomic programmatic usage, and supports custom catalog seeds for counterfactual perturbation tests.

To execute evaluations through the Google ADK Runner lifecycle:
```bash
python3 -m evals.runner \
  --dataset evals/dataset/fixtures/simple_test.evalset.json \
  --output evals/reports/eval_results.json \
  --use-adk-runner
```

### F. Brand-Agnostic Hermetic Mocking (Anti-Overfitting)
`create_hermetic_bq_client` utilizes generalized token-overlap matching against catalog brand names and item titles instead of hardcoded brand whitelists, ensuring unbiased evaluation over novel products, categories, and holdout datasets.

### G. Candidate Foundation Model & Stage-First Specialist Benchmarking (`evals/benchmark_models.py`)
Benchmark candidate foundation models (`gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-1.5-flash`, `tiered-hybrid`) using a **Stage-First (Specialist-Only)** architecture, custom rubrics (`evals/rubrics/data_accuracy.md`, `evals/rubrics/citation_faithfulness.md`), stratified 5-category sampling (`Laptops`, `Tablets`, `Headphones`, `Smart Home`, `TVs`), and sanitized Vertex AI Metadata run IDs (`run-stage1-intent-<model>-<ts>`, `run-stage2-rerank-<model>-<ts>`, `run-stage3-synthesis-<model>-<ts>`):
1. **Stage-First ADK Agent Specialist Evaluation (`run_per_stage_benchmarks`)**:
   - **Stage 1 (`QueryIntentSpecialist`)**: Measures query intent classification accuracy, token usage, cost, and P95 latency across all 4 models (`run-stage1-intent-<model>-<ts>`).
   - **Stage 2 (`RelevanceDetectorSpecialist`)**: Measures post-retrieval candidate reranking with explicit **Accuracy (Exact Match)**, **Precision**, **Recall**, **F1 Score**, cost, and P95 latency across identical candidate pools (`run-stage2-rerank-<model>-<ts>`).
   - **Stage 3 (`SpecComparisonSpecialist`)**: Measures grounded matrix synthesis, spec data accuracy, citation faithfulness, cost, and P95 latency (`run-stage3-synthesis-<model>-<ts>`).
   - **Synthesized Architecture Reports**: Candidate architecture metrics (`tiered-hybrid`, `gemini-2.5-flash`, etc.) are synthesized directly and analytically from their constituent specialist stages ($\text{P95}_{\text{Pipeline}} = \text{P95}_{\text{Stage 1}} + \text{P95}_{\text{BQ}} + \text{P95}_{\text{Stage 2}} + \text{P95}_{\text{Stage 3}}$), avoiding black-box error attribution.
   - **Optional End-to-End Evaluation**: Monolithic end-to-end multi-agent evaluation can be optionally run using `--include-end-to-end`.
   - **Summed Latency SLA Check**: Empirically verifies that total pipeline latency satisfies $\le 3000\text{ ms}$ without artificial per-stage constraints.
2. **Execution**:
```bash
# Execute Stage-First specialist benchmark sweep and log to GCP project fde-bestbuy-sandbox-dev-508321:
python3 evals/benchmark_models.py \
  --live \
  --limit 15 \
  --concurrency 4 \
  --experiment-name bestbuy-catalog-model-selection-benchmark \
  --output-json evals/reports/model_benchmark_results.json \
  --output-md evals/reports/model_benchmark_summary.md

# To include legacy end-to-end multi-agent execution:
python3 evals/benchmark_models.py --live --include-end-to-end
```
This command logs the 12 per-stage runs and the champion tiered-hybrid pipeline run to Vertex AI Experiments, and automatically updates `evals/reports/model_decision_scorecard.md`.

### H. Empirical Foundation Model Decision Matrix & Pairwise Judge (ADR-004)
Generate the multi-objective Model Decision Scorecard (`tiered-hybrid`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-1.5-flash`) and execute head-to-head pairwise tournaments:
```bash
# Generate JSON and Markdown Model Decision Scorecard:
python3 -m evals.generate_model_matrix \
  --output-json evals/reports/model_decision_matrix.json \
  --output-md evals/reports/model_decision_scorecard.md

# Execute standalone head-to-head Pairwise Judge check:
python3 -m evals.pairwise_judge
```

### I. Counterfactual Anti-Overfitting & Generalization Gate (`evals/anti_overfitting_gate.py`)
To verify that prompt optimizations do not overfit to the 80 benchmark queries and that the agent adheres strictly to retrieved facts over parametric memory:
```bash
# Run both benchmark and holdout evaluations and compute generalization gap:
python3 -m evals.anti_overfitting_gate \
  --benchmark-dataset evals/dataset/benchmark_catalog.evalset.json \
  --holdout-dataset evals/dataset/holdout_catalog.evalset.json \
  --max-gap 0.05 \
  --strict
```

---

## 4. Tool Trajectory Grader & Sequence Validation

The Trajectory Grader (`evals/trajectory_grader.py`) validates agent tool executions:
- **Match Modes**:
  - `EXACT`: Verifies identical tool sequence and exact argument equality.
  - `IN_ORDER`: Ensures all expected tools are called sequentially while allowing benign intermediate retrieval steps.
  - `ANY_ORDER`: Allows tools to execute in any sequence.
  - `FUZZY_SEMANTIC`: Validates that `query_catalog` parameters contain the expected brand and model keywords without failing on punctuation or casing nuances.
- **Sequence Diagnostics**: Automatically flags missing tool calls, unintended tool calls, argument drift, and tool latency.
- **Benchmark Integration**: Integrated directly into `evals.runner` and `evals.analyze` to compute `mean_tool_trajectory_score` and enforce $\ge 0.95$ gate.

---

## 5. Continuous Hillclimbing Rule

Whenever improving prompts, tool definitions, or response formatting:
1. First run the baseline eval runner and record metrics.
2. Make code or prompt modifications.
3. Re-run eval runner and `evals.generate_model_matrix` on both benchmark and holdout datasets via `evals.anti_overfitting_gate`. If Data Accuracy or Citation Faithfulness drops by even $0.01$ or if the generalization gap exceeds $0.05$, the change is rejected.
