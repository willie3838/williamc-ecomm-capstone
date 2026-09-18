# Backend Agent Guide: FastAPI & Google ADK Service

Welcome to the backend service of the **Best Buy Catalog Comparison Agent**. This service runs on Google Cloud Run in `fde-bestbuy-sandbox-dev-508321` and implements the agentic comparison core using FastAPI and the Google Agent Development Kit (ADK).

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
│       │   ├── multi_agent.py # Multi-node cooperative agent pipeline (MultiAgentCoordinator)
│       │   ├── orchestrator.py# Comparison orchestrator agent & LLM reranker
│       │   ├── prompts.py     # Anti-hallucination default system instructions
│       │   ├── prompts_service.py # Native Google Cloud Vertex AI Prompt Management client
│       │   ├── agent_card.py  # Stateless A2A Agent Card generator for Google Cloud Agent Registry
│       │   └── runner.py      # Google ADK InMemoryRunner execution engine & session management
│       └── tools/             # Agent tools
│           ├── __init__.py
│           └── catalog.py     # query_catalog BigQuery parameterized tool
└── tests/
    ├── __init__.py
    ├── conftest.py            # Pytest fixtures and mocks
    ├── test_health.py         # Health probe tests
    ├── test_catalog_tool.py   # query_catalog tool unit tests (mocked BQ)
    ├── test_multi_agent.py    # Multi-node agent unit tests
    ├── test_agent_registry.py # Vertex AI Prompt Management & A2A Agent Card unit tests
    └── test_compare_api.py    # End-to-end API route tests
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
7. **Google ADK Runner Integration (`app.agent.runner`)**:
    - Operates through `google.adk.runners.InMemoryRunner` and `google.adk.sessions.InMemorySessionService`.
    - Exposes `get_adk_runner()`, `create_catalog_runner()`, and `catalog_runner` bound to `root_agent` (`catalog_comparison_orchestrator`).
    - Exposes `run_adk_agent(query, session_id=...)` for asynchronous event streaming and multi-turn state tracking.
    - `ComparisonOrchestrator.execute_with_adk_runner` bridges orchestrator pipelines directly through the ADK Runner execution lifecycle.

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
Never initiate network connections to Google Cloud services during unit tests. Always mock `google.cloud.bigquery.Client` in tests or use the `mock_bq_client` fixture in `conftest.py`.


