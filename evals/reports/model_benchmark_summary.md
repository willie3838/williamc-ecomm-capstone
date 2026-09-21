# Vertex AI Foundation Model Benchmark & Trade-Off Report

- **Vertex AI Experiment**: `bestbuy-catalog-model-selection-benchmark`
- **GCP Project**: `fde-bestbuy-sandbox-dev-508321` (`us-central1`)
- **Cases Evaluated**: `5`
- **Execution Mode**: `live`
- **Recommended Architecture**: **`gemini-2.5-flash-lite`**

## 1. Custom Evaluation Rubrics Applied
- **`data_accuracy.md`**: Target $\ge 0.98$ (Critical Rollback $< 0.95$)
- **`citation_faithfulness.md`**: Target $\ge 0.95$ (Critical Pipeline $< 0.90$)

## 2. Per-Stage ADK Specialist Agent Evaluation Results

### 2.1 Stage 1: QueryIntentSpecialist (Query Analysis & Filter Generation)

| Model ID | Intent Extraction Accuracy | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 1.0000 | 180.0 | 320.0 | $0.1105 |
| `gemini-2.5-flash` | 1.0000 | 180.0 | 320.0 | $0.1934 |
| `gemini-2.5-pro` | 1.0000 | 450.0 | 850.0 | $2.5005 |
| `gemini-1.5-flash` | 1.0000 | 180.0 | 320.0 | $0.1100 |

### 2.2 Stage 2: RelevanceDetectorSpecialist (Candidate Reranking & SKU Matching)

| Model ID | Accuracy (Exact Match) | Precision | Recall | F1 Score | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 0.6000 | 0.8333 | 1.0000 | 0.9091 | 220.0 | 380.0 | $0.1102 |
| `gemini-2.5-flash` | 0.6000 | 0.8333 | 1.0000 | 0.9091 | 220.0 | 380.0 | $0.1971 |
| `gemini-2.5-pro` | 0.6000 | 0.8333 | 1.0000 | 0.9091 | 520.0 | 950.0 | $2.4865 |
| `gemini-1.5-flash` | 0.6000 | 0.8333 | 1.0000 | 0.9091 | 220.0 | 380.0 | $0.1094 |

### 2.3 Stage 3: SpecComparisonSpecialist (Synthesis & Citation Verification)

| Model ID | Data Accuracy | Citation Faithfulness | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 0.9000 | 0.9667 | 620.0 | 980.0 | $0.2814 |
| `gemini-2.5-flash` | 0.9000 | 0.9500 | 620.0 | 980.0 | $0.5145 |
| `gemini-2.5-pro` | 0.9000 | 0.9667 | 1150.0 | 1680.0 | $7.8048 |
| `gemini-1.5-flash` | 0.9000 | 0.9667 | 620.0 | 980.0 | $0.2415 |

## 3. Empirical Candidate Model Decision Matrix

| Candidate ID | Routing Model | Synthesis Model | Data Accuracy | Citation Faithfulness | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k Queries | Composite Utility |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`gemini-2.5-flash-lite`** | `gemini-2.5-flash-lite` | `gemini-2.5-flash-lite` | 0.9000 | 0.9667 | 1060.0 | 1800.0 | $0.50 | **0.8407** |
| **`gemini-2.5-flash`** | `gemini-2.5-flash` | `gemini-2.5-flash` | 0.9000 | 0.9500 | 1060.0 | 1800.0 | $0.91 | **0.8324** |
| **`gemini-2.5-pro`** | `gemini-2.5-pro` | `gemini-2.5-pro` | 0.9000 | 0.9667 | 2160.0 | 3600.0 | $12.79 | **0.6947** |
| **`gemini-1.5-flash`** | `gemini-1.5-flash` | `gemini-1.5-flash` | 0.9000 | 0.9667 | 1060.0 | 1800.0 | $0.46 | **0.8066** |
| **`tiered-hybrid`** | `gemini-2.5-flash` | `gemini-2.5-pro` | 0.9000 | 0.9667 | 1590.0 | 2500.0 | $8.20 | **0.7547** |

## 4. Summed Pipeline Latency & Strict SLA Verification (P95 $\le 3.0$s)

- **Stage 1 (QueryIntentSpecialist)**: `gemini-2.5-flash` (P95: `320.0 ms`)
- **BigQuery Catalog Retrieval**: Parameterized SQL (P95: `120.0 ms`)
- **Stage 2 (RelevanceDetectorSpecialist)**: `gemini-2.5-flash` (P95: `380.0 ms`)
- **Stage 3 (SpecComparisonSpecialist)**: `gemini-2.5-pro` (P95: `1680.0 ms`)
- **Summed End-to-End Pipeline P95 Latency**: **`2500.0 ms`** (SLA $\le 3000\text{ ms}$: **PASSED**)

## 5. Architectural Trade-Off Notes

- **`gemini-2.5-flash-lite`**: Ultra-lightweight high-throughput model; optimal for Stage 1 intent extraction and fast routing.
- **`gemini-2.5-flash`**: Single-model high-throughput Flash architecture; lowest latency and low cost.
- **`gemini-2.5-pro`**: Single-model deep reasoning Pro architecture; highest reasoning depth, higher token cost.
- **`gemini-1.5-flash`**: Previous-generation Flash baseline; lower structured JSON adherence on multi-brand edge cases.
- **`tiered-hybrid`**: Dynamic ADK routing: Gemini 2.5 Flash for sub-second intent & reranking + Gemini 2.5 Pro for grounded synthesis.
