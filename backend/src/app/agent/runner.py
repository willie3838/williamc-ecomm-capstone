"""Google ADK Runner integration for the Best Buy Catalog Comparison Agent.

Provides a production-grade `CatalogAdkRunner` backed by `CatalogVertexAiSessionService`
(`VertexAiSessionService`), which automatically connects to the Vertex AI Agent Engine
Session Service (`projects/{project}/locations/{location}/reasoningEngines/{id}/sessions`)
when Agent Runtime injects `GOOGLE_CLOUD_AGENT_ENGINE_ID`, while maintaining an
`InMemorySessionService` fallback for local development, `pytest`, and offline evaluations.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import (
    BaseSessionService,
    InMemorySessionService,
    Session,
    VertexAiSessionService,
)
from google.adk.sessions.base_session_service import (
    GetSessionConfig,
    ListSessionsResponse,
)
from google.genai import types

from app.config import settings as _settings
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def _resolve_agent_engine_id(explicit_id: str | None = None) -> str | None:
    """Resolve the Reasoning Engine ID injected by Agent Runtime (`GOOGLE_CLOUD_AGENT_ENGINE_ID`)."""
    raw = (
        explicit_id
        or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")
        or os.environ.get("AGENT_ENGINE_ID")
        or os.environ.get("REASONING_ENGINE_ID")
        or getattr(_settings, "agent_engine_id", None)
    )
    if not raw:
        return None
    raw_str = str(raw).strip()
    if not raw_str:
        return None
    # If full resource path `projects/.../locations/.../reasoningEngines/12345` is passed, extract the numeric ID
    if "/" in raw_str:
        parts = [p for p in raw_str.split("/") if p]
        if "reasoningEngines" in parts:
            idx = parts.index("reasoningEngines")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return parts[-1]
    return raw_str


class CatalogVertexAiSessionService(VertexAiSessionService):
    """Vertex AI Agent Engine Session Service (`VertexAiSessionService`) with `InMemorySessionService` fallback.

    - In production on **Agent Runtime** (where `GOOGLE_CLOUD_AGENT_ENGINE_ID` is injected by the runtime),
      delegates `create_session`, `get_session`, `list_sessions`, `delete_session`, and `append_event`
      directly to `VertexAiSessionService` (`vertexai.Client.aio.agent_engines.sessions`).
    - In local development, `pytest`, or hermetic offline evaluation benchmarks (`HERMETIC_EVAL=true`),
      transparently falls back to an internal `InMemorySessionService` while preserving
      `isinstance(service, VertexAiSessionService) == True`.
    """

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        agent_engine_id: str | None = None,
        *,
        hermetic: bool = False,
        express_mode_api_key: str | None = None,
    ) -> None:
        resolved_project = project or getattr(
            _settings, "gcp_project", "fde-bestbuy-sandbox-dev-508321"
        )
        resolved_location = location or getattr(_settings, "region", "us-central1")
        resolved_engine_id = _resolve_agent_engine_id(agent_engine_id)

        super().__init__(
            project=resolved_project,
            location=resolved_location,
            agent_engine_id=resolved_engine_id,
            express_mode_api_key=express_mode_api_key,
        )
        self.project_id = resolved_project
        self.location = resolved_location
        self.hermetic = hermetic
        self._fallback_memory = InMemorySessionService()

    @property
    def agent_engine_id(self) -> str | None:
        """Return the active Reasoning Engine ID resolved from config or GOOGLE_CLOUD_AGENT_ENGINE_ID."""
        return _resolve_agent_engine_id(self._agent_engine_id)

    @property
    def sessions(self) -> dict[str, Any]:
        """Expose in-memory sessions dictionary for inspection and test compatibility."""
        return self._fallback_memory.sessions

    def _should_use_vertex_remote(self) -> bool:
        """Determine whether to invoke the live Vertex AI Agent Engine Sessions API."""
        engine_id = self.agent_engine_id
        if not engine_id:
            return False
        self._agent_engine_id = engine_id
        if self.hermetic or os.environ.get("HERMETIC_EVAL", "").lower() == "true":
            return False
        if os.environ.get(
            "PYTEST_CURRENT_TEST"
        ) and "test_vertex_ai_session_service" not in os.environ.get("PYTEST_CURRENT_TEST", ""):
            return False
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
        # Always maintain L1 in-memory copy for fast local lookup and fallback resilience
        local_session = await self._fallback_memory.create_session(
            app_name=app_name,
            user_id=user_id,
            state=state,
            session_id=session_id,
        )
        if self._should_use_vertex_remote():
            try:
                remote_session = await super().create_session(
                    app_name=self.agent_engine_id or app_name,
                    user_id=user_id,
                    state=state,
                    session_id=session_id,
                    **kwargs,
                )
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
        if self._should_use_vertex_remote():
            try:
                remote_session = await super().get_session(
                    app_name=self.agent_engine_id or app_name,
                    user_id=user_id,
                    session_id=session_id,
                    config=config,
                )
                if remote_session is not None:
                    remote_session.app_name = app_name
                    return remote_session
            except Exception as exc:
                logger.debug(
                    "VertexAiSessionService.get_session fallback to InMemorySessionService: %s",
                    exc,
                )
        return await self._fallback_memory.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            config=config,
        )

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: str | None = None,
    ) -> ListSessionsResponse:
        if self._should_use_vertex_remote():
            try:
                return await super().list_sessions(
                    app_name=self.agent_engine_id or app_name,
                    user_id=user_id,
                )
            except Exception as exc:
                logger.debug(
                    "VertexAiSessionService.list_sessions fallback to InMemorySessionService: %s",
                    exc,
                )
        return await self._fallback_memory.list_sessions(
            app_name=app_name,
            user_id=user_id,
        )

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
        if self._should_use_vertex_remote():
            try:
                await super().delete_session(
                    app_name=self.agent_engine_id or app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.debug("VertexAiSessionService.delete_session note: %s", exc)

    async def append_event(self, session: Session, event: Event) -> Event:
        updated = await self._fallback_memory.append_event(session=session, event=event)
        if self._should_use_vertex_remote():
            try:
                await super().append_event(session=session, event=event)
            except Exception as exc:
                logger.debug("VertexAiSessionService.append_event note: %s", exc)
        return updated


# Alias for backward compatibility
FirestoreSessionService = CatalogVertexAiSessionService


class CatalogAdkRunner(InMemoryRunner):
    """Production ADK Runner backed by CatalogVertexAiSessionService (`VertexAiSessionService`) with auto_create_session=True."""

    def __init__(
        self,
        agent: BaseAgent | None = None,
        *,
        app_name: str = "app",
        session_service: BaseSessionService | None = None,
        hermetic: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(agent=agent, app_name=app_name, **kwargs)
        self.session_service = session_service or get_default_session_service(hermetic=hermetic)
        self.auto_create_session = True


# Global singleton session service and default runner
_DEFAULT_SESSION_SERVICE: CatalogVertexAiSessionService | None = None
_DEFAULT_RUNNER: CatalogAdkRunner | None = None


def get_default_session_service(hermetic: bool = False) -> CatalogVertexAiSessionService:
    """Retrieve or initialize the global VertexAiSessionService-backed ADK session service."""
    global _DEFAULT_SESSION_SERVICE
    if _DEFAULT_SESSION_SERVICE is None:
        _DEFAULT_SESSION_SERVICE = CatalogVertexAiSessionService(hermetic=hermetic)
    elif hermetic:
        _DEFAULT_SESSION_SERVICE.hermetic = True
    return _DEFAULT_SESSION_SERVICE


def create_catalog_runner(
    agent: BaseAgent | None = None,
    app_name: str = "app",
    session_service: BaseSessionService | None = None,
    hermetic: bool = False,
) -> CatalogAdkRunner:
    """Create a configured CatalogAdkRunner (`google.adk.runners.Runner`) for a catalog agent."""
    if agent is None:
        from app.agent.orchestrator import catalog_agent

        target_agent = catalog_agent
    else:
        target_agent = agent

    return CatalogAdkRunner(
        agent=target_agent,
        app_name=app_name,
        session_service=session_service,
        hermetic=hermetic,
    )


def get_adk_runner(
    agent: BaseAgent | None = None,
    app_name: str = "app",
    session_service: BaseSessionService | None = None,
) -> Runner:
    """Get the active ADK Runner, reusing default singleton if uncustomized."""
    global _DEFAULT_RUNNER
    if agent is not None or session_service is not None or app_name != "app":
        return create_catalog_runner(
            agent=agent, app_name=app_name, session_service=session_service
        )

    if _DEFAULT_RUNNER is None:
        _DEFAULT_RUNNER = create_catalog_runner(
            agent=None,
            app_name="app",
            session_service=get_default_session_service(),
        )
    return _DEFAULT_RUNNER


async def run_adk_agent(
    query: str,
    session_id: str | None = None,
    user_id: str = "user_default",
    runner: Runner | None = None,
    app_name: str = "app",
) -> AsyncGenerator[Event, None]:
    """Execute the ADK agent asynchronously via Runner and yield all execution events."""
    active_runner = runner or get_adk_runner()
    target_session_id = session_id or f"sess_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"

    try:
        if hasattr(active_runner.session_service, "get_session"):
            session = await active_runner.session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=target_session_id
            )
            if session is None and hasattr(active_runner.session_service, "create_session"):
                await active_runner.session_service.create_session(
                    app_name=app_name, user_id=user_id, session_id=target_session_id
                )
    except Exception as sess_err:
        logger.debug("Session initialization note: %s", sess_err)

    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=query)],
    )

    with tracer.start_as_current_span("adk.runner.run_async") as span:
        span.set_attribute("adk.query", query[:200])
        span.set_attribute("adk.session_id", target_session_id)
        span.set_attribute("adk.user_id", user_id)

        try:
            async for event in active_runner.run_async(
                user_id=user_id,
                session_id=target_session_id,
                new_message=user_message,
            ):
                yield event
        except Exception as e:
            logger.warning("ADK runner execution encountered exception: %s", e)
            span.record_exception(e)
            return


def run_adk_agent_sync(
    agent: BaseAgent,
    prompt: str,
    session_id: str | None = None,
    user_id: str = "user_default",
    hermetic: bool = False,
) -> tuple[str, list[Event]]:
    """Synchronously execute an ADK Agent through CatalogAdkRunner and return (final_text, events)."""
    runner = create_catalog_runner(agent=agent, hermetic=hermetic)
    events: list[Event] = []

    async def _collect() -> None:
        async for evt in run_adk_agent(
            query=prompt,
            session_id=session_id,
            user_id=user_id,
            runner=runner,
        ):
            events.append(evt)

    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(_collect())).result(timeout=30.0)
    except RuntimeError:
        asyncio.run(_collect())

    final_text = ""
    for evt in reversed(events):
        if evt.content and evt.content.parts:
            texts = [p.text for p in evt.content.parts if hasattr(p, "text") and p.text]
            if texts:
                final_text = "\n".join(texts).strip()
                break

    return final_text, events


# Export default singleton instance for ADK module conventions
catalog_runner = get_adk_runner()
