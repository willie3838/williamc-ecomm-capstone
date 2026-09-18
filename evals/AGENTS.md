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

### F. Counterfactual Anti-Overfitting & Generalization Gate
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

## 5. Continuous Hillclimbing Rule

Whenever improving prompts, tool definitions, or response formatting:
1. First run the baseline eval runner and record metrics.
2. Make code or prompt modifications.
3. Re-run eval runner on both benchmark and holdout datasets via `evals.anti_overfitting_gate`. If Data Accuracy or Citation Faithfulness drops by even $0.01$ or if the generalization gap exceeds $0.05$, the change is rejected.
