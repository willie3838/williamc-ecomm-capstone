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
├── dataset/
│   ├── benchmark_catalog.evalset.json # Canonical 80-pair ADK EvalSet
│   ├── benchmark_queries.json # Legacy 80-pair comparison test cases
│   └── fixtures/
│       └── simple_test.evalset.json   # 1-case integration fixture for Pytest
├── rubrics/
│   ├── data_accuracy.md       # Ground truth accuracy criteria
│   └── citation_faithfulness.md # Citation validity criteria
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
  --dataset evals/dataset/benchmark_queries.json \
  --output evals/reports/eval_results.json
```


---

## 5. Continuous Hillclimbing Rule

Whenever improving prompts, tool definitions, or response formatting:
1. First run the baseline eval runner and record metrics.
2. Make code or prompt modifications.
3. Re-run eval runner. If Data Accuracy or Citation Faithfulness drops by even $0.01$, the change is rejected.
