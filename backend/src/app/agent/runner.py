"""Google ADK Runner integration for the Best Buy Catalog Comparison Agent.

Provides production-grade orchestration using ADK's native execution engine:
- `InMemoryRunner` with stateful session management (`InMemorySessionService`).
- Asynchronous and synchronous agent invocation yielding ADK `Event` streams.
- Seamless compatibility with `ComparisonOrchestrator` and evaluation benchmarks.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING

from google.adk.runners import InMemoryRunner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from app.agent.orchestrator import catalog_agent
from app.config import get_settings
from app.observability.tracing import get_tracer

_settings = get_settings()
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault(
    "GOOGLE_CLOUD_PROJECT", getattr(_settings, "gcp_project", "fde-bestbuy-sandbox-dev-508321")
)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

if TYPE_CHECKING:
    from google.adk.agents import BaseAgent
    from google.adk.events import Event

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Global singleton session service for in-memory session persistence
_DEFAULT_SESSION_SERVICE: InMemorySessionService | None = None
_DEFAULT_RUNNER: InMemoryRunner | None = None


def get_default_session_service() -> InMemorySessionService:
    """Retrieve or initialize the global in-memory session service."""
    global _DEFAULT_SESSION_SERVICE
    if _DEFAULT_SESSION_SERVICE is None:
        _DEFAULT_SESSION_SERVICE = InMemorySessionService()
    return _DEFAULT_SESSION_SERVICE


def create_catalog_runner(
    agent: BaseAgent | None = None,
    app_name: str = "app",
    session_service: BaseSessionService | None = None,
) -> InMemoryRunner:
    """Create a new ADK InMemoryRunner instance for a catalog agent."""
    target_agent = agent or catalog_agent
    runner = InMemoryRunner(
        agent=target_agent,
        app_name=app_name,
    )
    if session_service is not None:
        runner.session_service = session_service
    return runner


def get_adk_runner(
    agent: BaseAgent | None = None,
    app_name: str = "app",
    session_service: BaseSessionService | None = None,
) -> InMemoryRunner:
    """Get the active ADK InMemoryRunner, reusing default instance if uncustomized."""
    global _DEFAULT_RUNNER
    if agent is not None or session_service is not None or app_name != "app":
        return create_catalog_runner(
            agent=agent, app_name=app_name, session_service=session_service
        )

    if _DEFAULT_RUNNER is None:
        _DEFAULT_RUNNER = create_catalog_runner(
            agent=catalog_agent,
            app_name="app",
            session_service=get_default_session_service(),
        )
    return _DEFAULT_RUNNER


# Default exported runner for ADK conventions
catalog_runner = get_adk_runner()


async def run_adk_agent(
    query: str,
    session_id: str | None = None,
    user_id: str = "user_default",
    runner: InMemoryRunner | None = None,
    app_name: str = "app",
) -> AsyncGenerator[Event, None]:
    """Execute the ADK agent asynchronously and yield all execution events.

    Args:
        query: Customer query or comparison request text.
        session_id: Optional persistent session ID.
        user_id: User identifier for session grouping.
        runner: Optional preconfigured Runner.
        app_name: Application name matching ADK project conventions.

    Yields:
        ADK Event objects representing tool calls, reasoning steps, and final response.
    """
    active_runner = runner or get_adk_runner()
    target_session_id = session_id or f"sess_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Ensure session exists in the session service
    try:
        if hasattr(active_runner.session_service, "get_session"):
            session = await active_runner.session_service.get_session(
                app_name=app_name, user_id=user_id, session_id=target_session_id
            )
            if session is None and hasattr(active_runner.session_service, "create_session"):
                await active_runner.session_service.create_session(
                    app_name=app_name, user_id=user_id, session_id=target_session_id
                )
        elif hasattr(active_runner.session_service, "create_session"):
            try:
                await active_runner.session_service.create_session(
                    app_name=app_name, user_id=user_id, session_id=target_session_id
                )
            except Exception:
                pass  # Session may already exist
    except Exception as sess_err:
        logger.debug("Session initialization note: %s", sess_err)

    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=query)],
    )

    with tracer.start_as_current_span("adk.runner.run_async") as span:
        span.set_attribute("adk.query", query)
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
