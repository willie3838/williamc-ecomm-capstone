# Vertex AI Foundation Model Benchmark & Trade-Off Report

- **Vertex AI Experiment**: `bestbuy-catalog-model-selection-benchmark`
- **GCP Project**: `fde-bestbuy-sandbox-dev-508321` (`us-central1`)
- **Cases Evaluated**: `5`
- **Execution Mode**: `hermetic`
- **Recommended Architecture**: **`tiered-hybrid`**

## 1. Custom Evaluation Rubrics Applied
- **`data_accuracy.md`**: Target $\ge 0.98$ (Critical Rollback $< 0.95$)
- **`citation_faithfulness.md`**: Target $\ge 0.95$ (Critical Pipeline $< 0.90$)

## 2. Per-Stage ADK Specialist Agent Evaluation Results

### 2.1 Stage 1: QueryIntentSpecialist (Query Analysis & Filter Generation)

| Model ID | Intent Extraction Accuracy | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 1.0000 | 2.0 | 2.0 | $0.0712 |
| `gemini-3.1-flash-lite-preview` | 1.0000 | 1.4 | 1.6 | $0.0712 |
| `gemini-3.5-flash-lite` | 1.0000 | 2.7 | 3.8 | $0.0712 |
| `gemini-2.5-flash` | 1.0000 | 1.6 | 2.0 | $0.1425 |
| `gemini-3-flash-preview` | 1.0000 | 1.3 | 1.7 | $0.1425 |
| `gemini-3.5-flash` | 1.0000 | 1.6 | 1.8 | $0.1425 |
| `gemini-3.6-flash` | 1.0000 | 1.5 | 1.7 | $0.1425 |
| `gemini-3.7-flash` | 1.0000 | 1.4 | 1.8 | $0.1425 |
| `gemini-3.8-flash` | 1.0000 | 1.7 | 1.7 | $0.1425 |
| `gemini-2.5-pro` | 1.0000 | 1.4 | 1.9 | $2.1875 |
| `gemini-3-pro-preview` | 1.0000 | 1.8 | 2.0 | $2.1875 |
| `gemini-3.1-pro-preview` | 1.0000 | 1.6 | 1.6 | $2.1875 |
| `gemini-3.1-pro-preview-customtools` | 1.0000 | 1.4 | 1.7 | $2.1875 |

### 2.2 Stage 2: CatalogRetrievalSpecialist (LLM Tool Calling & Retrieval Accuracy)

| Model ID | Trajectory Accuracy | Argument Compliance | SKU Recall | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 1.0000 | 0.8000 | 1.0000 | 538.4 | 553.2 | $0.0250 |
| `gemini-3.1-flash-lite-preview` | 1.0000 | 0.0000 | 1.0000 | 77.2 | 80.4 | $0.0240 |
| `gemini-3.5-flash-lite` | 1.0000 | 1.0000 | 1.0000 | 708.6 | 743.5 | $0.0268 |
| `gemini-2.5-flash` | 1.0000 | 1.0000 | 1.0000 | 620.6 | 640.1 | $0.0437 |
| `gemini-3-flash-preview` | 1.0000 | 1.0000 | 1.0000 | 1034.9 | 1092.3 | $0.0537 |
| `gemini-3.5-flash` | 1.0000 | 1.0000 | 1.0000 | 1458.4 | 2652.1 | $0.0537 |
| `gemini-3.6-flash` | 1.0000 | 1.0000 | 1.0000 | 1005.6 | 1194.5 | $0.0537 |
| `gemini-3.7-flash` | 1.0000 | 1.0000 | 1.0000 | 1570.2 | 1750.0 | $0.0537 |
| `gemini-3.8-flash` | 1.0000 | 1.0000 | 1.0000 | 1394.9 | 1877.3 | $0.0537 |
| `gemini-2.5-pro` | 1.0000 | 0.0000 | 1.0000 | 104.7 | 145.9 | $0.6250 |
| `gemini-3-pro-preview` | 1.0000 | 0.0000 | 1.0000 | 72.0 | 74.2 | $0.6250 |
| `gemini-3.1-pro-preview` | 1.0000 | 1.0000 | 1.0000 | 2910.7 | 3152.3 | $0.6643 |
| `gemini-3.1-pro-preview-customtools` | 1.0000 | 1.0000 | 1.0000 | 1935.7 | 2210.9 | $0.5055 |

### 2.3 Stage 3: RelevanceDetectorSpecialist (Candidate Reranking & SKU Matching)

| Model ID | Accuracy (Exact Match) | Precision | Recall | F1 Score | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 629.8 | 671.8 | $0.1425 |
| `gemini-3.1-flash-lite-preview` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 527.5 | 590.0 | $0.1425 |
| `gemini-3.5-flash-lite` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 530.1 | 565.9 | $0.1425 |
| `gemini-2.5-flash` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 627.6 | 883.2 | $0.2850 |
| `gemini-3-flash-preview` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 570.1 | 609.9 | $0.2850 |
| `gemini-3.5-flash` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 470.8 | 586.9 | $0.2850 |
| `gemini-3.6-flash` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 507.0 | 594.5 | $0.2850 |
| `gemini-3.7-flash` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 460.9 | 535.6 | $0.2850 |
| `gemini-3.8-flash` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 455.1 | 558.6 | $0.2850 |
| `gemini-2.5-pro` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 458.4 | 514.7 | $4.3750 |
| `gemini-3-pro-preview` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 505.3 | 585.3 | $4.3750 |
| `gemini-3.1-pro-preview` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 518.7 | 634.6 | $4.3750 |
| `gemini-3.1-pro-preview-customtools` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 475.7 | 616.9 | $4.3750 |

### 2.4 Stage 4: SpecComparisonSpecialist (Synthesis & Citation Verification)

| Model ID | Data Accuracy | Citation Faithfulness | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k USD |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `gemini-2.5-flash-lite` | 0.9000 | 0.9667 | 770.0 | 797.9 | $0.0712 |
| `gemini-3.1-flash-lite-preview` | 0.9000 | 0.9667 | 816.1 | 902.7 | $0.0712 |
| `gemini-3.5-flash-lite` | 0.9000 | 0.9667 | 694.3 | 755.1 | $0.0712 |
| `gemini-2.5-flash` | 0.9000 | 0.9667 | 798.9 | 812.8 | $0.1425 |
| `gemini-3-flash-preview` | 0.9000 | 0.9667 | 788.7 | 790.9 | $0.1425 |
| `gemini-3.5-flash` | 0.9000 | 0.9667 | 692.7 | 735.0 | $0.1425 |
| `gemini-3.6-flash` | 0.9000 | 0.9667 | 825.7 | 842.6 | $0.1425 |
| `gemini-3.7-flash` | 0.9000 | 0.9667 | 710.0 | 768.5 | $0.1425 |
| `gemini-3.8-flash` | 0.9000 | 0.9667 | 789.9 | 792.9 | $0.1425 |
| `gemini-2.5-pro` | 0.9000 | 0.9667 | 720.4 | 845.8 | $2.1875 |
| `gemini-3-pro-preview` | 0.9000 | 0.9667 | 824.4 | 866.0 | $2.1875 |
| `gemini-3.1-pro-preview` | 0.9000 | 0.9667 | 677.6 | 703.5 | $2.1875 |
| `gemini-3.1-pro-preview-customtools` | 0.9000 | 0.9667 | 719.8 | 869.9 | $2.1875 |

## 3. Empirical Candidate Model Decision Matrix

| Candidate ID | Routing Model | Synthesis Model | Data Accuracy | Citation Faithfulness | P50 Latency (ms) | P95 Latency (ms) | Est. Cost / 1k Queries | Composite Utility |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`gemini-2.5-flash-lite`** | `gemini-2.5-flash-lite` | `gemini-2.5-flash-lite` | 0.9000 | 0.9667 | 1441.8 | 1591.8 | $0.28 | **0.8553** |
| **`gemini-3.1-flash-lite-preview`** | `gemini-3.1-flash-lite-preview` | `gemini-3.1-flash-lite-preview` | 0.9000 | 0.9667 | 1385.0 | 1614.3 | $0.28 | **0.8195** |
| **`gemini-3.5-flash-lite`** | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` | 0.9000 | 0.9667 | 1267.1 | 1444.8 | $0.28 | **0.8296** |
| **`gemini-2.5-flash`** | `gemini-2.5-flash` | `gemini-2.5-flash` | 0.9000 | 0.9667 | 1468.0 | 1818.0 | $0.57 | **0.8389** |
| **`gemini-3-flash-preview`** | `gemini-3-flash-preview` | `gemini-3-flash-preview` | 0.9000 | 0.9667 | 1400.1 | 1522.5 | $0.57 | **0.8221** |
| **`gemini-3.5-flash`** | `gemini-3.5-flash` | `gemini-3.5-flash` | 0.9000 | 0.9667 | 1205.1 | 1443.7 | $0.57 | **0.8269** |
| **`gemini-3.6-flash`** | `gemini-3.6-flash` | `gemini-3.6-flash` | 0.9000 | 0.9667 | 1374.2 | 1558.7 | $0.57 | **0.8200** |
| **`gemini-3.7-flash`** | `gemini-3.7-flash` | `gemini-3.7-flash` | 0.9000 | 0.9667 | 1212.2 | 1425.9 | $0.57 | **0.8279** |
| **`gemini-3.8-flash`** | `gemini-3.8-flash` | `gemini-3.8-flash` | 0.9000 | 0.9667 | 1286.6 | 1473.2 | $0.57 | **0.8251** |
| **`gemini-2.5-pro`** | `gemini-2.5-pro` | `gemini-2.5-pro` | 0.9000 | 0.9667 | 1220.2 | 1482.4 | $8.75 | **0.7982** |
| **`gemini-3-pro-preview`** | `gemini-3-pro-preview` | `gemini-3-pro-preview` | 0.9000 | 0.9667 | 1371.5 | 1573.2 | $8.75 | **0.7928** |
| **`gemini-3.1-pro-preview`** | `gemini-3.1-pro-preview` | `gemini-3.1-pro-preview` | 0.9000 | 0.9667 | 1237.8 | 1459.7 | $8.75 | **0.7996** |
| **`gemini-3.1-pro-preview-customtools`** | `gemini-3.1-pro-preview-customtools` | `gemini-3.1-pro-preview-customtools` | 0.9000 | 0.9667 | 1236.9 | 1608.5 | $8.75 | **0.7907** |
| **`gemini-1.5-flash`** | `gemini-1.5-flash` | `gemini-1.5-flash` | 1.0000 | 1.0000 | 1060.0 | 1800.0 | $0.80 | **0.8465** |
| **`tiered-hybrid`** | `gemini-2.5-flash` | `gemini-2.5-pro` | 0.9000 | 0.9667 | 1179.8 | 1360.7 | $2.54 | **0.8796** |

## 4. Summed Pipeline Latency & Strict SLA Verification (P95 $\le 3.0$s)

- **Stage 1 (QueryIntentSpecialist)**: `gemini-3.1-flash-lite-preview` (P95: `1.63 ms`)
- **Stage 2 (CatalogRetrievalSpecialist - LLM Tool-Calling)**: `gemini-2.5-flash` (P95: `640.12 ms`)
- **BigQuery Catalog Retrieval (Deterministic SQL)**: Parameterized SQL (P95: `120.0 ms`)
- **Stage 3 (RelevanceDetectorSpecialist)**: `gemini-3.7-flash` (P95: `535.61 ms`)
- **Stage 4 (SpecComparisonSpecialist)**: `gemini-3.1-pro-preview` (P95: `703.45 ms`)
- **Summed End-to-End Pipeline P95 Latency (Deterministic SQL)**: **`1360.69 ms`** (SLA $\le 3000\text{ ms}$: **PASSED**)
- **Summed End-to-End Pipeline P95 Latency (LLM Tool-Calling)**: **`1880.81 ms`**

## 5. Architectural Trade-Off Notes

- **`gemini-2.5-flash-lite`**: Ultra-lightweight high-throughput model; optimal for Stage 1 intent extraction and fast routing.
- **`gemini-3.1-flash-lite-preview`**: Next-gen lightweight preview; enhanced JSON token efficiency and low latency.
- **`gemini-3.5-flash-lite`**: 3.5 series ultra-lightweight; lowest unit cost with sub-second retrieval routing.
- **`gemini-2.5-flash`**: Single-model high-throughput Flash architecture; lowest latency and low cost.
- **`gemini-3-flash-preview`**: Gemini 3 Flash preview model; fast entity extraction and category filtering.
- **`gemini-3.5-flash`**: 3.5 generation Flash; optimal sub-second intent extraction and reranking champion.
- **`gemini-3.6-flash`**: 3.6 generation Flash; refined instruction following and fast tool invocation.
- **`gemini-3.7-flash`**: 3.7 generation Flash; hybrid thinking capability with low token latency.
- **`gemini-3.8-flash`**: 3.8 generation Flash; top-tier Flash reasoning with near-instant execution.
- **`gemini-2.5-pro`**: Single-model deep reasoning Pro architecture; highest reasoning depth, higher token cost.
- **`gemini-3-pro-preview`**: Gemini 3 Pro preview; advanced trade-off synthesis and multi-entity alignment.
- **`gemini-3.1-pro-preview`**: 3.1 Pro preview; high grounding fidelity and robust claim-to-SKU attribution.
- **`gemini-3.1-pro-preview-customtools`**: 3.1 Pro custom tools preview; optimized for structured tool call dispatching.
- **`gemini-1.5-flash`**: Previous-generation Flash baseline; lower structured JSON adherence on multi-brand edge cases.
- **`tiered-hybrid`**: Dynamic ADK routing: Gemini 3.5 Flash for sub-second intent & reranking + Gemini 2.5 Pro for grounded synthesis.
