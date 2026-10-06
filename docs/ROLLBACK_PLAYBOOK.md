# Prompt & Model Rollback Playbook 🛠️🔄

This operational runbook provides step-by-step instructions for rolling back or switching **Vertex AI Prompt Management versions** and **Gemini model versions** across each stage of the **TechBuy Retailers Catalog Comparison Agent** without rebuilding container images.

---

## 1. Stage-by-Stage Prompt & Model Governance Matrix

Prompt Management and Model Selection are **strictly decoupled**:
- **Prompts** are governed in [Vertex AI Prompt Management](https://console.cloud.google.com/vertex-ai/studio/saved-prompts?project=fde-bestbuy-sandbox-dev-508321) (`us-central1`) and defined in [`backend/src/app/agent/prompts.py`](../backend/src/app/agent/prompts.py).
- **Models** are governed via stage-level environment variables in [`backend/src/app/config.py`](../backend/src/app/config.py) with automatic regional/tier failover in [`backend/src/app/agent/orchestrator.py`](../backend/src/app/agent/orchestrator.py).

| Pipeline Stage | Vertex AI Prompt Name & GCP ID | Prompt Version Env Var | Prompt ID Env Var | Model Selection Env Var | Default Model |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Global System Grounding** | `catalog-comparison-system-prompt` (`6969351484559327232`) | `SYSTEM_PROMPT_VERSION` *(falls back to `PROMPT_VERSION`)* | `VERTEX_PROMPT_ID` | `GEMINI_MODEL` | `gemini-2.5-flash` |
| **Stage 1: Query Intent & Entity Extraction** | `stage1-query-intent-prompt` (`1204743961525092352`) | `STAGE1_PROMPT_VERSION` | `STAGE1_PROMPT_ID` | `STAGE1_INTENT_MODEL` | `gemini-3.5-flash-lite` |
| **Stage 2: BigQuery SQL Retrieval** | *(Deterministic SQL — 0 LLM tokens)* | N/A | N/A | N/A | Parameterized SQL |
| **Stage 3: Candidate Relevance Reranking** | `stage3-relevance-rerank-prompt` (`7625751130248577024`) | `STAGE3_PROMPT_VERSION` | `STAGE3_PROMPT_ID` | `STAGE2_RELEVANCE_MODEL` *(or `STAGE3_RELEVANCE_MODEL`)* | `gemini-2.5-flash-lite` |
| **Stage 4 (Call 1): Narrative Synthesis** | `stage4-spec-synthesis-prompt` (`121628251142488064`) | `STAGE4_PROMPT_VERSION` | `STAGE4_PROMPT_ID` | `STAGE3_SYNTHESIS_MODEL` *(or `STAGE4_SYNTHESIS_MODEL`)* / `STAGE3_FAST_SYNTHESIS_MODEL` | `gemini-2.5-pro` (`flash-lite` fast path) |
| **Stage 4 (Call 2): Matrix Row Winners** | *(Inline compact spec-row winner prompt)* | N/A | N/A | `STAGE4_MATRIX_WINNERS_MODEL` | `gemini-2.5-flash` |
| **Stage 5: Multi-Turn Follow-Up Chat** | `multi-turn-followup-chat-prompt` (`7445607145153757184`) | `CHAT_PROMPT_VERSION` | `CHAT_PROMPT_ID` | `STAGE5_CHAT_MODEL` *(or `GEMINI_MODEL`)* | `gemini-2.5-flash` |

---

## 2. Playbook A: Rolling Back or Switching Prompt Versions

### Option A1 — Instant UI Rollback in GCP Console (Zero Redeploy, ~60s)
When Cloud Run is configured with `ENABLE_VERTEX_PROMPT_REGISTRY=true` and `PROMPT_VERSION=latest`, [`prompts_service.py`](../backend/src/app/agent/prompts_service.py) caches the `"latest"` prompt for **60 seconds** (`PROMPT_CACHE_TTL_SECONDS=60`) and then refreshes from Vertex AI.

1. Open **[Vertex AI Studio → Prompt Management](https://console.cloud.google.com/vertex-ai/studio/saved-prompts?project=fde-bestbuy-sandbox-dev-508321)** (Region: `us-central1`).
2. Click the stage prompt you want to roll back (e.g., `stage4-spec-synthesis-prompt`).
3. Click the **Version History** icon in the right-hand toolbar.
4. Select the target historical version (e.g., `Version 1`) and click **Restore version** (or edit the prompt text and click **Save → Save as new version**).
5. Within **60 seconds**, all live Cloud Run instances automatically pick up the restored/new `latest` version—no Cloud Run redeployment required.

---

### Option A2 — Pin a Specific Prompt Version via Cloud Run Env Var (Zero Code Rebuild, ~30s)
When you pin an explicit version number (e.g., `1` or `2`), [`prompts_service.py`](../backend/src/app/agent/prompts_service.py) locks onto that immutable version in GCP and ignores any newer versions (`v3`, `v4`, or UI edits) until unpinned.

#### Pin or Roll Back a Single Stage Prompt (e.g., Lock Stage 4 Synthesis to Version `1`)
```bash
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="ENABLE_VERTEX_PROMPT_REGISTRY=true,STAGE4_PROMPT_VERSION=1"
```

#### Pin Multiple Stage Prompts Simultaneously
```bash
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="ENABLE_VERTEX_PROMPT_REGISTRY=true,SYSTEM_PROMPT_VERSION=1,STAGE1_PROMPT_VERSION=1,STAGE3_PROMPT_VERSION=1,STAGE4_PROMPT_VERSION=1,CHAT_PROMPT_VERSION=1"
```

#### Unpin & Return All Stages to Live `latest` (60s TTL Auto-Refresh)
```bash
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="ENABLE_VERTEX_PROMPT_REGISTRY=true,PROMPT_VERSION=latest" \
  --remove-env-vars="SYSTEM_PROMPT_VERSION,STAGE1_PROMPT_VERSION,STAGE3_PROMPT_VERSION,STAGE4_PROMPT_VERSION,CHAT_PROMPT_VERSION"
```

#### Emergency Local Fallback (Bypass GCP Prompt Registry Completely)
If Vertex AI Prompt Management is unreachable or you want to force the immutable local templates compiled into [`backend/src/app/agent/prompts.py`](../backend/src/app/agent/prompts.py):
```bash
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="ENABLE_VERTEX_PROMPT_REGISTRY=false"
```

---

### Option A3 — GitOps Prompt Update & Version Creation (~2 mins)
[`backend/scripts/seed_gcp_registry_and_prompts.py`](../backend/scripts/seed_gcp_registry_and_prompts.py) is **diff-aware and idempotent**:
- It compares each prompt in [`backend/src/app/agent/prompts.py`](../backend/src/app/agent/prompts.py) against the latest version stored in GCP.
- It **only creates a new version (`v2`, `v3`, ...)** when the prompt text actually changes.

```bash
cd backend
# 1. Edit prompt template(s) in src/app/agent/prompts.py
# 2. Sync to GCP (only modified prompts get a new version number):
PYTHONPATH=src uv run python scripts/seed_gcp_registry_and_prompts.py --skip-registry
```

---

## 3. Playbook B: Rolling Back or Switching Gemini Models per Stage

Model selection is governed from a **single source of truth**: [`resolve_stage_models()`](../backend/src/app/agent/orchestrator.py) + [`backend/src/app/config.py`](../backend/src/app/config.py). Every stage reads its environment variable dynamically at runtime and falls back to the benchmark-validated default in `config.py`. When Cloud Run delegates to the remote Vertex AI Reasoning Engine (`reasoningEngines/2445220951441276928`), Cloud Run automatically forwards the resolved `stage1_model`, `stage2_model`, and `stage3_model` in the request payload—so updating Cloud Run env vars takes effect across the entire pipeline immediately without redeploying the Reasoning Engine.

### Option B1 — Temporary Local Override (Terminal / `.env`)
```bash
# Override any stage model locally:
export STAGE1_INTENT_MODEL="gemini-2.5-flash"          # Stage 1: Query Intent (default: gemini-3.5-flash-lite)
export STAGE2_RELEVANCE_MODEL="gemini-2.5-flash"       # Stage 3: Relevance Reranking (default: gemini-2.5-flash-lite)
export STAGE3_SYNTHESIS_MODEL="gemini-2.5-flash-lite"  # Stage 4 Call 1: Narrative Synthesis (default: gemini-2.5-pro)
export STAGE4_MATRIX_WINNERS_MODEL="gemini-2.5-flash"  # Stage 4 Call 2: Matrix Winners (default: gemini-2.5-flash)
export STAGE5_CHAT_MODEL="gemini-2.5-flash-lite"       # Stage 5: Follow-Up Chat (default: gemini-2.5-flash)

# Revert local overrides back to code defaults:
unset STAGE1_INTENT_MODEL STAGE2_RELEVANCE_MODEL STAGE3_SYNTHESIS_MODEL STAGE4_MATRIX_WINNERS_MODEL STAGE5_CHAT_MODEL
```

### Option B2 — Switch or Roll Back Individual Stage Models on Cloud Run (~15s, Zero Rebuild)

#### 1. Switch Stage 1 (Query Intent) Model
```bash
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="STAGE1_INTENT_MODEL=gemini-2.5-flash"
```

#### 2. Switch Stage 3 (Candidate Relevance Reranking) Model
```bash
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="STAGE2_RELEVANCE_MODEL=gemini-2.5-flash"
```

#### 3. Switch Stage 4 (Comparative Synthesis) Models (Call 1 Narrative & Call 2 Matrix Winners)
```bash
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="STAGE3_SYNTHESIS_MODEL=gemini-2.5-flash,STAGE4_MATRIX_WINNERS_MODEL=gemini-2.5-flash-lite"
```

#### 4. Switch Stage 5 (Multi-Turn Follow-Up Chat) & Global Fallback Model
```bash
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="STAGE5_CHAT_MODEL=gemini-2.5-flash-lite,GEMINI_MODEL=gemini-2.5-flash"
```

#### 5. Restore Default Benchmark-Optimal Model Fleet Configuration
```bash
# Either remove custom env var overrides so Cloud Run uses config.py defaults:
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --remove-env-vars="STAGE1_INTENT_MODEL,STAGE2_RELEVANCE_MODEL,STAGE3_SYNTHESIS_MODEL,STAGE4_MATRIX_WINNERS_MODEL,STAGE5_CHAT_MODEL"

# Or explicitly pin the default stage-optimal fleet:
gcloud run services update catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --update-env-vars="GEMINI_MODEL=gemini-2.5-flash,STAGE1_INTENT_MODEL=gemini-3.5-flash-lite,STAGE2_RELEVANCE_MODEL=gemini-2.5-flash-lite,STAGE3_SYNTHESIS_MODEL=gemini-2.5-pro,STAGE3_FAST_SYNTHESIS_MODEL=gemini-2.5-flash-lite,STAGE4_MATRIX_WINNERS_MODEL=gemini-2.5-flash,STAGE5_CHAT_MODEL=gemini-2.5-flash,AGENT_VERSION=1.2.0-tiered"
```

---

## 4. Playbook C: Per-Request or Traffic-Level Rollback

### 1. Per-Request Model / Agent Version Override (No Env Change Needed)
Callers can override `agent_version`, `model`, or `synthesis_model` on any individual `POST /api/compare` request:
```bash
curl -X POST "https://catalog-comparison-service-ocj5dik5ra-uc.a.run.app/api/compare" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Compare MacBook Air M3 vs Dell XPS 13",
    "agent_version": "1.1.0-flash",
    "model": "gemini-2.5-flash",
    "synthesis_model": "gemini-2.5-flash"
  }'
```

### 2. Cloud Run Revision Traffic Rollback (~15s)
To roll back the entire Cloud Run service (container image + env vars) to the previous known-good revision:
```bash
# 1. List recent revisions
gcloud run revisions list \
  --service=catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --limit=5

# 2. Route 100% of traffic to the target revision
gcloud run services update-traffic catalog-comparison-service \
  --project=fde-bestbuy-sandbox-dev-508321 \
  --region=us-central1 \
  --to-revisions=<REVISION_NAME>=100
```

---

## 5. Post-Rollback Verification Checklist

Run these 3 checks after any prompt or model rollback to confirm the active configuration:

```bash
# 1. Verify active agent & prompt versions via /api/agent/versions
curl -s "https://catalog-comparison-service-ocj5dik5ra-uc.a.run.app/api/agent/versions" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" | jq .

# 2. Verify A2A Agent Card metadata (/.well-known/agent-card.json)
curl -s "https://catalog-comparison-service-ocj5dik5ra-uc.a.run.app/.well-known/agent-card.json" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" | jq .metadata

# 3. Verify live comparison response telemetry fields (agent_version, model_version, prompt_version)
curl -s -X POST "https://catalog-comparison-service-ocj5dik5ra-uc.a.run.app/api/compare" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"query": "MacBook Air M3 vs Dell XPS 13"}' \
  | jq '{agent_version, model_version, synthesis_model, prompt_version, latency_ms}'
```
