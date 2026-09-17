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
│       ├── main.py            # FastAPI application entrypoint (/health, /api/compare)
│       ├── config.py          # Environment settings (Pydantic BaseSettings)
│       ├── models/            # Pydantic data schemas
│       │   ├── __init__.py
│       │   ├── requests.py    # ComparisonRequest schema
│       │   └── responses.py   # ComparisonResponse, MatrixRow, Citation schemas
│       ├── agent/             # Google ADK agent definitions
│       │   ├── __init__.py
│       │   ├── multi_agent.py # Multi-node cooperative agent pipeline (MultiAgentCoordinator)
│       │   ├── orchestrator.py# Comparison orchestrator agent & LLM reranker
│       │   └── prompts.py     # Anti-hallucination system instructions
│       └── tools/             # Agent tools
│           ├── __init__.py
│           └── catalog.py     # query_catalog BigQuery parameterized tool
└── tests/
    ├── __init__.py
    ├── conftest.py            # Pytest fixtures and mocks
    ├── test_health.py         # Health probe tests
    ├── test_catalog_tool.py   # query_catalog tool unit tests (mocked BQ)
    ├── test_multi_agent.py    # Multi-node agent unit tests
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
- `POST /api/compare`:
  - Request:
    ```json
    {
      "query": "Compare MacBook Air M3 and Dell XPS 13",
      "category": "Laptops"
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
      ]
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
   - Subjective rants, complaints, or opinions without comparison intent (e.g., 'this is a stupid laptop') are detected and rejected.
   - Products are reranked via pure LLM scoring (relevance threshold >= 6.0).
   - If fewer than 2 relevant products match, `comparison_matrix` MUST be empty (`[]`). No artificial comparison matrices are generated.

---

## 4. Testing & Code Quality Protocol

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
