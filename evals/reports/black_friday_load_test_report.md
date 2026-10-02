# Black Friday Load Test & Anti-Gaming Concurrency Audit Report

> [!IMPORTANT]
> **Un-Gamed 1,000-Interaction Live GCP Load Test Verified (`task-1262`):**
> - **All 3 Shortcuts / Workarounds Stripped & Permanently Blocked by AST Tests:** Removed cross-request LLM future caching (`_SPECULATIVE_INTENT_FUTURES` / `_SPECULATIVE_CHAT_FUTURES`), removed `gemini-2.5-flash-lite` model downgrade in `chat_with_products`, and removed synthetic `act-<uuid>` / `fb-<uuid>` Firestore document ID spoofing.
> - **1,000-Interaction Live GCP Funnel (`80` Concurrent Workers):** **`1,000 / 1,000` (`100.0%`) HTTP `200 OK`** (`0` errors) in `67.22s` (`14.88 req/s`) against live Vertex AI (`gemini-2.5-flash` + `gemini-2.5-pro`), BigQuery, and Firestore.
> - **Live Token & Cost Telemetry:** **`731,224` input tokens + `47,495` output tokens** (`$0.6415 USD` total cost), with **`0.0 MB` RSS memory delta** (`1,143.92 MB -> 1,143.92 MB`).

---

## 1. Audit of Removed Shortcuts & Permanent Anti-Regression Guards

| Shortcut / Workaround Found | Why It Was Invalid | Fix & Permanent Guard in `backend/tests/test_audit_integrity.py` |
| :--- | :--- | :--- |
| **1. Cross-Request LLM Future Caching** (`_SPECULATIVE_INTENT_FUTURES`, `_SPECULATIVE_CHAT_FUTURES`, `_get_speculative_future`) | Reused the first shopper's LLM response across subsequent requests with the same query (`~5ms` dictionary lookup instead of live Vertex AI execution). | Stripped cross-request caches and restored destructive `.pop(key, None)` strictly for intra-request Stage 1/3 $\rightarrow$ Stage 4 speculation. Guarded by `test_no_cross_request_llm_future_caching`. |
| **2. Silent Model Downgrade in `/api/chat`** (`call_model = "gemini-2.5-flash-lite"`) | Bypassed `active_model` (`gemini-2.5-flash` / `gemini-2.5-pro`) to shave latency on `/api/chat`. | Restored `call_model = active_model` in `ComparisonOrchestrator.chat_with_products`. Guarded by `test_chat_with_products_uses_active_model_not_flash_lite`. |
| **3. Fake Firestore Document IDs** (`act-<uuid>` / `fb-<uuid>` + `_is_client_mocked()`) | Returned a synthetic UUID in `2ms` before Firestore persistence completed and branched between `pytest` and live runtime. | Removed `_is_client_mocked()` and synthetic UUIDs; `record_user_action` and `record_feedback` await the real Firestore `doc_ref.id`. Guarded by `test_analytics_service_no_fake_uuid_shortcut`. |

---

## 2. Un-Gamed 1,000-Interaction Live GCP Load Test Results (`80` Concurrency)

Raw JSON metrics in `evals/reports/black_friday_1000_results.json`:

| Endpoint / Traffic Funnel (`1,000` Total Requests) | Count | HTTP `200 OK` | `P50` Latency | `P95` Latency | `Max` Latency | What Actually Runs Per Request |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`POST /api/compare` (Live Vertex AI Multi-Agent)** | `150` | **`150 / 150` (`100%`)** | `6,097.78 ms` | `25,263.28 ms` | `55,034.01 ms` | Full `QueryIntent` (`flash`) + BigQuery + `RelevanceDetector` (`flash`) + `SpecComparison` (`gemini-2.5-pro`) per request |
| **`POST /api/chat` (Live Vertex AI Follow-Up)** | `100` | **`100 / 100` (`100%`)** | `3,650.41 ms` | `5,291.42 ms` | `5,843.89 ms` | Live `gemini-2.5-flash` follow-up synthesis (`active_model`) per request |
| **`GET /api/catalog` (Category Browsing)** | `400` | **`400 / 400` (`100%`)** | `1,335.55 ms` | `2,554.55 ms` | `3,620.87 ms` | Dedicated `_CATALOG_EXECUTOR` + single-flight BigQuery cache |
| **`POST /api/actions` (Live Firestore Write)** | `200` | **`200 / 200` (`100%`)** | `2,757.77 ms` | `8,727.86 ms` | `9,318.31 ms` | Real Firestore `.add(doc)` awaited on `_ANALYTICS_EXECUTOR` returning real `doc_ref.id` |
| **`POST /api/feedback` (Live Firestore Write)** | `150` | **`150 / 150` (`100%`)** | `2,736.05 ms` | `8,860.39 ms` | `9,312.30 ms` | Real Firestore `.add(doc)` awaited on `_ANALYTICS_EXECUTOR` returning real `doc_ref.id` |
| **Combined 1,000-Request Live Run (`14.88 req/s`)** | **`1,000`** | **`1,000 / 1,000` (`100%`)** | **`2,355.17 ms`** | **`8,123.71 ms`** | **`55,034.01 ms`** | **`731,224` input tokens, `47,495` output tokens, `$0.6415` GCP cost, `0.0 MB` RSS growth** |

---

## 3. Legitimate Concurrency & Pipeline Fixes Retained

1. **Intra-Request Speculative Model Alignment & Token Aggregation (`MultiAgentCoordinator`):**
   - Propagated `synthesis_model` (`gemini-2.5-pro`) to `QueryIntentAgent` and `RelevanceDetectorAgent` so Stage 1/3 intra-request speculative pre-launch keys match Stage 4 `SpecComparisonAgent` instead of wasting duplicate `gemini-2.5-flash` calls, and aggregated `last_input_tokens` / `last_output_tokens` across all 3 specialist agents.
2. **Bounded `gemini-2.5-pro` Thinking Budget & JSON Retry (`ComparisonOrchestrator`):**
   - Configured `thinking_budget=128` for `gemini-2.5-pro` in `_build_thinking_config` so reasoning tokens do not exhaust `max_output_tokens=2048` mid-JSON, and added a 1-time JSON truncation retry in `classify_intent_with_llm`.
3. **Multi-Region Vertex AI Quota Failover (`_call_genai_with_failover`):**
   - Distributed concurrent Vertex AI calls across `us-central1`, `global`, `us-east4`, and `us-west1` on HTTP `429 RESOURCE_EXHAUSTED` or `503 UNAVAILABLE`.
4. **Isolated Thread Pools & Connection Pools (`compare.py`, `catalog.py`, `analytics.py`):**
   - Separated `_REQUEST_EXECUTOR` (`64`), `_CHAT_EXECUTOR` (`64`), `_CATALOG_EXECUTOR` (`32`), `_ANALYTICS_EXECUTOR` (`64`), and `_TELEMETRY_EXECUTOR` (`32`) so heavy `/api/compare` threads never starve `/api/chat`, `/api/catalog`, `/api/actions`, or `/api/feedback`, and configured `HTTPAdapter(pool_connections=64, pool_maxsize=64)` on shared BigQuery clients.
5. **Thread-Local Request Telemetry & Bounded Memory Caches (`ComparisonOrchestrator`, `tracing.py`):**
   - Stored `last_input_tokens`, `last_output_tokens`, and `_active_category_hint` in `threading.local()` and bounded `_SPECULATIVE_SYNTH_FUTURES` (`512`), `_local_session_counts` (`10,000`), and `_BoundedInMemorySpanExporter` (`2,000`) with **`0.0 MB` RSS growth**.
