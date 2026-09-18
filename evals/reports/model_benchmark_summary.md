# Vertex AI Foundation Model Benchmark & Trade-Off Report

- **Vertex AI Experiment**: `bestbuy-catalog-model-selection-benchmark`
- **GCP Project**: `fde-bestbuy-sandbox-dev-508321` (`us-central1`)
- **Cases Evaluated**: `80`
- **Recommended Architecture**: **`gemini-2.5-flash`**

## 1. Custom Evaluation Rubrics Applied
- **`data_accuracy.md`**: Target $\ge 0.98$ (Critical Rollback $< 0.95$)
- **`citation_faithfulness.md`**: Target $\ge 0.95$ (Critical Pipeline $< 0.90$)

## 2. Empirical Candidate Model Decision Matrix

| Candidate ID | Routing Model | Synthesis Model | Data Accuracy | Citation Faithfulness | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k Queries | Composite Utility |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`gemini-2.5-flash`** | `gemini-2.5-flash` | `gemini-2.5-flash` | 1.0000 | 1.0000 | 783.3 | 1385.3 | $0.53 | **0.9363** |
| **`gemini-2.5-pro`** | `gemini-2.5-pro` | `gemini-2.5-pro` | 1.0000 | 1.0000 | 1622.8 | 2795.1 | $8.04 | **0.7015** |
| **`gemini-1.5-flash`** | `gemini-1.5-flash` | `gemini-1.5-flash` | 1.0000 | 1.0000 | 892.9 | 1644.2 | $0.25 | **0.9263** |
| **`tiered-hybrid`** | `gemini-2.5-flash` | `gemini-2.5-pro` | 1.0000 | 1.0000 | 943.1 | 1725.4 | $1.69 | **0.8926** |

## 3. Architectural Trade-Off Notes
- **`gemini-2.5-flash`**: Single-model high-throughput Flash architecture; lowest latency and low cost.
- **`gemini-2.5-pro`**: Single-model deep reasoning Pro architecture; highest reasoning depth, higher token cost.
- **`gemini-1.5-flash`**: Previous-generation Flash baseline; lower structured JSON adherence on multi-brand edge cases.
- **`tiered-hybrid`**: Dynamic ADK routing: Gemini 2.5 Flash for sub-second intent & reranking + Gemini 2.5 Pro for grounded synthesis.
