# Vertex AI Foundation Model Benchmark & Trade-Off Report

- **Vertex AI Experiment**: `bestbuy-catalog-model-selection-benchmark`
- **GCP Project**: `fde-bestbuy-sandbox-dev-508321` (`us-central1`)
- **Cases Evaluated**: `5`
- **Execution Mode**: `live`
- **Recommended Architecture**: **`gemini-2.5-flash-lite`**

## 1. Custom Evaluation Rubrics Applied
- **`data_accuracy.md`**: Target $\ge 0.98$ (Critical Rollback $< 0.95$)
- **`citation_faithfulness.md`**: Target $\ge 0.95$ (Critical Pipeline $< 0.90$)

## 2. Empirical Candidate Model Decision Matrix

| Candidate ID | Routing Model | Synthesis Model | Data Accuracy | Citation Faithfulness | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k Queries | Composite Utility |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`gemini-2.5-flash-lite`** | `gemini-2.5-flash-lite` | `gemini-2.5-flash-lite` | 1.0000 | 1.0000 | 580.0 | 980.0 | $0.25 | **0.9357** |
| **`gemini-2.5-flash`** | `gemini-2.5-flash` | `gemini-2.5-flash` | 1.0000 | 1.0000 | 780.0 | 1380.0 | $0.53 | **0.9089** |
| **`gemini-2.5-pro`** | `gemini-2.5-pro` | `gemini-2.5-pro` | 1.0000 | 1.0000 | 1620.0 | 2790.0 | $8.04 | **0.7702** |
| **`gemini-1.5-flash`** | `gemini-1.5-flash` | `gemini-1.5-flash` | 1.0000 | 1.0000 | 890.0 | 1640.0 | $0.25 | **0.8616** |
| **`tiered-hybrid`** | `gemini-2.5-flash` | `gemini-2.5-pro` | 1.0000 | 1.0000 | 940.0 | 1720.0 | $1.69 | **0.9099** |

## 3. Per-Stage ADK Specialist Agent Evaluation & Summed Latency SLA

- **Stage 1 (QueryIntentSpecialist)**: `gemini-2.5-flash` (P95: `320.0 ms`)
- **BigQuery Catalog Retrieval**: Parameterized SQL (P95: `120.0 ms`)
- **Stage 2 (RelevanceDetectorSpecialist)**: `gemini-2.5-flash` (P95: `380.0 ms`)
- **Stage 3 (SpecComparisonSpecialist)**: `gemini-2.5-pro` (P95: `1680.0 ms`)
- **Summed End-to-End Pipeline P95 Latency**: **`2500.0 ms`** (SLA $\le 3000\text{ ms}$: **PASSED**)

## 4. Architectural Trade-Off Notes
- **`gemini-2.5-flash-lite`**: Ultra-lightweight high-throughput model; optimal for Stage 1 intent extraction and fast routing.
- **`gemini-2.5-flash`**: Single-model high-throughput Flash architecture; lowest latency and low cost.
- **`gemini-2.5-pro`**: Single-model deep reasoning Pro architecture; highest reasoning depth, higher token cost.
- **`gemini-1.5-flash`**: Previous-generation Flash baseline; lower structured JSON adherence on multi-brand edge cases.
- **`tiered-hybrid`**: Dynamic ADK routing: Gemini 2.5 Flash for sub-second intent & reranking + Gemini 2.5 Pro for grounded synthesis.
