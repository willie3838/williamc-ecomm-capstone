# Vertex AI Foundation Model Benchmark & Trade-Off Report

- **Vertex AI Experiment**: `bestbuy-catalog-model-selection-benchmark`
- **GCP Project**: `fde-bestbuy-sandbox-dev-508321` (`us-central1`)
- **Cases Evaluated**: `15`
- **Execution Mode**: `hermetic`
- **Recommended Architecture**: **`tiered-hybrid`**

## 1. Custom Evaluation Rubrics Applied
- **`data_accuracy.md`**: Target $\ge 0.98$ (Critical Rollback $< 0.95$)
- **`citation_faithfulness.md`**: Target $\ge 0.95$ (Critical Pipeline $< 0.90$)

## 2. Per-Stage ADK Specialist Agent Evaluation Results

### 2.1 Stage 1: QueryIntentSpecialist (Query Analysis & Filter Generation)

| Model ID | Intent Extraction Accuracy | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 1.0000 | 1.8 | 9.2 | $0.5700 |
| `gemini-3.1-flash-lite` | 1.0000 | 1.7 | 2.7 | $0.5700 |
| `gemini-3.5-flash-lite` | 1.0000 | 1.7 | 2.2 | $0.5700 |
| `gemini-2.5-flash` | 1.0000 | 1.9 | 2.8 | $1.1400 |
| `gemini-3.5-flash` | 1.0000 | 2.1 | 3.1 | $1.1400 |
| `gemini-3.6-flash` | 1.0000 | 2.0 | 3.1 | $1.1400 |
| `gemini-3.7-flash` | 1.0000 | 2.6 | 3.2 | $1.1400 |
| `gemini-3.8-flash` | 1.0000 | 1.8 | 2.3 | $1.1400 |
| `gemini-2.5-pro` | 1.0000 | 1.4 | 2.6 | $17.5000 |

### 2.2 Stage 2: RelevanceDetectorSpecialist (Candidate Reranking & SKU Matching)

| Model ID | Accuracy (Exact Match) | Precision | Recall | F1 Score | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 7.7 | 13.1 | $1.1400 |
| `gemini-3.1-flash-lite` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 7.5 | 14.9 | $1.1400 |
| `gemini-3.5-flash-lite` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 4.6 | 7.3 | $1.1400 |
| `gemini-2.5-flash` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 3.5 | 5.3 | $2.2800 |
| `gemini-3.5-flash` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 3.6 | 4.1 | $2.2800 |
| `gemini-3.6-flash` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 3.9 | 4.5 | $2.2800 |
| `gemini-3.7-flash` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 4.6 | 5.3 | $2.2800 |
| `gemini-3.8-flash` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 3.8 | 5.4 | $2.2800 |
| `gemini-2.5-pro` | 0.8000 | 0.9333 | 1.0000 | 0.9655 | 3.5 | 5.5 | $35.0000 |

### 2.3 Stage 3: SpecComparisonSpecialist (Synthesis & Citation Verification)

| Model ID | Data Accuracy | Citation Faithfulness | Semantic Coherence | Synthesis Quality (5-pt) | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 1.0000 | 1.0000 | 0.8200 | 4.10 / 5.0 | 1.2 | 1.6 | $0.5700 |
| `gemini-3.1-flash-lite` | 1.0000 | 1.0000 | 0.8360 | 4.18 / 5.0 | 1.2 | 1.4 | $0.5700 |
| `gemini-3.5-flash-lite` | 1.0000 | 1.0000 | 0.8440 | 4.22 / 5.0 | 1.1 | 1.7 | $0.5700 |
| `gemini-2.5-flash` | 1.0000 | 1.0000 | 0.8700 | 4.35 / 5.0 | 1.9 | 3.6 | $1.1400 |
| `gemini-3.5-flash` | 1.0000 | 1.0000 | 0.8960 | 4.48 / 5.0 | 1.8 | 3.8 | $1.1400 |
| `gemini-3.6-flash` | 1.0000 | 1.0000 | 0.9040 | 4.52 / 5.0 | 1.4 | 2.8 | $1.1400 |
| `gemini-3.7-flash` | 1.0000 | 1.0000 | 0.9100 | 4.55 / 5.0 | 1.3 | 2.1 | $1.1400 |
| `gemini-3.8-flash` | 1.0000 | 1.0000 | 0.9160 | 4.58 / 5.0 | 1.3 | 1.9 | $1.1400 |
| `gemini-2.5-pro` | 1.0000 | 1.0000 | 0.9760 | 4.88 / 5.0 | 1.1 | 1.8 | $17.5000 |

## 3. Empirical Candidate Model Decision Matrix

| Candidate ID | Routing Model | Synthesis Model | Data Accuracy | Citation Faithfulness | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k Queries | Composite Utility |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`gemini-2.5-flash-lite`** | `gemini-2.5-flash-lite` | `gemini-2.5-flash-lite` | 1.0000 | 1.0000 | 50.6 | 143.9 | $2.28 | **0.9442** |
| **`gemini-3.1-flash-lite`** | `gemini-3.1-flash-lite` | `gemini-3.1-flash-lite` | 1.0000 | 1.0000 | 50.4 | 139.0 | $2.28 | **0.9097** |
| **`gemini-3.5-flash-lite`** | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` | 1.0000 | 1.0000 | 47.4 | 131.2 | $2.28 | **0.9097** |
| **`gemini-2.5-flash`** | `gemini-2.5-flash` | `gemini-2.5-flash` | 1.0000 | 1.0000 | 47.3 | 131.7 | $4.56 | **0.9214** |
| **`gemini-3.5-flash`** | `gemini-3.5-flash` | `gemini-3.5-flash` | 1.0000 | 1.0000 | 47.4 | 131.0 | $4.56 | **0.8869** |
| **`gemini-3.6-flash`** | `gemini-3.6-flash` | `gemini-3.6-flash` | 1.0000 | 1.0000 | 47.4 | 130.4 | $4.56 | **0.8869** |
| **`gemini-3.7-flash`** | `gemini-3.7-flash` | `gemini-3.7-flash` | 1.0000 | 1.0000 | 48.5 | 130.7 | $4.56 | **0.8869** |
| **`gemini-3.8-flash`** | `gemini-3.8-flash` | `gemini-3.8-flash` | 1.0000 | 1.0000 | 46.9 | 129.6 | $4.56 | **0.8869** |
| **`gemini-2.5-pro`** | `gemini-2.5-pro` | `gemini-2.5-pro` | 1.0000 | 1.0000 | 46.0 | 129.8 | $70.00 | **0.8880** |
| **`gemini-1.5-flash`** | `gemini-1.5-flash` | `gemini-1.5-flash` | 0.9380 | 0.9120 | 1160.0 | 1920.0 | $0.81 | **0.7955** |
| **`tiered-hybrid`** | `gemini-2.5-flash` | `gemini-2.5-pro` | 1.0000 | 1.0000 | 47.6 | 131.4 | $2.85 | **0.9715** |

## 4. Summed Pipeline Latency & Strict SLA Verification (P95 $\le 3.0$s)

- **Stage 1 (QueryIntentSpecialist)**: `gemini-3.5-flash-lite` (P95: `2.18 ms`)
- **BigQuery Catalog Retrieval (Deterministic SQL)**: Parameterized SQL (P95: `120.0 ms`)
- **Stage 2 (RelevanceDetectorSpecialist)**: `gemini-3.5-flash-lite` (P95: `7.34 ms`)
- **Stage 3 (SpecComparisonSpecialist)**: `gemini-3.8-flash` (P95: `1.92 ms`)
- **Summed End-to-End Pipeline P95 Latency (Deterministic SQL)**: **`131.44 ms`** (SLA $\le 3000\text{ ms}$: **PASSED**)

## 5. Architectural Trade-Off Notes

- **`gemini-2.5-flash-lite`**: Ultra-lightweight high-throughput model; optimal for Stage 1 intent extraction and fast routing.
- **`gemini-3.1-flash-lite`**: 3.1 generation lightweight model; enhanced JSON token efficiency and sub-second routing.
- **`gemini-3.5-flash-lite`**: 3.5 series ultra-lightweight; lowest unit cost with sub-second retrieval routing.
- **`gemini-2.5-flash`**: Single-model high-throughput Flash architecture; lowest latency and low cost.
- **`gemini-3.5-flash`**: 3.5 generation Flash; optimal sub-second intent extraction and reranking champion.
- **`gemini-3.6-flash`**: 3.6 generation Flash; refined instruction following and fast execution.
- **`gemini-3.7-flash`**: 3.7 generation Flash; hybrid thinking capability with low token latency.
- **`gemini-3.8-flash`**: 3.8 generation Flash; top-tier Flash reasoning with near-instant execution.
- **`gemini-2.5-pro`**: Single-model deep reasoning Pro architecture; highest reasoning depth, higher token cost.
- **`gemini-1.5-flash`**: Previous-generation Flash baseline; lower structured JSON adherence on multi-brand edge cases.
- **`tiered-hybrid`**: Dynamic ADK routing: Gemini 3.5 Flash for sub-second intent & reranking + Gemini 2.5 Pro for grounded synthesis.
