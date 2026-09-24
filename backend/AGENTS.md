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
│       ├── main.py            # FastAPI application entrypoint (/health, /api/compare, A2A discovery)
│       ├── config.py          # Environment settings (Pydantic BaseSettings)
│       ├── models/            # Pydantic data schemas
│       │   ├── __init__.py
│       │   ├── requests.py    # ComparisonRequest schema (with agent_version)
│       │   └── responses.py   # ComparisonResponse, MatrixRow, Citation, AgentCard schemas
│       ├── agent/             # Google ADK agent definitions, Vertex AI prompts & A2A card
│       │   ├── __init__.py
│       │   ├── agent.py       # Google ADK CLI / Playground entrypoint (exposes root_agent)
│       │   ├── reasoning_engine.py # Vertex AI Agent Runtime wrapper (ReasoningEngine contract)
│       │   ├── multi_agent.py # Multi-node cooperative agent pipeline (MultiAgentCoordinator)
│       │   ├── orchestrator.py# Comparison orchestrator agent, precomputed_intent deduplication & LLM reranker
│       │   ├── hermetic_adapter.py # CatalogAdkLlm BaseLlm with automatic structured Pydantic schema inference
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
│   └── run_adk_playground.sh  # Google ADK Web UI launcher for visual debugging
└── tests/
    ├── __init__.py
    ├── conftest.py            # Pytest fixtures and mocks
    ├── test_health.py         # Health probe tests
    ├── test_catalog_tool.py   # query_catalog tool unit tests (mocked BQ)
    ├── test_multi_agent.py    # Multi-node agent unit tests
    ├── test_agent_registry.py # Vertex AI Prompt Management & A2A Agent Card unit tests
    ├── test_compare_api.py    # End-to-end API route tests
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
- `POST /api/compare`:
  - Request:
    ```json
    {
      "query": "Compare MacBook Air M3 and Dell XPS 13",
      "category": "Laptops",
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
4. **Multi-Node Architecture & Relevance Gating**:
   - The `/api/compare` endpoint executes through `MultiAgentCoordinator` across 4 specialist nodes: `QueryIntentAgent`, `CatalogRetrievalAgent`, `RelevanceDetectorAgent`, and `SpecComparisonAgent`.
   - `QueryIntentAgent` and `ComparisonOrchestrator` semantically classify query intent using Gemini structured JSON generation (`QueryIntentAnalysis`), eliminating brittle hardcoded regex word lists.
   - Subjective rants, complaints, or opinions without comparison intent (e.g., 'this is a stupid laptop') are classified as `OPINION_OR_CHATTER` with `is_comparison_eligible=False` and suppressed.
   - Early opinion query gating: Non-comparative rants and opinions are rejected immediately before BigQuery catalog querying to eliminate unnecessary database load and guarantee fast matrix suppression.
   - Products are reranked via pure LLM scoring (relevance threshold >= 6.0).
   - If fewer than 2 relevant products match, `comparison_matrix` MUST be empty (`[]`). No artificial comparison matrices are generated.
5. **Entity Balancing, SKU Deduplication & Analytics Resilience**:
    - `query_catalog` and `CatalogRetrievalAgent` strictly deduplicate catalog results by SKU, preventing duplicate products from appearing in candidate lists.
    - `rank_and_select_products` enforces comparative entity balancing: when a query compares multiple brands (e.g. 'mac vs dell'), candidate selection balances across target brands rather than returning multiple products from the same brand.
    - All Firestore network calls in `AnalyticsService` are wrapped in 2.0-second worker thread timeouts to protect API availability, and live cloud calls are bypassed in automated test environments (`PYTEST_CURRENT_TEST`).
6. **Anti-Overfitting & Brand-Agnostic Keyword Extraction**:
    - `ComparisonOrchestrator.extract_keywords` uses syntactic token splitting and structural attribute lead-in stripping rather than hardcoded brand dictionaries or benchmark question prefix regexes.
    - System prompts (`app/agent/prompts.py`) use synthetic placeholder SKUs (`[SKU: 9000001]`) and abstract device models ("Model Alpha", "Model Beta") to prevent data leakage and benchmark memorization.
    - Category classification leverages semantic Gemini structured classification (`QueryIntentAnalysis`) while supporting fast-path taxonomy aliases across all primary consumer electronics categories (`Laptops`, `Tablets`, `Headphones`, `Smart Home`, `TVs`).
    - All spec grounding relies exclusively on dynamic `query_catalog` tool results, satisfying counterfactual perturbation invariance.
7. **Google ADK Runner & `VertexAiSessionService` Integration (`app.agent.runner`, `app.agent.hermetic_adapter`)**:
    - Operates through `CatalogAdkRunner` (`google.adk.runners.InMemoryRunner` with `auto_create_session=True`) and `CatalogVertexAiSessionService` (`google.adk.sessions.VertexAiSessionService`).
    - `CatalogVertexAiSessionService` automatically resolves `GOOGLE_CLOUD_AGENT_ENGINE_ID` injected at runtime by Agent Runtime (Vertex AI Agent Engine) to persist sessions via `vertexai.Client.aio.agent_engines.sessions`, while transparently falling back to `InMemorySessionService` during local development, `pytest`, and offline evaluations.
    - `CatalogAdkLlm(BaseLlm)` is registered in `LLMRegistry` for `gemini-*` models, unifying live Vertex AI Gemini execution (with Model Armor & safety settings) and offline hermetic execution (`HermeticModelAdapter`), including multi-turn ADK `FunctionCall(query_catalog)` -> `FunctionResponse` -> `ComparisonSynthesis` trajectories.
    - `MultiAgentCoordinator` specialists (`QueryIntentAgent`, `CatalogRetrievalAgent`, `RelevanceDetectorAgent`, `SpecComparisonAgent`) and `ComparisonOrchestrator.execute_with_adk_runner` execute through `CatalogAdkRunner`.

---

## 5. Native Google Cloud Agent Registry & Vertex AI Prompt Management

Instead of maintaining a custom in-memory registry class, the backend integrates directly with native Google Cloud managed services:

1. **Vertex AI Prompt Management (`app.agent.prompts_service`)**:
   - Uses `vertexai.preview.prompts.get(prompt_id=..., version_id=...)` to fetch immutable, cloud-versioned prompts (`v1`, `v2`, etc.) stored in Google Cloud Vertex AI Prompt Management.
   - Enables instant prompt version pinning or rollback (`PROMPT_VERSION` / `agent_version`) without modifying code or rebuilding Docker containers, with safe local fallback (`SYSTEM_INSTRUCTION`) when running offline or in unit tests.
2. **Stateless A2A Discovery (`app.agent.agent_card`) & Google Cloud Agent Registry**:
   - Serves the standard Agent-to-Agent (A2A) JSON manifest at `GET /.well-known/agent-card.json` (`build_a2a_agent_card`).
   - Provisioned in Terraform (`deployment/terraform/agent_registry.tf` enabling `agentregistry.googleapis.com`) so `gcloud agent-registry services` and Gemini Enterprise can discover our Cloud Run service's endpoints, skills (`spec-comparison`, `intent-classification`, `catalog-retrieval`), and active model/prompt metadata.
3. **Dynamic Model Swappability & Tiered-Hybrid Architecture**:
   - `ComparisonOrchestrator` and `MultiAgentCoordinator` support runtime and constructor `model` and `synthesis_model` injection via `resolve_model_pair`.
   - When `model="tiered-hybrid"`, fast intent classification and reranking execute on `gemini-2.5-flash` while comparative feature synthesis executes on `gemini-2.5-pro`, achieving optimal latency ($\le 3.0$s P95) and token efficiency.
4. **Traceability**:
   - Every comparison response outputs `agent_version`, `model_version`, `synthesis_model`, and `prompt_version`, and OpenTelemetry spans are annotated with `ai.agent.version`, `ai.model.name`, `ai.synthesis_model.name`, `ai.model.tiered_hybrid`, `ai.model.version`, and `ai.prompt.version`.
5. **Google ADK Runner Execution & Robust Keyword Extraction**:
   - `app.agent.runner` provisions an `InMemoryRunner` with `InMemorySessionService` bound to `catalog_agent`. `ComparisonOrchestrator.execute_with_adk_runner` executes queries through ADK's native runner lifecycle, collecting tool calls (`query_catalog`) and synthesized grounded narrative responses.
   - `ComparisonOrchestrator.extract_keywords` implements robust brand-agnostic entity parsing that accurately isolates product models from question-colon lead-ins (`Which ... is better: Model A or Model B?`), chip comparison prefixes (`Chip X vs Chip Y: Model A vs Model B`), and trailing spec/attribute comparison phrases without discarding target products.
6. **Vertex AI Agent Runtime (Reasoning Engine Contract) & Decoupled Architecture (`app.agent.reasoning_engine`)**:
   - The agent core conforms to Google Cloud's Vertex AI Reasoning Engine contract (`set_up()`, `query()`, `stream_query()`) in `CatalogComparisonReasoningEngine`.
   - When deployed to Vertex AI Agent Runtime (`projects/{project}/locations/{location}/reasoningEngines/{id}` via `deployment/terraform/agent_runtime.tf` or `scripts/deploy_agent_runtime.py`), the agent appears directly in the Google Cloud Console under **Vertex AI -> Agent Runtime**.
   - Cloud Run hosts the public React 18 UI and serves as the secure API Gateway behind IAP. When `AGENT_RUNTIME_RESOURCE_NAME` is configured, `/api/compare` transparently delegates comparison queries to the Vertex AI Reasoning Engine with automated fallback to in-process execution during offline testing.
   - **Automated Cloud Build GitOps (`cloudbuild.yaml` Step 7)**: On pull request merges to `main`, Cloud Build runs a merge-aware diff (`FIRST_PARENT..HEAD`) against agent directories (`app/agent/`, `models/`, `tools/`, `requirements.txt`). When changes are present, it auto-detects the existing engine ID from `deployment_metadata.json` and updates the active instance in-place with `adk deploy agent_engine --agent_engine_id=... --otel_to_cloud`, preventing duplicate instances and activating OpenTelemetry tracing in the Google Cloud Console. It then executes `scripts/deploy_agent_runtime.py --clean-stale` (using REST API `?force=true` deletion) to safely prune any orphaned or superseded reasoning engine instances.
   - **Google Cloud Console Playground & Multi-Turn Execution**: Native ADK Agent Engine registration (`adk deploy agent_engine`) enables the interactive conversational **Playground** chat tab under **Vertex AI -> Agents -> Agent Engines** (`console.cloud.google.com/vertex-ai/agents/agent-engines`). The `CatalogAdkLlm` hermetic adapter serves dual purposes: in hermetic/offline testing it supplies deterministic mock catalog data with zero LLM API cost, while in production live execution it wraps `google.genai.Client(vertexai=True)` against Gemini 2.5 Pro, preserves `function_call` parts via `LlmResponse.create(response)`, records token usage, and forwards complete `llm_request.contents` conversation history across turns, preventing blank responses and tool-calling loops. The system prompt defines explicit catalog retrieval protocol rules (single/double call max, closest model fallback) to prevent redundant queries when user mentions unlisted model years.


---

## 6. Testing & Code Quality Protocol

Every backend change must pass the automated gate before pushing:
```bash
# Lint and format
ruff check . --fix
ruff format .

# Run unit tests with mandatory >=80% code coverage
pytest --cov=src --cov-report=term-missing --cov-fail-under=80 tests/
```

### Model Swappability & Benchmark Testing
Run dynamic model swappability and pairwise evaluation test suites:
```bash
pytest tests/test_model_swappability.py tests/test_model_matrix_and_pairwise.py -v
```

### Mocking Guidelines
Never initiate network connections to Google Cloud services during unit tests. Always mock `google.cloud.bigquery.Client` in tests or use the `mock_bq_client` fixture in `conftest.py`. For offline integration testing and evaluators, utilize `create_hermetic_bq_client()` from `app.agent.hermetic_adapter` which reads deterministic product data from `backend/src/app/data/catalog_seed.json`.

6. **Hermetic Testing & Canary Model Routing**:
   - `create_hermetic_bq_client` is exported by `app.agent.hermetic_adapter` and `evals.runner` to provide consistent BigQuery simulation across offline evals and automated unit test environments.
   - `_execute_comparison_sync` in `app.routes.compare` defaults `effective_model` to `tiered-hybrid` only when no model is explicitly passed and `agent_version` is `1.0.0` or omitted, preserving specialized canary variant configurations (`1.1.0-flash`).

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
