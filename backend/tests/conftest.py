"""Centralized pytest fixtures for hermetic unit testing without production test-detection branches."""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _isolate_unit_test_state(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Reset module-level caches and default cloud runtime flags before and after each test."""
    # Default unit tests to no remote Agent Engine ID unless the test explicitly sets it
    monkeypatch.delenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", raising=False)
    monkeypatch.delenv("AGENT_ENGINE_ID", raising=False)
    monkeypatch.delenv("REASONING_ENGINE_ID", raising=False)
    monkeypatch.delenv("AGENT_RUNTIME_RESOURCE_NAME", raising=False)

    from app.agent import adk_llm, prompts_service, runner
    from app.config import settings
    from app.data.analytics import analytics_service
    from app.routes import compare as compare_routes
    from app.tools import catalog

    monkeypatch.setattr(settings, "agent_engine_id", None, raising=False)
    monkeypatch.setattr(settings, "agent_runtime_resource_name", None, raising=False)
    monkeypatch.setattr(settings, "enable_background_warmup", False, raising=False)
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
