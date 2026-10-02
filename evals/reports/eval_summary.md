# 📊 Evaluation Flywheel Benchmark Summary

- **Timestamp**: `2026-10-02T16:09:21.814011+00:00`
- **Dataset**: `evals/dataset/benchmark_catalog.evalset.json` (80 Cases: 60 2-Product + 20 Multi-Product 3–5 SKU Comparisons)
- **Total Cases**: 80
- **Passed Cases**: 80 / 80 (100.0%)
- **Overall Status**: ✅ **PASSED**

## 1. Core Flywheel Metrics

| Metric | Measured | Target | Status |
| :--- | :--- | :--- | :--- |
| **Data Accuracy** | 1.0000 | $\ge 0.98$ | ✅ PASS |
| **Citation Faithfulness** | 1.0000 | $\ge 0.95$ | ✅ PASS |
| **Semantic Coherence (2–5 Products)** | 1.0000 | $\ge 0.95$ | ✅ PASS |
| **Tool Trajectory Score** | 1.0000 | $\ge 1.00$ | ✅ PASS |
| **P95 Latency** | 0.0146s | $\le 3.0$s | ✅ PASS |
| **Structured Output Validity** | 1.0000 | $1.00$ | ✅ PASS |

## 2. Category Performance Breakdown

| Category | Cases | Pass Rate | Data Accuracy | Citation Faithfulness | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Laptops** | 16 | 100.0% | 1.0000 | 1.0000 | 0.0123s |
| **Tablets** | 16 | 100.0% | 1.0000 | 1.0000 | 0.0101s |
| **Headphones** | 16 | 100.0% | 1.0000 | 1.0000 | 0.0088s |
| **Smart Home** | 16 | 100.0% | 1.0000 | 1.0000 | 0.0100s |
| **TVs** | 16 | 100.0% | 1.0000 | 1.0000 | 0.0111s |
