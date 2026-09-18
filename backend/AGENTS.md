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
│       ├── agent/             # Google ADK agent definitions & registry
│       │   ├── __init__.py
│       │   ├── multi_agent.py # Multi-node cooperative agent pipeline (MultiAgentCoordinator)
│       │   ├── orchestrator.py# Comparison orchestrator agent & LLM reranker
│       │   ├── prompts.py     # Anti-hallucination system instructions
│       │   └── registry.py    # Google Cloud Agent Registry & A2A Version Manager
│       └── tools/             # Agent tools
│           ├── __init__.py
│           └── catalog.py     # query_catalog BigQuery parameterized tool
└── tests/
    ├── __init__.py
    ├── conftest.py            # Pytest fixtures and mocks
    ├── test_health.py         # Health probe tests
    ├── test_catalog_tool.py   # query_catalog tool unit tests (mocked BQ)
    ├── test_multi_agent.py    # Multi-node agent unit tests
    ├── test_agent_registry.py # Agent Registry & A2A versioning unit tests
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
- `GET /.well-known/agent-card.json`: A2A protocol discovery card conforming to Google Cloud Agent Registry.
- `GET /api/agent/card`: Returns versioned Agent Card specification (e.g. `?version=1.1.0-flash`).
- `GET /api/agent/versions`: Returns all registered agent versions with active default, model, and prompt versions.
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
    - `AnalyticsService` maintains an in-memory session counter fallback per `session_id`, ensuring session comparison counts reliably increment across queries even if Firestore is offline.
    - All Firestore network calls in `AnalyticsService` are wrapped in 2.0-second worker thread timeouts to protect API availability, and live cloud calls are bypassed in automated test environments (`PYTEST_CURRENT_TEST`).

---

## 5. Google Cloud Agent Registry & A2A Built-In Versioning

The backend integrates an enterprise **Agent Registry** (`app.agent.registry`) implementing the **Agent-to-Agent (A2A)** specification.

### Immutable Version Releases & Dynamic Model Swappability
Each release couples:
- `version`: Semantic version (e.g. `1.0.0`, `1.1.0-flash`, `1.2.0-tiered`).
- `model`: Gemini foundation model identifier (`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-1.5-flash`, `tiered-hybrid`).
- `synthesis_model`: Optional dedicated model for comparison narrative synthesis (e.g. `gemini-2.5-pro` in `tiered-hybrid` mode).
- `model_version`: Exact pinned model release (`gemini-2.5-pro@001`, `gemini-2.5-flash@001`, `tiered-hybrid(gemini-2.5-flash+gemini-2.5-pro)@001`).
- `prompt_version`: Pinned prompt version (`2026.03-v1`, `2026.03-v2`).
- `system_instruction`: Exact grounding system instructions for the version.
- `skills`: Declared agent capabilities (`spec-comparison`, `intent-classification`, `catalog-retrieval`).

`ComparisonOrchestrator` and `MultiAgentCoordinator` support runtime and constructor `model` and `synthesis_model` injection via `resolve_model_pair` and `create_adk_agent`. When `model="tiered-hybrid"`, fast intent classification and reranking execute on `gemini-2.5-flash` while feature synthesis executes on `gemini-2.5-pro`.

### Discovery & Side-by-Side Execution
1. **A2A Discovery**: Any service or agent can introspect capabilities via `GET /.well-known/agent-card.json` or `GET /api/agent/card?version=1.1.0-flash`.
2. **Version Listing**: `GET /api/agent/versions` lists all active and canary releases.
3. **Execution Routing**: Clients pass optional `"agent_version"`, `"model"`, and `"synthesis_model"` in `POST /api/compare`. If omitted, the active production default (`1.0.0`) is used.
4. **Sub-second Rollback**: Switching the active release requires changing `is_default` in the registry without container rebuilds or pipeline delays.
5. **Traceability**: Every comparison response outputs `agent_version`, `model_version`, `synthesis_model`, and `prompt_version`, and the OpenTelemetry root span is annotated with `ai.agent.version`, `ai.model.name`, `ai.synthesis_model.name`, `ai.model.tiered_hybrid`, `ai.model.version`, and `ai.prompt.version`.

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

### Mocking Guidelines
Never initiate network connections to Google Cloud services during unit tests. Always mock `google.cloud.bigquery.Client` in tests or use the `mock_bq_client` fixture in `conftest.py`.

