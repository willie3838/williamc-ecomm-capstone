# Evaluation & Quality Flywheel Agent Guide

Welcome to the evaluation engine of the **Best Buy Catalog Comparison Agent**. This module implements the Quality Flywheel and quantitative evaluation harness to ensure zero hallucination, strict factual grounding, and high-fidelity citations.

---

## 1. Directory Structure

```
evals/
├── AGENTS.md                  # This file (evaluation harness guide)
├── adk_eval_config.json       # Official ADK EvalConfig (hallucinations_v1, trajectory)
├── runner.py                  # Hermetic in-memory SQL + GenAI evaluation runner (mocks BigQuery & Vertex AI in hermetic mode)
├── analyze.py                 # Report analysis and metric visualization
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

### F. Candidate Foundation Model Benchmarking & Vertex AI Experiments (`evals/benchmark_models.py`)
Benchmark candidate foundation models (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-1.5-flash`, `tiered-hybrid`) using custom rubrics (`evals/rubrics/data_accuracy.md`, `evals/rubrics/citation_faithfulness.md`) and log experiment runs to Google Cloud Vertex AI Experiments:
```bash
python3 -m evals.benchmark_models \
  --dataset evals/dataset/benchmark_catalog.evalset.json \
  --output-json evals/reports/model_benchmark_results.json \
  --output-md evals/reports/model_benchmark_summary.md
```

### G. Empirical Foundation Model Decision Matrix & Pairwise Judge (ADR-004)
Generate the multi-objective Model Decision Scorecard (`tiered-hybrid`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-1.5-flash`) and execute head-to-head pairwise tournaments:
```bash
# Generate JSON and Markdown Model Decision Scorecard:
python3 -m evals.generate_model_matrix \
  --output-json evals/reports/model_decision_matrix.json \
  --output-md evals/reports/model_decision_scorecard.md

# Execute standalone head-to-head Pairwise Judge check:
python3 -m evals.pairwise_judge
```

### H. Counterfactual Anti-Overfitting & Generalization Gate (`evals/anti_overfitting_gate.py`)
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

## 4. Continuous Hillclimbing Rule

Whenever improving prompts, tool definitions, or response formatting:
1. First run the baseline eval runner and record metrics.
2. Make code or prompt modifications.
3. Re-run eval runner and `evals.generate_model_matrix` on both benchmark and holdout datasets via `evals.anti_overfitting_gate`. If Data Accuracy or Citation Faithfulness drops by even $0.01$ or if the generalization gap exceeds $0.05$, the change is rejected.
