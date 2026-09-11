# Evaluation & Quality Flywheel Agent Guide

Welcome to the evaluation engine of the **Best Buy Catalog Comparison Agent**. This module implements the Quality Flywheel and quantitative evaluation harness to ensure zero hallucination, strict factual grounding, and high-fidelity citations.

---

## 1. Directory Structure

```
evals/
├── AGENTS.md                  # This file (evaluation harness guide)
├── runner.py                  # CLI evaluation test runner
├── analyze.py                 # Report analysis and metric visualization
├── dataset/
│   └── benchmark_queries.json # 80 gold-standard comparison test cases
├── rubrics/
│   ├── data_accuracy.md       # Ground truth accuracy criteria
│   └── citation_faithfulness.md # Citation validity criteria
└── reports/                   # Output artifacts from eval runs
    └── .gitkeep
```

---

## 2. Core Evaluation Metrics

| Metric | Target | Formula / Assessment | Critical Threshold |
| :--- | :--- | :--- | :--- |
| **Data Accuracy** | $\ge 0.98$ | Percentage of technical specs matching BigQuery catalog exactly | $< 0.95$ triggers immediate rollback |
| **Citation Faithfulness** | $\ge 0.95$ | Ratio of technical claims with valid `[SKU: ...]` citation | $< 0.90$ fails CI pipeline |
| **End-to-End P95 Latency** | $\le 3.0$s | 95th percentile request duration in seconds | $> 3.0$s requires optimization |
| **Structured Output Validity**| $1.00$ | Valid JSON parsing against Pydantic `CompareResponse` schema | Any validation error is fatal |

---

## 3. Benchmark Dataset Schema

`evals/dataset/benchmark_queries.json` contains curated test cases across primary product categories:
```json
[
  {
    "id": "laptop-001",
    "category": "Laptops",
    "query": "Compare Apple MacBook Air M3 13-inch and Dell XPS 13 Intel Core Ultra 7",
    "expected_skus": ["6534606", "6575132"],
    "key_differential_features": ["processor", "ram_gb", "battery_life_hours", "weight_lbs"],
    "ground_truth_specs": {
      "6534606": {"processor": "Apple M3 8-core", "ram_gb": 16, "battery_life_hours": 18.0},
      "6575132": {"processor": "Intel Core Ultra 7", "ram_gb": 16, "battery_life_hours": 14.0}
    }
  }
]
```

---

## 4. Running Evaluations

```bash
# Run the complete 80-pair benchmark suite
python3 -m evals.runner \
  --dataset evals/dataset/benchmark_queries.json \
  --output evals/reports/eval_results.json \
  --judge-model gemini-1.5-flash

# Run targeted eval on a single category
python3 -m evals.runner \
  --dataset evals/dataset/benchmark_queries.json \
  --category Laptops

# Analyze score progression vs previous run
python3 -m evals.analyze \
  --current evals/reports/eval_results.json \
  --baseline evals/reports/baseline_results.json
```

---

## 5. Continuous Hillclimbing Rule

Whenever improving prompts, tool definitions, or response formatting:
1. First run the baseline eval runner and record metrics.
2. Make code or prompt modifications.
3. Re-run eval runner. If Data Accuracy or Citation Faithfulness drops by even $0.01$, the change is rejected.
