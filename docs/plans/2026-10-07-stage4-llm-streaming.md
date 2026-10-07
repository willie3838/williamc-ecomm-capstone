# Stage 4 LLM Streaming & Instant Matrix Progressive Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `develop-feature` (`spawn_swarm.py`), `superpowers:subagent-driven-development`, or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream Stage 4 (`agent.stage_4.spec_synthesis`) LLM calls and pre-synthesis comparison matrices over Server-Sent Events (`POST /api/compare/stream`) so customers see verified products and the deterministic comparison matrix in ~150ms TTFB, followed by real-time token-by-token streaming of the AI comparison summary and recommendations.

**Architecture:** After Stage 1 (`QueryIntentAgent`) and Stage 2 (`CatalogRetrievalStep`) complete (~120–250ms), `MultiAgentCoordinator.execute_stream()` immediately computes the deterministic comparison matrix (<0.1ms) and emits an initial `matrix_ready` SSE event so the React UI renders `ProductCard`s and `ComparisonTable` immediately without waiting for Stage 4 LLM generation. Stage 4 (`ComparisonOrchestrator.stream_synthesize_comparison_with_llm()`) then invokes `client.models.generate_content_stream()` (with concurrent `MatrixWinnerAgent` when customer preferences are present), incrementally extracting `"summary"` and `"recommendations"` from the in-flight JSON token stream to emit `synthesis_chunk` and `matrix_updated` SSE events before finalizing with a citation-scrubbed and Model-Armor-verified `complete` event.

**Tech Stack:** Python 3.11+, FastAPI (`StreamingResponse`, SSE `text/event-stream`), Google GenAI SDK (`generate_content_stream`), Google ADK 2.0, React 18, TypeScript, Tailwind CSS, Vitest, Pytest.

**Spec:** User request: "in the ecomm repo can you implement a feature to stream the llm calls from stage 4 so the latency seems fast. come up with a plan"

---

## Global Constraints

- **Perceived TTFB Target**: Initial `matrix_ready` SSE event (products + deterministic comparison matrix + citations) must flush within $\le 250\text{ ms}$ on warm requests; total end-to-end stream completion must remain $\le 3.0\text{ seconds}$ P95.
- **Zero Hallucination & Strict Citation Scrubbing**: All streamed chunks and the final `complete` payload must pass `verify_and_align_claim_citations()` so phantom or contradicted `[SKU: ...]` tags never render.
- **Model Armor Security Guardrails**: If Model Armor blocks the prompt or streamed response (`SecurityViolationError`), emit an SSE `error` / blocked refusal state and never leak unsafe output.
- **Full Backward Compatibility**: Existing synchronous `POST /api/compare` (and `/api/v1/compare`) endpoints, `MultiAgentCoordinator.execute()`, and `ComparisonOrchestrator.synthesize_comparison_with_llm()` must remain 100% backward-compatible for evaluations, A2A callers, and existing unit tests.
- **Zero Un-documented Changes**: Update `ARCHITECTURE.md`, `backend/AGENTS.md`, and `frontend/AGENTS.md` in the same PR so `backend/tests/test_docs_sync.py` passes.
- **Test Coverage**: Backend (`pytest --cov=src --cov-fail-under=80`) and frontend (`npm test`) suites must pass with $\ge 80\%$ coverage and zero `ruff` / TypeScript lint errors.

## Review Focus

1. **Incomplete JSON Token Stream Parsing**: `generate_content_stream` yields partial JSON strings like `{"summary": "The MacBook Air [SKU: 6534606]` before the closing quote or `"recommendations"` key arrives. `_extract_partial_synthesis_fields()` must cleanly extract in-progress string values with escaped characters (`\"`, `\n`) without raising `JSONDecodeError`.
2. **Trailing Incomplete `[SKU:` Tag Suppression During Streaming**: If a chunk ends mid-citation (e.g. `"The MacBook Air [SKU: 653"`), the partial tag suffix must be held back until the closing `]` arrives so raw broken bracket fragments never flicker in the UI.
3. **Mock & Fallback Compatibility (`generate_content_stream` Absent)**: Unit test mocks that only configure `client.models.generate_content` (and not `generate_content_stream`) must transparently fall back to single-chunk yielding in `_call_genai_stream_with_failover()`.
4. **Parallel Preference Matrix Winners (`matrix_updated`)**: When a query contains user preferences (e.g. `"for gaming"`), `_run_matrix_winners_llm` runs in parallel on `_SPECULATIVE_SYNTH_POOL` and emits a `matrix_updated` event as soon as `spec_winners` resolves.
5. **Frontend Stream Fallback in Tests**: If `fetch` in existing `App.test.tsx` tests returns a standard JSON response or mocks `compareProducts`, `compareProductsStream` must seamlessly handle or fall back without breaking existing Vitest tests.

---

## File Structure

| Action | Path | Responsibility |
| :--- | :--- | :--- |
| **Modify** | `backend/src/app/agent/orchestrator.py` | Add `_extract_partial_synthesis_fields()`, `_call_genai_stream_with_failover()`, and `stream_synthesize_comparison_with_llm()` yielding incremental Stage 4 synthesis chunks and parallel matrix winner updates. |
| **Modify** | `backend/src/app/agent/multi_agent.py` | Add `SpecComparisonAgent.process_stream()` and `MultiAgentCoordinator.execute_stream()` yielding `matrix_ready`, `synthesis_chunk`, `matrix_updated`, and `complete` events. |
| **Modify** | `backend/src/app/agent/reasoning_engine.py` | Update `CatalogComparisonReasoningEngine.stream_query()` to stream live events from `MultiAgentCoordinator.execute_stream()`. |
| **Modify** | `backend/src/app/routes/compare.py` | Add `POST /api/compare/stream` (and `/api/v1/compare/stream`) returning SSE `StreamingResponse` (`text/event-stream`). |
| **Create** | `backend/tests/test_stage4_streaming.py` | Unit and integration tests for partial JSON stream extraction, Stage 4 LLM streaming, parallel preference matrix updates, Model Armor refusal handling, and `/api/compare/stream` SSE framing. |
| **Modify** | `frontend/src/types/comparison.ts` | Add `ComparisonStreamEvent` types (`matrix_ready`, `synthesis_chunk`, `matrix_updated`, `complete`, `error`). |
| **Modify** | `frontend/src/api/client.ts` | Add `compareProductsStream()` SSE reader using `fetch` + `ReadableStream` with graceful JSON fallback. |
| **Modify** | `frontend/src/components/RecommendationCard.tsx` | Add `isStreaming?: boolean` prop with live pulsing `"Synthesizing AI comparison..."` status badge and skeleton placeholder for recommendations while summary streams. |
| **Modify** | `frontend/src/App.tsx` | Wire progressive comparison state: render `ProductCard`s and `ComparisonTable` immediately on `matrix_ready`, and update `RecommendationCard` live on `synthesis_chunk` / `complete`. |
| **Modify** | `frontend/src/test/RecommendationCard.test.tsx` & `frontend/src/test/client.test.ts` | Add frontend unit tests for `compareProductsStream` SSE parsing and `RecommendationCard` streaming UI states. |
| **Modify** | `ARCHITECTURE.md`, `backend/AGENTS.md`, `frontend/AGENTS.md` | Synchronize architecture diagrams, SSE endpoint contracts, and perceived latency documentation. |

---

### Task 1: Incremental JSON Field Extractor & Stage 4 LLM Stream Generator (`orchestrator.py`)

**Files:**
- Modify: `backend/src/app/agent/orchestrator.py`
- Create: `backend/tests/test_stage4_streaming.py`

**Interfaces:**
- Produces:
  ```python
  def _extract_partial_synthesis_fields(raw_buffer: str) -> tuple[str, str | None]:
      """Extract in-progress 'summary' and 'recommendations' strings from partial JSON stream buffer."""

  # On ComparisonOrchestrator:
  def stream_synthesize_comparison_with_llm(
      self,
      products: list[ProductSpec],
      matrix: list[MatrixRow],
      query: str = "",
      model: str | None = None,
  ) -> Iterator[dict[str, Any]]:
      """Stream Stage 4 LLM synthesis chunks and final verified _SynthesisResult."""
  ```

- [ ] **Step 1: Write failing tests for partial JSON extraction and `stream_synthesize_comparison_with_llm` in `backend/tests/test_stage4_streaming.py`**

```python
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from app.agent.orchestrator import (
    ComparisonOrchestrator,
    _extract_partial_synthesis_fields,
)
from app.models.responses import ProductSpec


def _sample_products() -> list[ProductSpec]:
    return [
        ProductSpec(
            sku="6534606",
            name="Apple - MacBook Air 13.6\" Laptop - M3",
            brand="Apple",
            category="Laptops",
            price=1099.0,
            specifications={"ram_gb": 16, "battery_life_hours": 18},
            in_stock=True,
        ),
        ProductSpec(
            sku="6575132",
            name="Dell - XPS 13\" Laptop - Intel Core Ultra 7",
            brand="Dell",
            category="Laptops",
            price=1199.0,
            specifications={"ram_gb": 16, "battery_life_hours": 14},
            in_stock=True,
        ),
    ]


def test_extract_partial_synthesis_fields_handles_incomplete_json_and_partial_sku():
    buf1 = '{"summary": "Apple MacBook Air [SKU: 6534606] leads with 18h battery [SKU: 657'
    summary1, recs1 = _extract_partial_synthesis_fields(buf1)
    assert "Apple MacBook Air [SKU: 6534606] leads with 18h battery" in summary1
    assert "[SKU: 657" not in summary1
    assert recs1 is None

    buf2 = (
        '{"summary": "Apple MacBook Air [SKU: 6534606] leads with 18h battery [SKU: 6575132].", '
        '"recommendations": "Best for Travel: Apple MacBook Air [SKU: 6534606]'
    )
    summary2, recs2 = _extract_partial_synthesis_fields(buf2)
    assert summary2.endswith("[SKU: 6575132].")
    assert recs2 == "Best for Travel: Apple MacBook Air [SKU: 6534606]"


def test_stream_synthesize_comparison_with_llm_emits_chunks_and_final():
    products = _sample_products()
    mock_client = MagicMock()
    chunks = [
        SimpleNamespace(
            text='{"summary": "- Apple MacBook Air [SKU: 6534606] ($1,099.00) ',
            usage_metadata=None,
            candidates=[],
        ),
        SimpleNamespace(
            text='beats Dell XPS 13 [SKU: 6575132] ($1,199.00) on battery (18h vs 14h).", ',
            usage_metadata=None,
            candidates=[],
        ),
        SimpleNamespace(
            text='"recommendations": "Best for Portability: Apple MacBook Air [SKU: 6534606] — 18h battery"}',
            usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=45),
            candidates=[SimpleNamespace(finish_reason="STOP")],
        ),
    ]
    mock_client.models.generate_content_stream.return_value = iter(chunks)

    orch = ComparisonOrchestrator(genai_client=mock_client, model="gemini-3.5-flash-lite")
    matrix = []
    events = list(
        orch.stream_synthesize_comparison_with_llm(
            products, matrix, query="Compare MacBook Air and Dell XPS 13"
        )
    )

    chunk_events = [e for e in events if e["event"] == "synthesis_chunk"]
    complete_events = [e for e in events if e["event"] == "synthesis_complete"]
    assert len(chunk_events) >= 2
    assert len(complete_events) == 1
    assert "[SKU: 6534606]" in complete_events[0]["summary"]
    assert "[SKU: 6534606]" in complete_events[0]["recommendations"]
    assert len(matrix) > 0
    assert orch.last_input_tokens == 120
    assert orch.last_output_tokens == 45
```

- [ ] **Step 2: Run pytest to verify the new test fails**

Run: `PYTHONPATH=backend/src backend/.venv/bin/pytest backend/tests/test_stage4_streaming.py -v --no-cov --no-doc`
Expected: FAIL with `ImportError: cannot import name '_extract_partial_synthesis_fields' from 'app.agent.orchestrator'`

- [ ] **Step 3: Implement `_extract_partial_synthesis_fields`, `_call_genai_stream_with_failover`, and `stream_synthesize_comparison_with_llm` in `backend/src/app/agent/orchestrator.py`**

```python
def _strip_trailing_incomplete_sku_tag(text: str) -> str:
    """Strip an unclosed trailing '[SKU:...' fragment so partial tokens do not flicker in UI."""
    if not text:
        return ""
    last_open = text.rfind("[")
    if last_open != -1 and "]" not in text[last_open:]:
        tail = text[last_open:]
        if tail.upper().startswith("[SKU".upper()[: len(tail)]):
            return text[:last_open].rstrip()
    return text


def _unescape_json_fragment(fragment: str) -> str:
    """Unescape partial JSON string escapes (\\n, \\", \\\\, \\t) safely."""
    if not fragment:
        return ""
    if fragment.endswith("\\") and not fragment.endswith("\\\\"):
        fragment = fragment[:-1]
    return (
        fragment.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
    )


def _extract_partial_synthesis_fields(raw_buffer: str) -> tuple[str, str | None]:
    """Extract in-progress 'summary' and 'recommendations' strings from partial JSON stream buffer."""
    if not raw_buffer:
        return "", None
    sum_m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)', raw_buffer, re.DOTALL)
    rec_m = re.search(r'"recommendations"\s*:\s*"((?:[^"\\]|\\.)*)', raw_buffer, re.DOTALL)
    summary_val = (
        _strip_trailing_incomplete_sku_tag(_unescape_json_fragment(sum_m.group(1)))
        if sum_m
        else ""
    )
    recs_val = (
        _strip_trailing_incomplete_sku_tag(_unescape_json_fragment(rec_m.group(1)))
        if rec_m
        else None
    )
    return summary_val, recs_val
```

And on `ComparisonOrchestrator`:
- `_call_genai_stream_with_failover(self, client, model, contents, config)`:
  - Checks if `hasattr(client.models, "generate_content_stream")` and not a `MagicMock` without `return_value`/`side_effect` configured; iterates chunks from `client.models.generate_content_stream(...)` with the same `us-central1` failover logic as `_call_genai_with_failover`. If `generate_content_stream` is unconfigured on a mock client, falls back to `[self._call_genai_with_failover(client, model, contents, config)]`.
- `stream_synthesize_comparison_with_llm(self, products, matrix, query="", model=None)`:
  - Pre-populates `matrix[:]` deterministically in 0ms if empty.
  - Submits `matrix_fut` to `_SPECULATIVE_SYNTH_POOL` if `has_preferences` is True.
  - Iterates over `_call_genai_stream_with_failover`, accumulating `raw_buffer`, extracting `(partial_summary, partial_recs)` via `_extract_partial_synthesis_fields(raw_buffer)`, scrubbing valid SKUs with `verify_and_align_claim_citations`, and yielding `{"event": "synthesis_chunk", "summary": ..., "recommendations": ..., "delta": chunk_text}`.
  - Checks if `matrix_fut` completed (`matrix_fut.done()`) or awaits it at end of stream; if `mw_winners` updates `matrix`, yields `{"event": "matrix_updated", "comparison_matrix": matrix, "spec_winners": merged_spec_winners}`.
  - Validates final JSON via `_clean_synthesis_json` + `ComparisonSynthesis.model_validate_json`, verifies Model Armor response guard, and yields `{"event": "synthesis_complete", "summary": summary_out, "recommendations": recs_out, "spec_winners": merged_spec_winners, "comparison_matrix": matrix}`.

- [ ] **Step 4: Run pytest to verify Task 1 tests pass**

Run: `PYTHONPATH=backend/src backend/.venv/bin/pytest backend/tests/test_stage4_streaming.py -v --no-cov --no-doc`
Expected: PASS

---

### Task 2: MultiAgentCoordinator & ReasoningEngine Stage 4 Streaming (`multi_agent.py`, `reasoning_engine.py`, `compare.py`)

**Files:**
- Modify: `backend/src/app/agent/multi_agent.py`
- Modify: `backend/src/app/agent/reasoning_engine.py`
- Modify: `backend/src/app/routes/compare.py`
- Modify: `backend/tests/test_stage4_streaming.py`

**Interfaces:**
- Produces:
  ```python
  # On MultiAgentCoordinator:
  def execute_stream(
      self,
      raw_query: str,
      category: str | None = None,
      session_id: str | None = None,
      agent_version: str | None = None,
      model: str | None = None,
      synthesis_model: str | None = None,
      user_id: str | None = None,
      stage1_model: str | None = None,
      stage2_model: str | None = None,
      stage3_model: str | None = None,
  ) -> Iterator[dict[str, Any]]:
      """Yield 'matrix_ready', 'synthesis_chunk', 'matrix_updated', and 'complete' events."""

  # In routes/compare.py:
  @router.post("/compare/stream", tags=["Comparison"])
  async def compare_products_stream(request: ComparisonRequest, ...) -> StreamingResponse:
      """SSE endpoint streaming Stage 2 matrix_ready followed by Stage 4 LLM synthesis chunks."""
  ```

- [ ] **Step 1: Add failing tests for `MultiAgentCoordinator.execute_stream`, `CatalogComparisonReasoningEngine.stream_query`, and `POST /api/compare/stream` in `backend/tests/test_stage4_streaming.py`**

```python
import json
from fastapi.testclient import TestClient
from app.main import app
from app.agent.multi_agent import MultiAgentCoordinator
from app.agent.reasoning_engine import CatalogComparisonReasoningEngine


def test_multi_agent_coordinator_execute_stream_yields_matrix_ready_then_chunks(
    mock_bq_client,
):
    coord = MultiAgentCoordinator(bq_client=mock_bq_client, model="stage-optimal")
    events = list(
        coord.execute_stream(
            raw_query="Compare Apple MacBook Air M3 [SKU: 6534606] and Dell XPS 13 [SKU: 6575132]",
            category="Laptops",
            session_id="test-stream-sess",
        )
    )
    event_types = [e["event"] for e in events]
    assert event_types[0] == "matrix_ready"
    assert "complete" in event_types
    matrix_event = events[0]
    assert len(matrix_event["products"]) >= 2
    assert len(matrix_event["comparison_matrix"]) > 0
    complete_event = [e for e in events if e["event"] == "complete"][0]
    assert complete_event["data"]["summary"]
    assert complete_event["data"]["comparison_matrix"]


def test_compare_stream_sse_endpoint_returns_event_stream(mock_bq_client, monkeypatch):
    client = TestClient(app)
    resp = client.post(
        "/api/compare/stream",
        json={
            "query": "Compare Apple MacBook Air M3 [SKU: 6534606] and Dell XPS 13 [SKU: 6575132]",
            "category": "Laptops",
            "session_id": "sse-test-1",
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data: ")]
    assert len(lines) >= 2
    first_payload = json.loads(lines[0][len("data: ") :])
    last_payload = json.loads(lines[-1][len("data: ") :])
    assert first_payload["event"] == "matrix_ready"
    assert last_payload["event"] == "complete"
    assert len(first_payload["products"]) >= 2
    assert last_payload["data"]["summary"]
```

- [ ] **Step 2: Run pytest to verify the new tests fail**

Run: `PYTHONPATH=backend/src backend/.venv/bin/pytest backend/tests/test_stage4_streaming.py -v --no-cov --no-doc`
Expected: FAIL (`AttributeError: 'MultiAgentCoordinator' object has no attribute 'execute_stream'`)

- [ ] **Step 3: Implement `MultiAgentCoordinator.execute_stream`, update `CatalogComparisonReasoningEngine.stream_query`, and add `POST /api/compare/stream` in `backend/src/app/routes/compare.py`**

1. In `backend/src/app/agent/multi_agent.py`:
   - Add `execute_stream(...)` on `MultiAgentCoordinator`:
     - Runs Stage 1 (`QueryIntentAgent.process`) and Stage 2 (`CatalogRetrievalStep.process`) concurrently via `ThreadPoolExecutor` / `asyncio.gather`.
     - Balances candidates (`_select_best_entity_candidates`) and builds the initial deterministic matrix (`self.orchestrator.build_comparison_matrix(state.ranked_products, query=safe_query)`).
     - Immediately yields:
       ```python
       {
           "event": "matrix_ready",
           "products": [p.model_dump() for p in state.ranked_products],
           "comparison_matrix": [r.model_dump() for r in matrix],
           "citations": [c.model_dump() for c in citations],
           "session_id": session_id,
           "trace_id": trace_id,
           "timing_breakdown_ms": {
               "intent_ms": intent_ms,
               "retrieval_ms": retrieval_ms,
               "ttfb_ms": ttfb_ms,
           },
       }
       ```
     - Streams Stage 4 via `self.comparison_agent.orchestrator.stream_synthesize_comparison_with_llm(...)`, forwarding `synthesis_chunk` and `matrix_updated` events, then constructs the final `CompareResponse` and yields `{"event": "complete", "data": response.model_dump()}`.
2. In `backend/src/app/agent/reasoning_engine.py`:
   - Update `stream_query()` to iterate `self._coordinator.execute_stream(...)` and yield each intermediate event followed by `{"event_type": "comparison_completed", "data": final_data}` (preserving compatibility with `_invoke_remote_reasoning_engine` which reads the final line).
3. In `backend/src/app/routes/compare.py`:
   - Add `POST /compare/stream` returning `StreamingResponse` with `media_type="text/event-stream"`, formatting each yielded dict as `f"event: {ev['event']}\ndata: {json.dumps(ev)}\n\n"`.

- [ ] **Step 4: Run pytest to verify Task 2 tests pass**

Run: `PYTHONPATH=backend/src backend/.venv/bin/pytest backend/tests/test_stage4_streaming.py backend/tests/test_compare_api.py backend/tests/test_reasoning_engine.py -v --no-cov --no-doc`
Expected: PASS

---

### Task 3: Frontend SSE Streaming Client & Progressive UI Rendering (`client.ts`, `RecommendationCard.tsx`, `App.tsx`)

**Files:**
- Modify: `frontend/src/types/comparison.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/RecommendationCard.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/test/client.test.ts`
- Modify: `frontend/src/test/RecommendationCard.test.tsx`

**Interfaces:**
- Produces:
  ```typescript
  // In frontend/src/types/comparison.ts:
  export interface ComparisonStreamCallbacks {
    onMatrixReady?: (partial: {
      products: ProductSpec[];
      comparison_matrix: MatrixRow[];
      citations: Citation[];
      session_id?: string | null;
      trace_id?: string | null;
      timing_breakdown_ms?: Record<string, number>;
    }) => void;
    onSynthesisChunk?: (chunk: {
      summary: string;
      recommendations?: string | null;
      delta?: string;
    }) => void;
    onMatrixUpdated?: (update: {
      comparison_matrix: MatrixRow[];
    }) => void;
  }

  // In frontend/src/api/client.ts:
  export async function compareProductsStream(
    request: ComparisonRequest,
    callbacks?: ComparisonStreamCallbacks
  ): Promise<ComparisonResponse>;
  ```

- [ ] **Step 1: Write failing frontend tests in `frontend/src/test/client.test.ts` and `frontend/src/test/RecommendationCard.test.tsx`**

```typescript
// In frontend/src/test/RecommendationCard.test.tsx:
it('renders streaming indicator badge when isStreaming is true', () => {
  render(
    <RecommendationCard
      summary="Partial streamed summary [SKU: 6534606]..."
      recommendations={null}
      isStreaming={true}
    />
  );
  expect(screen.getByTestId('synthesis-streaming-badge')).toBeInTheDocument();
  expect(screen.getByText(/Synthesizing AI comparison/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run Vitest to verify failure**

Run: `npm --prefix frontend test -- --run src/test/RecommendationCard.test.tsx`
Expected: FAIL (`Unable to find an element by: [data-testid="synthesis-streaming-badge"]`)

- [ ] **Step 3: Implement `compareProductsStream`, update `RecommendationCard.tsx`, and wire progressive state in `App.tsx`**

1. **`frontend/src/api/client.ts`**:
   - Implement `compareProductsStream(request, callbacks)`:
     - Calls `POST ${API_BASE_URL}/api/compare/stream` with `Accept: text/event-stream`.
     - If the environment/test mock returns a non-stream response or `/api/compare/stream` is not mocked in legacy tests (e.g., `response.body` is null or content-type is `application/json`), falls back to parsing JSON directly or calling `compareProducts(request)`.
     - Reads chunks from `response.body.getReader()` using `TextDecoder`, splits SSE frames on `\n\n`, parses `data: {...}`, invokes `onMatrixReady`, `onSynthesisChunk`, `onMatrixUpdated`, and resolves with the final `ComparisonResponse` from the `complete` event.
2. **`frontend/src/components/RecommendationCard.tsx`**:
   - Add `isStreaming?: boolean` prop to `RecommendationCardProps`.
   - When `isStreaming` is `true`, render `<span data-testid="synthesis-streaming-badge" className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-bb-blue border border-blue-200 animate-pulse">Synthesizing AI comparison...</span>`.
   - If `isStreaming && !summary`, render a compact 2-line shimmer placeholder inside the card while the comparison table and product cards below it are already fully interactive!
3. **`frontend/src/App.tsx`**:
   - Add `streamingComparison` state (`Partial<ComparisonResponse> | null`) and `isStreamingSynthesis` boolean state.
   - Inside `useQuery`'s `queryFn`, call `compareProductsStream` with callbacks that update `streamingComparison` on `onMatrixReady`, `onSynthesisChunk`, and `onMatrixUpdated`, clearing `isStreamingSynthesis` when `complete` resolves.
   - Compute `activeComparison = comparison || (streamingComparison as ComparisonResponse | null)`.
   - Show `<SkeletonLoader />` ONLY while `isLoading && !streamingComparison`. As soon as `matrix_ready` arrives (~150ms), hide `<SkeletonLoader />` and render `activeComparison` with `<RecommendationCard isStreaming={isStreamingSynthesis} ... />`, `<ProductCard />` grid, and `<ComparisonTable />`!

- [ ] **Step 4: Run frontend tests and build to verify all pass**

Run: `npm --prefix frontend test -- --run && npm --prefix frontend run build`
Expected: PASS

---

### Task 4: Documentation Sync (`ARCHITECTURE.md`, `backend/AGENTS.md`, `frontend/AGENTS.md`) & Full Verification Gate

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `backend/AGENTS.md`
- Modify: `frontend/AGENTS.md`

- [ ] **Step 1: Update `ARCHITECTURE.md`, `backend/AGENTS.md`, and `frontend/AGENTS.md`**
  - Document `POST /api/compare/stream` (and `/api/v1/compare/stream`) SSE protocol (`matrix_ready` -> `synthesis_chunk` -> `matrix_updated` -> `complete`).
  - Document `ComparisonOrchestrator.stream_synthesize_comparison_with_llm()`, `_extract_partial_synthesis_fields()`, and `MultiAgentCoordinator.execute_stream()`.
  - Document frontend `compareProductsStream()` progressive rendering and `RecommendationCard` streaming state.

- [ ] **Step 2: Run full backend + frontend verification gates**

```bash
ruff check backend/ evals/
ruff format --check backend/ evals/
PYTHONPATH=backend/src:.:backend backend/.venv/bin/pytest backend/tests/ --cov=backend/src --cov-fail-under=80
npm --prefix frontend test -- --run
npm --prefix frontend run build
```
Expected: 100% PASS with $\ge 80\%$ coverage and `test_docs_sync.py` green.
