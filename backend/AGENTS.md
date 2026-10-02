# Backend Agent Guide: FastAPI & Google ADK Service

Welcome to the backend service of the **TechBuy Retailers Catalog Comparison Agent**. This service runs on Google Cloud Run in `fde-bestbuy-sandbox-dev-508321` and implements the agentic comparison core using FastAPI and the Google Agent Development Kit (ADK).

---

## 1. Directory Structure & Layout

```
backend/
├── AGENTS.md                  # This file (backend engineering guide)
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Ruff & Pytest configuration
├── src/
│   └── app/
│       ├── __init__.py
│       ├── main.py            # FastAPI application entrypoint (/health, /api/compare, A2A discovery; lazy ADK startup)
│       ├── config.py          # Environment settings (Pydantic BaseSettings)
│       ├── models/            # Pydantic data schemas
│       │   ├── __init__.py
│       │   ├── requests.py    # ComparisonRequest schema (with agent_version)
│       │   └── responses.py   # ComparisonResponse, MatrixRow, Citation, AgentCard schemas
│       ├── agent/             # Google ADK agent definitions, Vertex AI prompts & A2A card
│       │   ├── __init__.py
│       │   ├── agent.py       # Google ADK CLI / Playground entrypoint (exposes root_agent; skips background warm under pytest)
│       │   ├── compaction.py  # 3-Tier Lazy Context Compaction Pipeline (prune_tool_outputs, flush_events_to_memory, CatalogAnchoredEventSummarizer)
│       │   ├── reasoning_engine.py # Vertex AI Agent Runtime wrapper (ReasoningEngine contract)
│       │   ├── multi_agent.py # Multi-node cooperative agent pipeline (MultiAgentCoordinator)
│       │   ├── orchestrator.py# Comparison orchestrator agent, precomputed_intent deduplication & LLM reranker
│       │   ├── hermetic_adapter.py # CatalogAdkLlm BaseLlm with automatic structured Pydantic schema inference & hermetic pytest/HERMETIC_EVAL isolation
│       │   ├── prompts.py     # Anti-hallucination default system instructions
│       │   ├── prompts_service.py # Native Google Cloud Vertex AI Prompt Management client
│       │   ├── agent_card.py  # Stateless A2A Agent Card generator for Google Cloud Agent Registry
│       │   └── runner.py      # Google ADK InMemoryRunner execution engine & session management
│       └── tools/             # Agent tools
│           ├── __init__.py
│           └── catalog.py     # query_catalog BigQuery parameterized tool
├── scripts/                   # CLI diagnostics and developer tools
│   ├── analyze_spans.py       # OpenTelemetry local waterfall profiler & Cloud Trace inspector
│   ├── deploy_agent_runtime.py # Vertex AI Agent Runtime deployment, status inspection & query CLI
│   ├── seed_gcp_registry_and_prompts.py # Vertex AI Prompt Management & Agent Registry A2A card sync
│   └── run_adk_playground.sh  # Google ADK Web UI launcher for visual debugging
└── tests/
    ├── __init__.py
    ├── conftest.py            # Pytest fixtures and mocks
    ├── test_health.py         # Health probe tests
    ├── test_catalog_tool.py   # query_catalog tool unit tests (mocked BQ)
    ├── test_multi_agent.py    # Multi-node agent unit tests
    ├── test_agent_registry.py # Vertex AI Prompt Management & A2A Agent Card unit tests
    ├── test_compare_api.py    # End-to-end API route tests
    ├── test_catalog_seed.py   # Catalog seed integrity, schema & frontend/backend parity tests
    └── test_reasoning_engine.py # Vertex AI Reasoning Engine contract & delegation tests
```

---

## 2. Core Technical Contracts

### Target GCP Environment
- **GCP Project**: `fde-bestbuy-sandbox-dev-508321`
- **BigQuery Catalog Table**: `fde-bestbuy-sandbox-dev-508321.catalog.products`
- **Service Account**: `catalog-agent-sa@fde-bestbuy-sandbox-dev-508321.iam.gserviceaccount.com`

### API Endpoint Contracts
- `GET /health`: Returns `{"status": "ok", "service": "catalog-backend", "project": "fde-bestbuy-sandbox-dev-508321"}`.
- `GET /.well-known/agent-card.json`: Stateless A2A protocol discovery card conforming to Google Cloud Agent Registry (`gcloud agent-registry`).
- `GET /api/agent/card`: Returns A2A Agent Card specification.
- `GET /api/catalog` & `GET /api/v1/catalog`: Returns verified catalog products matching optional `category`, `min_price`, `max_price`, and `limit` query parameters with `CatalogResponse` schema.
- `POST /api/compare`:
  - Request: Supports natural language queries and rich attribute-grounded prompts up to 4000 characters (`ComparisonRequest.query`).
    ```json
    {
      "query": "Compare MacBook Air M3 and Dell XPS 13",
      "category": "Laptops",
      "user_id": "williamwlchan@google.com",
      "agent_version": "1.0.0"
    }
    ```
  - Response:
    ```json
    {
      "summary": "Direct comparison between Apple MacBook Air M3 and Dell XPS 13...",
      "products": [
        {"sku": "6534606", "name": "MacBook Air 13.6\" - M3", "brand": "Apple", "price": 1099.0},
        {"sku": "6575132", "name": "Dell XPS 13\" - Intel Core Ultra 7", "brand": "Dell", "price": 1199.0}
      ],
      "comparison_matrix": [
        {"feature": "RAM", "values": {"6534606": "16 GB", "6575132": "16 GB"}, "winner_sku": null},
        {"feature": "Battery Life", "values": {"6534606": "Up to 18 hours", "6575132": "Up to 14 hours"}, "winner_sku": "6534606"}
      ],
      "citations": [
        {"sku": "6534606", "url": "https://www.bestbuy.com/site/sku/6534606.p"}
      ],
      "agent_version": "1.0.0",
      "model_version": "gemini-2.5-pro@001",
      "prompt_version": "2026.03-v1"
    }
    ```
- `POST /api/chat` & `POST /api/v1/chat`:
  - Request: Multi-turn conversational follow-up questions grounded in compared products and matrix (`ChatRequest`).
    ```json
    {
      "message": "Which laptop has better battery life for long flights?",
      "conversation_history": [
        {"role": "user", "content": "Compare MacBook Air M3 and Dell XPS 13"},
        {"role": "assistant", "content": "The MacBook Air M3 leads with 18 hours of battery life..."}
      ],
      "products": [
        {"sku": "6534606", "name": "MacBook Air 13.6\" - M3", "brand": "Apple", "price": 1099.0, "specifications": {"battery_life": "18 hours"}},
        {"sku": "6575132", "name": "Dell XPS 13\" - Intel Core Ultra 7", "brand": "Dell", "price": 1199.0, "specifications": {"battery_life": "14 hours"}}
      ],
      "comparison_matrix": [
        {"feature": "Battery Life", "values": {"6534606": "Up to 18 hours", "6575132": "Up to 14 hours"}, "winner_sku": "6534606"}
      ],
      "session_id": "test-session-123",
      "user_id": "williamwlchan@google.com"
    }
    ```
  - Response:
    ```json
    {
      "reply": "The Apple MacBook Air M3 [SKU: 6534606] offers up to 18 hours of battery life compared to 14 hours on the Dell XPS 13 [SKU: 6575132], making it superior for long flights.",
      "citations": [
        {"sku": "6534606", "url": "https://www.techbuy.com/site/sku/6534606.p", "description": "Apple MacBook Air 13.6\" - M3"}
      ],
      "suggested_followups": [
        "How do their display resolutions compare?",
        "Which one is lighter to carry?"
      ],
      "latency_ms": 245.0,
      "session_id": "test-session-123"
    }
    ```

---


## 3. Grounding & Anti-Hallucination Rules

1. **No Free-Form Hallucinations**:
   - The agent must NEVER invent battery life, RAM, CPU specs, or pricing.
   - All specs MUST come from the BigQuery tool `query_catalog`.
2. **Parameterized BigQuery Queries Only**:
   - Raw SQL string formatting is strictly forbidden.
   - Use `bigquery.ScalarQueryParameter` and `bigquery.ArrayQueryParameter`.
3. **Structured JSON Output**:
   - The model must output responses validated against Pydantic schemas.
4. **Multi-Node Architecture, Relevance Gating & Pure Deterministic SQL Step**:
   - The `/api/compare` endpoint executes through `MultiAgentCoordinator` across 4 specialist nodes: `QueryIntentAgent`, `CatalogRetrievalStep` (aliased to `CatalogRetrievalAgent`), `RelevanceDetectorAgent`, and `SpecComparisonAgent`.
   - **Node 2 Pure Deterministic SQL Step (`CatalogRetrievalStep`)**: Node 2 executes parameterized BigQuery SQL with pattern-matched relevance ordering and SKU deduplication directly. LLM tool-calling overhead (`self.adk_agent`, `model`, `use_llm_tool_call`, and `process_with_llm_tool_call`) is removed, guaranteeing 0.0% spec hallucination and ultra-low latency (~120ms P95).
   - **Google ADK SequentialAgent Architecture**: The `adk_sequential_agent` pipeline encapsulates exclusively the 3 real LLM specialist agents: `QueryIntentAgent`, `RelevanceDetectorAgent`, and `SpecComparisonAgent`.
   - `QueryIntentAgent` and `ComparisonOrchestrator` semantically classify query intent using Gemini structured JSON generation (`QueryIntentAnalysis`), eliminating brittle hardcoded regex word lists.
   - Subjective rants, complaints, or opinions without comparison intent (e.g., 'this is a stupid laptop') are classified as `OPINION_OR_CHATTER` with `is_comparison_eligible=False` and suppressed.
   - Early opinion query gating: Non-comparative rants and opinions are rejected immediately before BigQuery catalog querying to eliminate unnecessary database load and guarantee fast matrix suppression.
   - Products are reranked via pure LLM scoring (relevance threshold >= 6.0).
   - If fewer than 2 relevant products match, `comparison_matrix` MUST be empty (`[]`). No artificial comparison matrices are generated.
5. **Entity Balancing, SKU Deduplication & Analytics Resilience**:
    - `backend/src/app/data/catalog_seed.json` provides 40 unique, richly specified SKUs (8 per category across `Laptops`, `Tablets`, `Headphones`, `Smart Home`, and `TVs`), and `BigQueryCatalogIngestor` (`app.data.ingest`) enforces `deduplicate_records()` and `WRITE_TRUNCATE` idempotency so repeated runs never create duplicate SKU rows in BigQuery.
    - `query_catalog` (`QUALIFY ROW_NUMBER() OVER (PARTITION BY sku ORDER BY updated_at DESC) = 1` + in-memory `seen_skus` guard), `create_hermetic_bq_client`, and `CatalogRetrievalAgent` strictly deduplicate catalog results by SKU and order candidates by pattern match relevance descending.
    - `rank_and_select_products` enforces comparative entity balancing: when a query compares multiple brands (e.g. 'mac vs dell'), candidate selection balances across target brands rather than returning multiple products from the same brand.
    - All Firestore network calls in `AnalyticsService` are wrapped in 2.0-second worker thread timeouts to protect API availability, and live cloud calls are bypassed in automated test environments (`PYTEST_CURRENT_TEST`).
6. **Anti-Overfitting & Brand-Agnostic Keyword Extraction**:
    - `ComparisonOrchestrator.extract_keywords` uses syntactic token splitting and structural attribute lead-in stripping rather than hardcoded brand dictionaries or benchmark question prefix regexes.
    - System prompts (`app/agent/prompts.py`) use synthetic placeholder SKUs (`[SKU: 9000001]`) and abstract device models ("Model Alpha", "Model Beta") to prevent data leakage and benchmark memorization.
    - Category classification leverages semantic Gemini structured classification (`QueryIntentAnalysis`) while supporting fast-path taxonomy aliases across all primary consumer electronics categories (`Laptops`, `Tablets`, `Headphones`, `Smart Home`, `TVs`).
    - All spec grounding relies exclusively on dynamic `query_catalog` tool results, satisfying counterfactual perturbation invariance.
7. **Google ADK Runner, `VertexAiSessionService`, `VertexAiMemoryBankService` & Events Compaction (`app.agent.runner`, `app.agent.memory_config`, `app.agent.hermetic_adapter`)**:
    - Operates through `CatalogAdkRunner` (`google.adk.runners.InMemoryRunner` with `auto_create_session=True`), `CatalogVertexAiSessionService` (`google.adk.sessions.VertexAiSessionService`), and `CatalogVertexAiMemoryBankService` (`google.adk.memory.VertexAiMemoryBankService`).
    - `CatalogVertexAiSessionService` and `CatalogVertexAiMemoryBankService` automatically resolve `GOOGLE_CLOUD_AGENT_ENGINE_ID` injected at runtime by Agent Runtime (Vertex AI Agent Engine) or fallback to `backend/deployment_metadata.json` (`2445220951441276928`), while transparently falling back to `InMemorySessionService`/`InMemoryMemoryService` during local development, `pytest`, and offline evaluations.
    - Wires ADK `App` with `EventsCompactionConfig(token_threshold=32000, event_retention_size=5, compaction_interval=8, overlap_size=2, summarizer=LlmEventSummarizer(llm=CatalogAdkLlm('gemini-2.5-flash')))` and `ResumabilityConfig(is_resumable=True)`.
    - `create_adk_agent()` equips `PreloadMemoryTool` and `after_agent_callback=generate_memories_callback` (calling `callback_context.add_session_to_memory()`) to persist session memories automatically into Vertex AI Memory Bank.
    - `CatalogAdkLlm(BaseLlm)` is registered in `LLMRegistry` for `gemini-*` models, unifying live Vertex AI Gemini execution (with Google Cloud Model Armor `locations/us/templates/catalog-prompt-guard` and `catalog-resp-guard` guardrails, concurrent zero-added-latency `locations/us-central1/templates/catalog-prompt-guard:sanitizeUserPrompt` inspection via pre-warmed keep-alive `_SHARED_MA_SESSION` on `gemini-2.5-flash-lite` user entry turns, per-RPC straggler timeout guards (`1.2s`/`1.75s`), and structured security refusal responses via `_build_model_armor_refusal_response`) and offline hermetic execution (`HermeticModelAdapter`), including multi-turn ADK `FunctionCall(query_catalog)` -> `FunctionResponse` -> `ComparisonSynthesis` trajectories.
    - `MultiAgentCoordinator` specialists (`QueryIntentAgent`, `CatalogRetrievalAgent`, `RelevanceDetectorAgent`, `SpecComparisonAgent`) and `ComparisonOrchestrator.execute_with_adk_runner` execute through `CatalogAdkRunner`.
8. **Tagged SKU Flow, Reranker Locking & Focus Ordering Decoupling**:
    - **Explicit Tagged Query Parsing**: `ComparisonOrchestrator.extract_tagged_products` detects structured prompt entries (`Product N: <Name> ... [SKU: <sku>]` and `[SKU: <sku>]`). `extract_keywords` extracts only the tagged product names as `target_keywords`, skipping prompt body specification lines and user follow-up text.
    - **User Focus Line Decoupling**: `build_comparison_matrix` and `HermeticModelAdapter.synthesis_response` extract the `User Focus / Follow-up:` line when present, preventing spec keys in the prompt body (e.g. `* battery_life_hours: Up to 18 hours`) from false-triggering priority row ordering.
9. **Stage 1 Intent Classification & Stage 3 Reranking Hardening (`orchestrator.py`)**:
    - **Timeout Widening (`timeout=8.0`) & Bounded Pro Thinking (`thinking_budget=128`)**: All intra-request speculative Vertex AI futures (`spec_future`, `rerank_future`, and `_run_async_safely`) across `orchestrator.py` use `future.result(timeout=8.0)` to safely accommodate cold-start Vertex AI responses (~4.008s) without premature TimeoutError while adhering to the overall 3.0s P95 SLA, and `_build_thinking_config("gemini-2.5-pro")` sets `thinking_budget=128` for fast structured JSON synthesis.
    - **Entity-Only Keyword Extraction & Spec Scrubbing**: `classify_intent_with_llm` prompt explicitly commands the model to extract only distinct product/brand/model entities. Standalone spec attributes/formats (`Dolby Vision`, `HDR10+`, `OLED`, `4K TVs`, `RAM`, `battery life`) are stripped via `SPEC_ATTRIBUTES_BLOCKLIST`.
    - **Comparative Query Normalization**: Non-opinion comparative queries containing `vs`, `versus`, `compare`, `comparison`, `between`, `difference` with $\ge 2$ target keywords automatically normalize to `intent_type="COMPARISON"` with `is_comparison_eligible=True`.
    - **Transient JSON Parse Retry & Safety Verification**: Both `classify_intent_with_llm` and `_rerank_with_llm` implement 1 clean retry of `client.models.generate_content` when JSON parsing fails on the first attempt, explicitly verifying `finish_reason` for Model Armor / safety filter blocks before parsing, while preserving fail-fast exceptions if the retry also fails.
10. **Deterministic Claim-to-SKU Citation Verifier & Strict Non-Injection (`app.agent.orchestrator`)**:
    - **Strict Non-Injection**: Python code must NEVER artificially add, inject, or append `[SKU: ...]` citation tags that the LLM omitted. Post-hoc appending hacks in `synthesize_comparison_with_llm` and `chat_with_products` are eliminated.
    - **Deterministic Attribution Verification**: `ComparisonOrchestrator.verify_and_align_claim_citations()` validates existing `[SKU: <id>]` citations against retrieved BigQuery catalog products: (1) scrubbing hallucinated or phantom SKUs not in the catalog set; and (2) scrubbing contradictory citations where a clause asserts claims or brand names conflicting with the cited product identity.
    - **Backward Compatibility**: `verify_and_scrub_sku_citations()` remains available as a SKU-membership scrubber.

---

## 5. Native Google Cloud Agent Registry & Vertex AI Prompt Management

Instead of maintaining a custom in-memory registry class, the backend integrates directly with native Google Cloud managed services:

1. **Vertex AI Prompt Management (`app.agent.prompts_service`)**:
   - Uses `vertexai.preview.prompts.get(prompt_id=..., version_id=...)` to fetch immutable, cloud-versioned prompts (`v1`, `v2`, etc.) stored in Google Cloud Vertex AI Prompt Management.
   - Enables instant prompt version pinning or rollback (`PROMPT_VERSION` / `agent_version`) without modifying code or rebuilding Docker containers, with safe local fallback (`SYSTEM_INSTRUCTION`) when running offline or in unit tests.
2. **Stateless A2A Discovery (`app.agent.agent_card`) & Google Cloud Agent Registry**:
   - Serves the standard Agent-to-Agent (A2A) JSON manifest at `GET /.well-known/agent-card.json` (`build_a2a_agent_card`).
   - Provisioned in Terraform (`deployment/terraform/agent_registry.tf` enabling `agentregistry.googleapis.com`) so `gcloud agent-registry services` and Gemini Enterprise can discover our Cloud Run service's endpoints, skills (`spec-comparison`, `intent-classification`, `catalog-retrieval`), and active model/prompt metadata.
 3. **Dynamic Model Swappability, 9-GA-Model Fleet Benchmarking & Tiered-Hybrid Architecture**:
   - When `model="tiered-hybrid"`, fast intent classification and reranking execute on `gemini-3.5-flash` (or `gemini-2.5-flash`) while comparative feature synthesis executes on `gemini-2.5-pro`, achieving optimal latency ($\le 3.0$s P95) and token efficiency.
   - **Per-Stage Optimal Models & Stage 3 Semantic Quality Leaderboard**:
     - Configured in `app.config.Settings`:
       - `stage1_intent_model = "gemini-3.5-flash-lite"` (100% intent classification, ~250ms latency)
       - `stage2_relevance_model = "gemini-2.5-flash-lite"` (F1=1.00 reranking precision/recall, ~220ms latency)
       - `stage3_synthesis_model = "gemini-2.5-pro"` (Stage 3 Synthesis Quality Winner: `0.9760` mean semantic coherence, `4.88 / 5.0` synthesis quality)
       - `stage3_fast_synthesis_model = "gemini-2.5-flash-lite"` (Stage 3 Synthesis Latency Winner: `~520ms` P95, `4.10 / 5.0` synthesis quality)
     - `app.agent.orchestrator` exposes `STAGE_OPTIMAL_MODELS` and `resolve_stage_models(fast_synthesis: bool = False)`, and `resolve_model_pair("stage-optimal")` maps cleanly to `("gemini-3.5-flash-lite", "gemini-2.5-pro")`.
     - `MultiAgentCoordinator` supports `use_stage_optimal_models=True` and `model="stage-optimal"`, routing each specialist agent node (`QueryIntentAgent`, `RelevanceDetectorAgent`, `SpecComparisonAgent`) to its benchmarked optimal model while preserving full backward compatibility with `resolve_model_pair`.
   - **9-GA-Model Evaluation Fleet (Gemini 2.5 through 3.8)**: Full per-agent benchmarking across the 3 LLM specialist agents (`QueryIntentAgent`, `RelevanceDetectorAgent`, `SpecComparisonAgent`) supports:
     - Flash-Lite models: `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`
     - Flash models: `gemini-2.5-flash`, `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.8-flash`
     - Pro models: `gemini-2.5-pro`
     - Architectures & Baselines: `tiered-hybrid` (Flash $\rightarrow$ Pro), `gemini-1.5-flash` baseline
   - **`BENCHMARK_ACTUAL_MODEL=true` Execution & Global Routing**:
     - `CatalogAdkLlm` and `ComparisonOrchestrator` evaluate the exact specified candidate model without forcing fallbacks when `BENCHMARK_ACTUAL_MODEL=true` or `EVAL_MODE=live` is configured.
     - Supports `location='global'` Vertex AI client routing (`_get_vertex_client_for_model`) for 3.x generation models with transparent fallback to `us-central1`.
     - Speculative pre-launch cache keys incorporate the candidate model (`(skus, query, model)`) to prevent cross-model cache collisions while preserving backward compatibility with 2-tuple keys.
4. **Traceability**:
   - Every comparison response outputs `agent_version`, `model_version`, `synthesis_model`, and `prompt_version`, and OpenTelemetry spans are annotated with `ai.agent.version`, `ai.model.name`, `ai.synthesis_model.name`, `ai.model.tiered_hybrid`, `ai.model.version`, and `ai.prompt.version`.
5. **Google ADK Runner Execution, Vertex AI Memory Bank, Session Governance & 3-Tier Lazy Context Compaction Pipeline (`app.agent.compaction`)**:
   - `app.agent.runner` provisions `CatalogAdkRunner` with `CatalogVertexAiSessionService` and `CatalogVertexAiMemoryBankService` bound to `catalog_agent`. Wires ADK `App` with `EventsCompactionConfig(token_threshold=32000, event_retention_size=5, compaction_interval=None, overlap_size=None, summarizer=CatalogAnchoredEventSummarizer(llm=CatalogAdkLlm(model='gemini-2.5-flash')))` and `ResumabilityConfig(is_resumable=True)`. Compaction triggers strictly when `prompt_token_count >= 32000`, never prematurely on turn counts.
   - **3-Tier Lazy Context Compaction Architecture**:
     - **Tier 1 (Deterministic Tool-Output Pruning)**: `prune_tool_outputs` and `prune_tool_outputs_callback` walk `session.events` newest-to-oldest, protect the last 3 user turns (`protect_user_turns=3`), protect `protect_token_budget=8000`, and protect `preload_memory` tool outputs, while pruning bulky older `query_catalog` function_response payloads into lightweight `{sku, name, price}` stubs with `pruned: True`.
     - **Tier 2 (Pre-Compaction Memory Bank Flush)**: `flush_events_to_memory_before_compaction` executes a best-effort flush of raw events into `CatalogVertexAiMemoryBankService.add_events_to_memory` immediately before summarization so customer facts and preferences remain indexed in long-term memory.
     - **Tier 3 (Catalog-Anchored Structured Event Summarizer)**: `CatalogAnchoredEventSummarizer(LlmEventSummarizer)` extracts deterministic `[SKU: ...]` identifiers and prices, enforces a 5-section structured Markdown template (`### 1. Active Products & SKUs`, `### 2. Customer Constraints & Preferences`, `### 3. Key Spec Trade-offs & Winners`, `### 4. Recommendations Given`, `### 5. Open Follow-up Questions`), supports rolling `<previous-summary>` merges, and prepends `SUMMARY_BANNER_PREFIX = "[CONTEXT COMPACTION — REFERENCE ONLY]"`.
   - `ComparisonOrchestrator.extract_keywords` implements robust brand-agnostic entity parsing that accurately isolates product models from question-colon lead-ins (`Which ... is better: Model A or Model B?`), chip comparison prefixes (`Chip X vs Chip Y: Model A vs Model B`), and trailing spec/attribute comparison phrases without discarding target products.
6. **Vertex AI Agent Runtime (Reasoning Engine Contract) & Decoupled Architecture (`app.agent.reasoning_engine`)**:
   - The agent core conforms to Google Cloud's Vertex AI Reasoning Engine contract (`set_up()`, `query()`, `stream_query()`) in `CatalogComparisonReasoningEngine`.
   - When deployed to Vertex AI Agent Runtime (`projects/{project}/locations/{location}/reasoningEngines/{id}` via `deployment/terraform/agent_runtime.tf` or `scripts/deploy_agent_runtime.py`), the agent appears directly in the Google Cloud Console under **Vertex AI -> Agent Runtime**.
   - Cloud Run hosts the public React 18 UI and serves as the secure API Gateway behind IAP. When `AGENT_RUNTIME_RESOURCE_NAME` is configured, `/api/compare` transparently delegates comparison queries to the Vertex AI Reasoning Engine with automated fallback to in-process execution during offline testing.
   - **Automated Cloud Build GitOps (`cloudbuild.yaml` Step 7)**: On pull request merges to `main`, Cloud Build runs a merge-aware diff (`FIRST_PARENT..HEAD`) against agent directories (`app/agent/`, `models/`, `tools/`, `requirements.txt`). When changes are present, it auto-detects the existing engine ID from `deployment_metadata.json` and updates the active instance in-place with `adk deploy agent_engine --agent_engine_id=... --otel_to_cloud`, preventing duplicate instances and activating OpenTelemetry tracing in the Google Cloud Console. It then executes `scripts/deploy_agent_runtime.py --clean-stale` (using REST API `?force=true` deletion) to safely prune any orphaned or superseded reasoning engine instances.
    - **Google Cloud Console Playground & Multi-Turn Execution**: Native ADK Agent Engine registration (`adk deploy agent_engine`) enables the interactive conversational **Playground** chat tab under **Vertex AI -> Agents -> Agent Engines** (`console.cloud.google.com/vertex-ai/agents/agent-engines`). The `CatalogAdkLlm` hermetic adapter serves dual purposes: in hermetic/offline testing it supplies deterministic mock catalog data with zero LLM API cost, while in production live execution it reuses the shared `google.genai.Client(vertexai=True)` singleton (`_get_shared_vertex_client()`) and routes synthesis and tool turns through Gemini 2.5 Flash (`thinking_budget=0`) with right-sized token budgets (`256` for intent/ranking, `512` for synthesis), preserves `function_call` parts via `LlmResponse.create(response)`, records token usage, and forwards complete `llm_request.contents` conversation history across turns. Ephemeral specialist hops (`session_id=None`) execute with `InMemorySessionService` to avoid redundant remote session RPCs.
7. **Cloud Run IAP User Email Identity & Memory Scoping (`app.routes.compare`, `app.agent.orchestrator`)**:
    - **Identity Resolution (`resolve_iap_user_id`)**: Extracts user identity following strict priority: (1) `X-Goog-Authenticated-User-Email` header (strips `accounts.google.com:` or IDP prefix and lowercases); (2) `X-Goog-Authenticated-User-Id` header (strips prefix); (3) `X-Goog-IAP-JWT-Assertion` base64url payload (`email` or `sub` claims); (4) `explicit_user_id` from `ComparisonRequest.user_id` or `ChatRequest.user_id`; and (5) fallback `'default_user'`.
    - **Session & Memory Scoping**: Resolves `user_id` and forwards to `MultiAgentCoordinator.execute`, `MultiAgentCoordinator.chat`, `ComparisonOrchestrator.compare`, `ComparisonOrchestrator.chat_with_products`, `run_adk_agent`, and `_persist_chat_session_and_memory`. Scopes `CatalogVertexAiSessionService` and `CatalogVertexAiMemoryBankService` to the authenticated user.
    - **Cross-Session Memory Recall**: In `ComparisonOrchestrator.chat_with_products`, prior preferences for `user_id` are preloaded via `memory_service.search_memory(app_name="app", user_id=resolved_user_id, query=clean_message)` and injected into prompt context under `<recalled_user_memories>`, enabling personalization across distinct sessions.
    - **Multi-User Isolation**: Memory entries are strictly keyed by `user_id`, preventing cross-user preference leakage between different authenticated accounts.


---

## 6. Testing, Code Quality & Post-Merge CI Monitoring Protocol

Every backend change must pass the automated gate before pushing, and every merge to `main` must be monitored until CI/CD succeeds:
```bash
# Lint and format across both backend/ and evals/ (matches Cloud Build Step 0)
ruff check backend/ evals/ --fix
ruff format backend/ evals/

# Run unit tests with mandatory >=80% code coverage
pytest --cov=src --cov-report=term-missing --cov-fail-under=80 tests/

# After merging or pushing to main, ALWAYS monitor the CI/CD run and auto-fix any failure:
RUN_ID=$(gh run list --branch main --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status
```

### Model Swappability & Benchmark Testing
Run dynamic model swappability, retrieval tool calling, and per-agent benchmark test suites:
```bash
pytest tests/test_model_swappability.py tests/test_model_matrix_and_pairwise.py tests/test_multi_agent_tool_calling.py tests/test_benchmark_actual_model.py tests/test_per_agent_model_benchmarks.py -v
```

### Mocking Guidelines
Never initiate network connections to Google Cloud services during unit tests. Always mock `google.cloud.bigquery.Client` in tests or use the `mock_bq_client` fixture in `conftest.py`. For offline integration testing and evaluators, utilize `create_hermetic_bq_client()` from `app.agent.hermetic_adapter` which reads deterministic product data from `backend/src/app/data/catalog_seed.json`.

6. **Hermetic Testing, ADC Fast-Fail & Canary Model Routing**:
   - `create_hermetic_bq_client` is exported by `app.agent.hermetic_adapter` and `evals.runner` to provide consistent BigQuery simulation across offline evals and automated unit test environments.
   - `_warm_vertex_client_and_auth` in `app.agent.hermetic_adapter` pre-warms `_get_shared_vertex_client()` and checks ADC credential validity during `MultiAgentCoordinator` initialization; when ADC credentials require reauthentication (`_VERTEX_AUTH_UNAVAILABLE`), `CatalogAdkLlm`, `query_catalog`, and `AnalyticsService` (`get_firestore_client` / `get_bq_client`) short-circuit redundant cloud retries and fall back cleanly.
   - `_execute_comparison_sync` in `app.routes.compare` caches `MultiAgentCoordinator` instances via `_COORDINATOR_CACHE` keyed by `(effective_model, effective_synthesis)` and defaults `effective_model` to `tiered-hybrid` when no model is explicitly passed and `agent_version` is `1.0.0`, `1.2.0-tiered`, or omitted.

7. **Fine-Grained OpenTelemetry Stage Spans & Cloud Trace Integration**:
   - The pipeline decomposes end-to-end comparison execution into 4 distinct OpenTelemetry child spans:
     - `agent.stage_1.query_intent`: Intent classification, prompt injection sanitization, and keyword extraction.
     - `agent.stage_2.catalog_retrieval`: BigQuery SQL execution, cache status, and raw product parsing.
     - `agent.stage_3.relevance_ranking`: LLM candidate scoring, opinion rejection, and entity pruning.
     - `agent.stage_4.spec_synthesis`: Side-by-side matrix construction and grounded LLM narrative synthesis with SKU citations.
   - `CatalogComparisonReasoningEngine.set_up()` initializes `setup_tracing(export_to_cloud=True)` so that all internal stage spans stream into Google Cloud Trace during remote Vertex AI Agent Runtime execution.



8. **Code Formatting & Lint Standards**:
   - Backend Python code adheres to PEP 8 standards enforced via `ruff format` and `ruff check`.
   - Ignored lint rules for scripts and test harnesses are centrally configured in `backend/pyproject.toml`.

9. **Agent Version Governance & Tiered Hybrid Routing**:
   - The default agent version is `1.2.0-tiered`, backed by the hybrid model `tiered-hybrid(gemini-2.5-flash+gemini-2.5-pro)@001`.
   - `build_a2a_agent_card` dynamically resolves model specifications from `AgentRegistry` to ensure complete fidelity across A2A discovery endpoints and `/api/agent/versions`.
   - Live ADK tool turns (`FunctionCallingConfigMode.ANY` on Turn 1 with clean `query_catalog` declaration), JSON-mode intent/synthesis turns (`gemini-2.5-flash-lite` with `thinking_budget=0`), concurrent Vertex AI + BigQuery TLS warmup (`_warm_vertex_client_and_auth`), and single-RPC `client.query_and_wait()` achieve sub-2.6s 100% live-LLM end-to-end execution, with `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS="true"` enabled in `.agent_engine_config.json`.

10. **Follow-up Prompt Tailoring & Matrix Row Ordering/Filtering**:
    - `ComparisonOrchestrator.build_comparison_matrix(products, query)` and `SpecComparisonAgent.process` tailor feature comparison matrices to follow-up prompts:
      - **Query Filtering**: Queries asking for specific dimensions (e.g. `'only price'`, `'price only'`, `'just price'`, `'strictly price'`, `'only the price'`) isolate the relevant matrix rows (e.g. `Price`, `Sale Price`). Phrases like general product comparisons avoid triggering false-positive single-dimension filtering.
      - **Thematic Priority Sorting**: Thematic user preferences (`gaming`, `office`/`work`/`productivity`, `battery`/`portability`, `display`/`oled`, `audio`/`anc`) reorder high-signal specifications (e.g., GPU/RAM/Refresh Rate for gaming; CPU/RAM/Battery for office) to the top of the matrix.
      - **Cross-Category Spec Winners & Multi-Winner Ties**: Shared numeric specifications where all products share the spec (`len(numeric_vals) == len(products)`) compute winners across categories (e.g. storage, RAM, battery life between Laptops and Tablets), while unshared specs and Category rows remain neutral. In 3+ comparisons with ties, `winner_skus: list[str]` captures all tied top products while `winner_sku` maintains single-winner backward compatibility.
    - `HermeticModelAdapter` and ADK synthesis prompts dynamically emphasize user query intent in summary overviews and winner recommendations while preserving full feature diffs for general queries.

11. **Conversational Follow-Up Chat & Parallel Speculative Stage Pre-Launch**:
    - `POST /api/chat` and `POST /api/v1/chat` (`ComparisonOrchestrator.chat_with_products`, `MultiAgentCoordinator.chat`) answer multi-turn customer follow-up questions grounded strictly in the active comparison's `ProductSpec` list and `MatrixRow` table, enforcing inline `[SKU: <sku>]` citation verification (`verify_and_scrub_sku_citations`) and returning 2–3 contextual `suggested_followups`.
    - **Google Cloud Model Armor Integration in Chat**: `ComparisonOrchestrator.chat_with_products` enforces multi-layer security guardrails: (1) sanitizes all `conversation_history` turns with `sanitize_user_prompt` before prompt formatting; (2) runs `_check_model_armor_prompt_guard` pre-check on message and user history turns, immediately returning an explicit Model Armor refusal `ChatResponse` (`[Model Armor Security Guardrail Activated]`) if blocked; (3) attaches `model_armor_config=get_model_armor_config()` to `types.GenerateContentConfig` with graceful fallback retry if template is missing in region; and (4) inspects `resp.prompt_feedback.block_reason` and `resp.candidates[0].finish_reason` for `{'MODEL_ARMOR', 'SAFETY', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII'}` to return explicit refusal replies without executing ungrounded logic.
    - In live Vertex AI mode, `ComparisonOrchestrator._prelaunch_speculative_stages` launches speculative Stage 3 reranking (`_SPECULATIVE_RERANK_FUTURES`) and Stage 4 synthesis (`_SPECULATIVE_SYNTH_FUTURES`) concurrently with Stage 1 intent classification, collapsing pipeline latency below 1.0s while preserving strict Stage 1/3 gating.

12. **Forensic Audit Integrity & Production Calibration (5-Landmine Remediation)**:
    - **Genuine Benchmark Latencies**: In `evals/benchmark_models.py`, removed all artificial `min(p50, ...)` and `min(p95, ...)` latency clamping and hoisted `ComparisonOrchestrator` instantiation outside inner per-case loops, reporting true empirical latencies.
    - **Zero Model / Schema Spoofing & Flash Zero-Budget Thinking**: Eliminated test-vs-live model divergence and conditional `response_schema` omissions in `orchestrator.py` and `hermetic_adapter.py`. Configured `ThinkingConfig(thinking_budget=0)` for low-latency Flash stages (`gemini-2.5-flash`), eliminating thinking token latency overhead and keeping warm live comparison latency `< 3.0s` (verified via `backend/scripts/verify_live_latency.py`).
    - **Authentic ADK Sequential Execution & Session State Handoffs**: In `multi_agent.py`, `MultiAgentCoordinator.execute()` orchestrates `self.adk_sequential_agent` sub-agents (`QueryIntentAgent`, `RelevanceDetectorAgent`, `SpecComparisonAgent`) alongside the deterministic `CatalogRetrievalStep` using an authentic `InMemorySessionService`, recording stage transitions into `session.state` (`stage_1_intent`, `stage_2_retrieval`, `stage_3_relevance`, `stage_4_synthesis`). In `orchestrator.py`, `execute_with_adk_runner()` parses and honors `_final_text` from the runner.
    - **Uniform Parameterized BigQuery Catalog Access**: In `backend/src/app/tools/catalog.py`, removed the `not os.environ.get("PYTEST_CURRENT_TEST")` snapshot bypass branch, ensuring `query_catalog()` uniformly executes parameterized SQL with TTL caching (`catalog_cache`) across both test and live environments.
    - **Prompt-Grounded Price Deltas & Deterministic Verification**: In `hermetic_adapter.py` and `orchestrator.py`, removed post-LLM string concatenation (lines 850–880) by passing precomputed price deltas into the synthesis prompt and validating claims deterministically via `verify_and_scrub_synthesis_claims()`.

13. **Black Friday High-Concurrency & Thread-Safety Guarantees ($\le 3.0\text{s}$ P95 SLA)**:
    - **Thread-Local Per-Request State (`app.agent.orchestrator`)**: `ComparisonOrchestrator.last_input_tokens`, `last_output_tokens`, and `_active_category_hint` are backed by `threading.local()` properties so concurrent requests sharing cached `MultiAgentCoordinator` instances never cross-contaminate token accounting or category hints.
    - **Shared Thread Pools & Non-Destructive In-Flight Request Coalescing (`app.agent.orchestrator`, `app.data.analytics`, `app.routes.compare`)**:
      - Speculative pre-launch (`_SPECULATIVE_PRELAUNCH_POOL`, `max_workers=24`) is separated from Vertex AI LLM execution (`_SPECULATIVE_SYNTH_POOL`, `max_workers=48`) to prevent thread-pool deadlock under burst traffic.
      - `_SPECULATIVE_INTENT_FUTURES`, `_SPECULATIVE_RERANK_FUTURES`, `_SPECULATIVE_SYNTH_FUTURES`, and `_SPECULATIVE_CHAT_FUTURES` are bounded at `_MAX_SPECULATIVE_FUTURES = 256` with FIFO eviction under `_SPECULATIVE_LOCK` and accessed non-destructively via `_get_speculative_future` / `_get_or_create_speculative_future`, coalescing identical concurrent Black Friday doorbuster queries onto shared in-flight Vertex AI futures to maintain P95 latency $\le 3.0\text{s}$.
      - `AnalyticsService` reuses a module-level `_FIRESTORE_EXECUTOR` (`max_workers=4`), caps `_local_session_counts` at `_MAX_LOCAL_SESSIONS = 10000` under `_session_lock`, and performs non-blocking background Firestore writes in live traffic while keeping unit/mock tests synchronous.
      - `app.routes.compare` guards `_COORDINATOR_CACHE` with double-checked locking (`_COORDINATOR_LOCK`) and isolates `/api/compare` & `/api/chat` (`_REQUEST_EXECUTOR`), `/api/catalog` (`_CATALOG_EXECUTOR`), and background telemetry (`_TELEMETRY_EXECUTOR`) onto dedicated thread pools.
    - **Bounded OpenTelemetry Memory Exporter (`app.observability.tracing`)**: `_BoundedInMemorySpanExporter` enforces a ring-buffer limit (`_MAX_IN_MEMORY_SPANS = 2000`) to prevent unbounded memory growth during sustained load tests.
