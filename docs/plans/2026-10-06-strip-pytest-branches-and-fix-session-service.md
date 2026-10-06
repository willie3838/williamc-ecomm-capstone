# Strip All 59 Test-Detection Branches & Fix CatalogVertexAiSessionService Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `develop-feature` (or `superpowers:subagent-driven-development` / `superpowers:executing-plans`) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all 59 `PYTEST_CURRENT_TEST`, `"pytest" in sys.modules`, `hasattr(..., "assert_called")`, and `"Mock"` branches across all 11 backend production files, fix `CatalogVertexAiSessionService` (`#L167-L206`) and `CatalogVertexAiMemoryBankService` so remote Vertex AI Agent Engine session/memory persistence works in production for all session IDs, and move all test isolation into `backend/tests/conftest.py`.

**Architecture:** Replace inline test-environment detection in `backend/src/app/` with constructor/function dependency injection, factory-keyed singleton caches (`(key, cls)`), unified `GenerateContentConfig` construction across all environments, and a centralized `backend/tests/conftest.py` fixture suite. Fix `CatalogVertexAiSessionService` to delegate `create_session`, `get_session`, `list_sessions`, `delete_session`, and `append_event` to `VertexAiSessionService` whenever `agent_engine_id` is configured, transparently mapping custom application session IDs (`sess_...`) to Vertex-assigned numeric session IDs when required by the remote API.

**Tech Stack:** Python 3.12, FastAPI, Google ADK (`google-adk`), Google GenAI SDK (`google-genai`), Google Cloud BigQuery, Google Cloud Firestore, Vertex AI Agent Engine Sessions & Memory Bank, Pytest.

**Spec:** `SPEC.md` and `RUBRIC.md`

## Global Constraints

- Zero occurrences of `PYTEST_CURRENT_TEST`, `"pytest" in sys.modules`, `assert_called`, or `"Mock" in type` are permitted anywhere under `backend/src/app/`.
- FastAPI backend test suite must maintain $\ge 80\%$ code coverage (`pytest backend/ --cov=backend/src --cov-fail-under=80`).
- Live comparison pipeline latency must remain $< 3.0\text{s}$ (`python backend/scripts/verify_live_latency.py --threshold-ms 3000`).
- `isinstance(service, VertexAiSessionService)` and `isinstance(memory_service, VertexAiMemoryBankService)` must remain `True`.

## Review Focus

- Custom string session IDs (e.g., `"sess_20261006..."`, `"session_1728..."`) passed to `CatalogVertexAiSessionService.create_session`, `get_session`, `delete_session`, and `append_event` in production when `GOOGLE_CLOUD_AGENT_ENGINE_ID` is set.
- Multiple `with unittest.mock.patch(...)` blocks within the same test function replacing `genai.Client`, `bigquery.Client`, `ComparisonOrchestrator`, or `MultiAgentCoordinator` without leaking cached singletons across patches.
- `GenerateContentConfig` in `ComparisonOrchestrator` passing `system_instruction`, `model_armor_config`, and `max_output_tokens` identically in production and unit tests without breaking regional vs. `global` endpoint routing for Gemini 3.x preview models.
- Multi-instance session comparison counter (`session_comparison_count` in `/api/compare`) returning accurate counts without `PYTEST_CURRENT_TEST` branching.
- Hermetic unit test execution in `pytest` when `GOOGLE_CLOUD_AGENT_ENGINE_ID` is unset or reset by `backend/tests/conftest.py`, ensuring zero unmocked outbound GCP calls during unit tests.

---

### Task 1: Create `backend/tests/conftest.py` & Automated Anti-Test-Branch Gate

**Files:**
- Create: `backend/tests/conftest.py`
- Modify: `backend/tests/test_audit_integrity.py`

**Interfaces:**
- Produces: `reset_global_singletons` autouse fixture in `backend/tests/conftest.py` and `test_zero_pytest_or_mock_branches_in_production_code` in `backend/tests/test_audit_integrity.py`.

- [ ] **Step 1: Write the failing test in `backend/tests/test_audit_integrity.py`**

Add a test that scans every `.py` file under `backend/src/app/` and asserts zero occurrences of `PYTEST_CURRENT_TEST`, `assert_called`, `"pytest" in sys.modules`, or `"Mock" in type`:

```python
def test_zero_pytest_or_mock_branches_in_production_code() -> None:
    """Verify production code under backend/src/app contains zero test-detection branches."""
    app_root = Path(__file__).resolve().parents[1] / "src" / "app"
    forbidden_tokens = (
        "PYTEST_CURRENT_TEST",
        "assert_called",
        '"pytest" in sys.modules',
        "'pytest' in sys.modules",
        '"Mock" in type',
    )
    violations: list[str] = []
    for py_file in sorted(app_root.rglob("*.py")):
        content = py_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(content.splitlines(), start=1):
            for token in forbidden_tokens:
                if token in line:
                    rel = py_file.relative_to(app_root.parents[2])
                    violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, "Forbidden test-detection branches in production code:\n" + "\n".join(
        violations
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_audit_integrity.py -k test_zero_pytest_or_mock_branches_in_production_code -v`
Expected: FAIL listing the 59+ lines across 11 files in `backend/src/app/`.

- [ ] **Step 3: Create `backend/tests/conftest.py` with singleton reset and hermetic environment fixtures**

```python
"""Centralized pytest fixtures for hermetic unit testing without production test-detection branches."""

from __future__ import annotations

import os
from collections.abc import Generator
import pytest


@pytest.fixture(autouse=True)
def _isolate_unit_test_state(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Reset module-level caches and default cloud runtime flags before and after each test."""
    # Default unit tests to no remote Agent Engine ID unless the test explicitly sets it
    monkeypatch.delenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_ID", raising=False)

    from app.agent import adk_llm, prompts_service, runner
    from app.config import settings
    from app.data.analytics import analytics_service
    from app.routes import compare as compare_routes
    from app.tools import catalog

    monkeypatch.setattr(settings, "agent_runtime_resource_name", None, raising=False)
    monkeypatch.setattr(analytics_service, "_disable_cloud_clients", True, raising=False)

    def _clear_caches() -> None:
        adk_llm._SHARED_VERTEX_CLIENT = None
        adk_llm._VERTEX_CLIENTS.clear()
        catalog._SHARED_BQ_CLIENT = None
        compare_routes._COORDINATOR_CACHE.clear()
        prompts_service._PROMPT_CACHE.clear()
        prompts_service._PROMPT_CACHE_TIMESTAMPS.clear()
        runner._DEFAULT_SESSION_SERVICE = None
        runner._DEFAULT_MEMORY_SERVICE = None
        runner._DEFAULT_RUNNER = None

    _clear_caches()
    yield
    _clear_caches()
```

- [ ] **Step 4: Run `pytest backend/tests/test_config.py` to verify `conftest.py` loads cleanly**

Run: `pytest backend/tests/test_config.py -v`
Expected: PASS

---

### Task 2: Fix `CatalogVertexAiSessionService` (`#L167-L206`) & `CatalogVertexAiMemoryBankService` in `runner.py`

**Files:**
- Modify: `backend/src/app/agent/runner.py:125-435`
- Test: `backend/tests/test_adk_runner.py`

**Interfaces:**
- Consumes: `VertexAiSessionService`, `InMemorySessionService`, `VertexAiMemoryBankService`, `InMemoryMemoryService`
- Produces: `CatalogVertexAiSessionService` and `CatalogVertexAiMemoryBankService` with zero `PYTEST_CURRENT_TEST` or `.isdigit()` branches, plus bidirectional mapping between custom string `session_id`s (e.g., `"sess_123"`) and Vertex-generated remote session IDs.

- [ ] **Step 1: Write failing tests in `backend/tests/test_adk_runner.py` for non-digit session IDs in production mode**

Add a test in `backend/tests/test_adk_runner.py` where `PYTEST_CURRENT_TEST` is removed from `os.environ` via `monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)` and a custom string `session_id="sess_prod_abc123"` is passed to `create_session`, `get_session`, `append_event`, and `delete_session`:

```python
@pytest.mark.asyncio
async def test_vertex_ai_session_service_production_non_digit_session_id(monkeypatch):
    """Verify create_session, get_session, append_event, and delete_session call Vertex AI when PYTEST_CURRENT_TEST is unset and session_id is alphanumeric."""
    from unittest.mock import AsyncMock, MagicMock

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv(
        "GOOGLE_CLOUD_AGENT_ENGINE_ID",
        "projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/reasoningEngines/9876543210",
    )
    service = CatalogVertexAiSessionService()
    assert service._should_use_vertex_remote() is True

    mock_api_client = MagicMock()
    mock_create_resp = MagicMock()
    mock_create_resp.response.name = (
        "projects/fde-bestbuy-sandbox-dev-508321/locations/us-central1/"
        "reasoningEngines/9876543210/sessions/sess_prod_abc123"
    )
    mock_create_resp.response.session_state = {"category": "Laptops"}
    mock_api_client.agent_engines.sessions.create = AsyncMock(return_value=mock_create_resp)

    mock_get_resp = MagicMock()
    mock_get_resp.name = mock_create_resp.response.name
    mock_get_resp.session_state = {"category": "Laptops"}
    mock_get_resp.update_time = None
    mock_api_client.agent_engines.sessions.get = AsyncMock(return_value=mock_get_resp)
    mock_api_client.agent_engines.sessions.events.list = AsyncMock(return_value=[])
    mock_api_client.agent_engines.sessions.delete = AsyncMock(return_value=None)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_api_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch.object(service, "_get_api_client", return_value=mock_cm):
        created = await service.create_session(
            app_name="app",
            user_id="prod_user",
            state={"category": "Laptops"},
            session_id="sess_prod_abc123",
        )
        assert created.id == "sess_prod_abc123"
        mock_api_client.agent_engines.sessions.create.assert_awaited_once()

        fetched = await service.get_session(
            app_name="app",
            user_id="prod_user",
            session_id="sess_prod_abc123",
        )
        assert fetched is not None
        mock_api_client.agent_engines.sessions.get.assert_awaited_once()

        await service.delete_session(
            app_name="app",
            user_id="prod_user",
            session_id="sess_prod_abc123",
        )
        mock_api_client.agent_engines.sessions.delete.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_adk_runner.py -k test_vertex_ai_session_service_production_non_digit_session_id -v`
Expected: FAIL (`mock_api_client.agent_engines.sessions.create.assert_awaited_once()` fails because `PYTEST_CURRENT_TEST` is unset and `session_id` is not `None`).

- [ ] **Step 3: Implement clean `CatalogVertexAiSessionService` and `CatalogVertexAiMemoryBankService` in `backend/src/app/agent/runner.py`**

Replace lines 139–280 and 323–434 in `backend/src/app/agent/runner.py`:

```python
    def _should_use_vertex_remote(self) -> bool:
        """Determine whether to invoke the live Vertex AI Agent Engine Sessions API."""
        engine_id = self.agent_engine_id
        if not engine_id:
            return False
        self._agent_engine_id = engine_id
        return True

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> Session:
        local_session = await self._fallback_memory.create_session(
            app_name=app_name,
            user_id=user_id,
            state=state,
            session_id=session_id,
        )
        if self._should_use_vertex_remote():
            try:
                try:
                    remote_session = await super().create_session(
                        app_name=self.agent_engine_id or app_name,
                        user_id=user_id,
                        state=state,
                        session_id=session_id,
                        **kwargs,
                    )
                except ValueError:
                    # Fallback if upstream ADK / Vertex rejects user-provided session_id
                    remote_session = await super().create_session(
                        app_name=self.agent_engine_id or app_name,
                        user_id=user_id,
                        state=state,
                        session_id=None,
                        **kwargs,
                    )
                if session_id and remote_session.id != session_id:
                    self._remote_session_id_map[(user_id, session_id)] = str(remote_session.id)
                    remote_session.id = session_id
                remote_session.app_name = app_name
                return remote_session
            except Exception as exc:
                logger.debug(
                    "VertexAiSessionService.create_session fallback to InMemorySessionService: %s",
                    exc,
                )
        return local_session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        local_session = await self._fallback_memory.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            config=config,
        )
        if self._should_use_vertex_remote() and session_id:
            remote_sid = self._remote_session_id_map.get((user_id, session_id), session_id)
            try:
                remote_session = await super().get_session(
                    app_name=self.agent_engine_id or app_name,
                    user_id=user_id,
                    session_id=remote_sid,
                    config=config,
                )
                if remote_session is not None:
                    remote_session.id = session_id
                    remote_session.app_name = app_name
                    return remote_session
            except Exception as exc:
                logger.debug(
                    "VertexAiSessionService.get_session fallback to InMemorySessionService: %s",
                    exc,
                )
        return local_session

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        await self._fallback_memory.delete_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        remote_sid = self._remote_session_id_map.pop((user_id, session_id), session_id)
        if self._should_use_vertex_remote() and remote_sid:
            try:
                await super().delete_session(
                    app_name=self.agent_engine_id or app_name,
                    user_id=user_id,
                    session_id=remote_sid,
                )
            except Exception as exc:
                logger.debug("VertexAiSessionService.delete_session note: %s", exc)

    async def append_event(self, session: Session, event: Event) -> Event:
        updated = await self._fallback_memory.append_event(session=session, event=event)
        sid = str(getattr(session, "id", "") or "")
        if self._should_use_vertex_remote() and sid:
            try:
                await super().append_event(session=session, event=event)
            except Exception as exc:
                logger.debug("VertexAiSessionService.append_event note: %s", exc)
        return updated
```

And in `CatalogVertexAiMemoryBankService`, remove all `PYTEST_CURRENT_TEST` and `user_id != "default_user"` conditions so `_should_use_vertex_remote()` checks only `bool(self.agent_engine_id)` and all 4 methods (`add_session_to_memory`, `add_events_to_memory`, `add_memory`, `search_memory`) delegate to `super()` whenever `self._should_use_vertex_remote()` is `True`.

- [ ] **Step 4: Run `pytest backend/tests/test_adk_runner.py` to verify all runner tests pass**

Run: `pytest backend/tests/test_adk_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/src/app/agent/runner.py backend/tests/test_adk_runner.py backend/tests/conftest.py
git commit -m "fix(agent): remove PYTEST_CURRENT_TEST guards in CatalogVertexAiSessionService and support all session IDs"
```

---

### Task 3: Strip Test-Detection Branches in `tools/catalog.py`, `data/analytics.py`, `agent/prompts_service.py`, `agent/agent.py`, `agent/reasoning_engine.py`, and `agent/__init__.py`

**Files:**
- Modify: `backend/src/app/tools/catalog.py:132-138, 349-363`
- Modify: `backend/src/app/data/analytics.py:61-125`
- Modify: `backend/src/app/agent/prompts_service.py:148-190`
- Modify: `backend/src/app/agent/agent.py:238-252`
- Modify: `backend/src/app/agent/reasoning_engine.py:45-56`
- Modify: `backend/src/app/agent/__init__.py:112-121`

**Interfaces:**
- Consumes: `settings` from `app.config`, singleton reset fixture in `backend/tests/conftest.py`
- Produces: Clean client resolution in `catalog.py` (keyed by `bigquery.Client` class identity), clean `analytics.py` (controlled solely by `self._disable_cloud_clients`), clean `prompts_service.py` (controlled by `settings.enable_vertex_prompt_registry`), and clean `agent.py`/`reasoning_engine.py`/`agent/__init__.py`.

- [ ] **Step 1: Update `backend/src/app/tools/catalog.py`**

1. Key `_get_shared_bq_client()` on `bigquery.Client` identity so if `bigquery.Client` is patched by a test, it constructs via the current `bigquery.Client` callable without checking `assert_called`:
```python
_SHARED_BQ_CLIENT: Any = None
_SHARED_BQ_CLIENT_CLS: Any = None


def _get_shared_bq_client() -> bigquery.Client:
    global _SHARED_BQ_CLIENT, _SHARED_BQ_CLIENT_CLS
    if _SHARED_BQ_CLIENT is not None and _SHARED_BQ_CLIENT_CLS is bigquery.Client:
        return _SHARED_BQ_CLIENT
    with _BQ_CLIENT_LOCK:
        if _SHARED_BQ_CLIENT is not None and _SHARED_BQ_CLIENT_CLS is bigquery.Client:
            return _SHARED_BQ_CLIENT
        _SHARED_BQ_CLIENT = bigquery.Client(project=settings.gcp_project)
        _SHARED_BQ_CLIENT_CLS = bigquery.Client
        return _SHARED_BQ_CLIENT
```
2. In `query_catalog` (`catalog.py:133-137`), replace the `if hasattr(bigquery.Client, "assert_called"):` branch with `if client is None: client = _get_shared_bq_client()`.
3. In `query_catalog` (`catalog.py:349-363`), standardize on `query_job = client.query(query_sql, job_config=job_config)` followed by `results = query_job.result(timeout=timeout_seconds)` in all environments (removing the `hasattr(bigquery.Client, "assert_called")` and `hasattr(client.query, "assert_called")` checks).

- [ ] **Step 2: Update `backend/src/app/data/analytics.py`**

Remove `if os.getenv("PYTEST_CURRENT_TEST"): return None` at lines 67 and 116. `self._disable_cloud_clients` (already present at lines 63 and 112 and set by `conftest.py` unless a test tests client initialization) cleanly controls whether cloud clients are initialized. Ensure `backend/tests/test_analytics.py` sets `service._disable_cloud_clients = False` when testing `get_firestore_client()` / `get_bq_client()`.

- [ ] **Step 3: Update `backend/src/app/agent/prompts_service.py`, `agent.py`, `reasoning_engine.py`, and `agent/__init__.py`**

1. In `prompts_service.py:152-190`: Remove `if os.environ.get("PYTEST_CURRENT_TEST") and not hasattr(prompts.get, "assert_called"):` and `not hasattr(prompts.get, "assert_called")`. By default `settings.enable_vertex_prompt_registry` is `False`; when enabled, call `prompts.get` directly and fall back cleanly on exception.
2. In `agent/__init__.py:114`: Call `_reg_re()` unconditionally inside `try...except Exception`.
3. In `agent.py:243-248`: Remove `"PYTEST_CURRENT_TEST" not in os.environ and "pytest" not in sys.modules`; guard background warmup with `if getattr(settings, "enable_background_warmup", False) and reasoning_engine._coordinator is None:`.
4. In `reasoning_engine.py:46-49`: Replace `"PYTEST_CURRENT_TEST" not in os.environ and os.environ.get("EXPORT_TRACES_TO_CLOUD", "false").lower() == "true"` with `os.environ.get("EXPORT_TRACES_TO_CLOUD", "false").lower() == "true"`.

- [ ] **Step 4: Run tests for catalog, analytics, prompts, and reasoning engine**

Run: `pytest backend/tests/test_catalog_tool.py backend/tests/test_analytics.py backend/tests/test_reasoning_engine.py backend/tests/test_agent_entrypoint.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/src/app/tools/catalog.py backend/src/app/data/analytics.py backend/src/app/agent/prompts_service.py backend/src/app/agent/agent.py backend/src/app/agent/reasoning_engine.py backend/src/app/agent/__init__.py backend/tests/
git commit -m "refactor(backend): remove test-detection branches from catalog, analytics, prompts, and entrypoint modules"
```

---

### Task 4: Strip Test-Detection Branches in `adk_llm.py`, `orchestrator.py`, `multi_agent.py`, and `routes/compare.py`

**Files:**
- Modify: `backend/src/app/agent/adk_llm.py` (11 occurrences)
- Modify: `backend/src/app/agent/orchestrator.py` (18 occurrences)
- Modify: `backend/src/app/agent/multi_agent.py` (3 occurrences)
- Modify: `backend/src/app/routes/compare.py` (7 occurrences)

**Interfaces:**
- Consumes: `conftest.py` singleton cache reset fixture
- Produces: Zero `PYTEST_CURRENT_TEST`, `assert_called`, or `"Mock"` checks across `adk_llm.py`, `orchestrator.py`, `multi_agent.py`, and `routes/compare.py`.

- [ ] **Step 1: Replace `hasattr(..., "assert_called")` in `backend/src/app/agent/adk_llm.py`**

1. Key `_VERTEX_CLIENTS` by `(location, genai.Client)` so if `genai.Client` is replaced by a mock in a test, `_get_shared_vertex_client` instantiates through the current `genai.Client` callable without checking `hasattr(genai.Client, "assert_called")`.
2. In `_sanitize_via_model_armor_rest` (`adk_llm.py:253`), always use `urllib.request.urlopen(req, timeout=1.5)` (which works identically for both real `urllib.request.urlopen` and patched `urlopen` in unit tests!).
3. In `CatalogAdkLlm.generate_content_async` (`adk_llm.py:634-691, 732-736, 975, 1001`), remove `hasattr(genai.Client, "assert_called")` and `hasattr(_get_shared_vertex_client, "assert_called")`; use `self._injected_client or _get_vertex_client_for_model(self.model)` and honor `self.model` directly.

- [ ] **Step 2: Replace `is_mock_env` / `PYTEST_CURRENT_TEST` / `assert_called` in `backend/src/app/agent/orchestrator.py` and `multi_agent.py`**

1. In `get_model_armor_config` (`orchestrator.py:330-362`), remove the `is_mock_env` parameter and always return `types.ModelArmorConfig(prompt_template_name=prompt_tmpl, response_template_name=resp_tmpl)` when `settings.enable_model_armor` is `True`. In `_call_genai_with_failover`, if a `location="global"` call raises `400 INVALID_ARGUMENT` due to regional `model_armor_config`, strip `model_armor_config` on the retry/failover call.
2. In `_synthesize_narrative` (`orchestrator.py:1465-1491`), `classify_intent_with_llm` (`orchestrator.py:1940-1975`), and `_rerank_with_llm` (`orchestrator.py:2458-2495`), remove `is_mock_env` and pass `system_instruction=self.active_system_instruction`, `model_armor_config=armor_cfg`, and `max_output_tokens=int(getattr(settings, "max_output_tokens", 2048))` consistently in both production and tests.
3. For speculative background pre-launch (`orchestrator.py:2363-2378, 2748-2761` and `multi_agent.py:931-944`), replace `is_mock_env` with a clean config setting `getattr(settings, "enable_speculative_prelaunch", False)` (defaulting to `False` for deterministic execution, or enabled explicitly in benchmark/load configs).
4. In `chat_with_products` (`orchestrator.py:3538-3552`), call `_persist_chat_session_and_memory` directly (which is fast with the L1 cache and handles exceptions internally) instead of branching on `PYTEST_CURRENT_TEST`.
5. In `multi_agent.py:120-124`, key or resolve `ComparisonOrchestrator(model=active_model, synthesis_model=active_synthesis)` if `type(self.orchestrator) is not ComparisonOrchestrator` (which handles class patching cleanly without `hasattr(ComparisonOrchestrator, "assert_called")`).

- [ ] **Step 3: Replace test-detection branches in `backend/src/app/routes/compare.py`**

1. Key `_COORDINATOR_CACHE` by `(model, synthesis_model, coord_cls)` so patched `MultiAgentCoordinator` classes automatically construct a fresh instance without checking `hasattr(coord_cls, "assert_called")`.
2. In `_execute_comparison_sync` (`compare.py:354-379`) and `_execute_chat_sync` (`compare.py:505-531`), check `if orch_cls is not None and orch_cls is not ComparisonOrchestrator:` instead of `hasattr(orch_cls, "assert_called")`.
3. In `compare_products` (`compare.py:458-493`), remove `if os.environ.get("PYTEST_CURRENT_TEST"):` and run telemetry + session comparison count consistently.
4. Remove `_is_test_or_eval_env()` (`compare.py:159-163`); guard module-import background thread spawning with `if getattr(settings, "enable_background_warmup", False):`.

- [ ] **Step 4: Run the full test suite and the anti-test-branch integrity check**

Run: `pytest backend/ --cov=backend/src --cov-fail-under=80 -v`
Expected: 100% PASS, zero `PYTEST_CURRENT_TEST` / `assert_called` branches in `backend/src/app/`, and coverage $\ge 80\%$.

- [ ] **Step 5: Verify live latency (< 3.0s)**

Run: `python backend/scripts/verify_live_latency.py --threshold-ms 3000`
Expected: PASS with latency $< 3000\text{ms}$.

- [ ] **Step 6: Commit Task 4**

```bash
git add backend/src/app/ backend/tests/
git commit -m "refactor(agent): strip all 59 PYTEST_CURRENT_TEST and assert_called branches across backend"
```
