"""Google ADK Runner and Firestore-backed Session Service for the Catalog Comparison Agent.

Provides production-grade orchestration using ADK's native execution engine:
- `CatalogAdkRunner` (`google.adk.runners.Runner` / `InMemoryRunner` with `auto_create_session=True`).
- `FirestoreSessionService` (`BaseSessionService` / `InMemorySessionService`): Hybrid L1 in-memory
  and L2 Google Cloud Firestore (`adk_sessions` collection) session persistence across stateless
  Cloud Run container instances, with zero-latency hermetic fallback for offline evaluations.
- Asynchronous (`run_adk_agent`) and synchronous (`run_adk_agent_sync`) execution helpers.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService, Session
from google.genai import types

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


class FirestoreSessionService(InMemorySessionService):
    """Hybrid Cloud Firestore + L1 In-Memory Session Service for Google ADK Runner.

    Solves stateless horizontal scaling on Google Cloud Run by persisting ADK `Session` state
    (`state`, `app_name`, `user_id`, `session_id`, and event history summaries) to Google Cloud
    Firestore (`adk_sessions` collection), while keeping an L1 `InMemorySessionService` cache for
    sub-millisecond local reads and 100% hermetic offline evaluation execution.
    """

    def __init__(
        self,
        project_id: str | None = None,
        collection_name: str = "adk_sessions",
        firestore_client: Any = None,
        hermetic: bool = False,
    ) -> None:
        super().__init__()
        self.project_id = project_id or getattr(
            _settings, "gcp_project", "fde-bestbuy-sandbox-dev-508321"
        )
        self.collection_name = collection_name
        self._firestore_client = firestore_client
        self.hermetic = hermetic
        self._fs_init_attempted = False

    def _get_firestore_client(self) -> Any:
        """Lazily initialize Cloud Firestore client when not in hermetic/offline test mode."""
        if self._firestore_client is not None:
            return self._firestore_client
        if (
            self.hermetic
            or os.environ.get("PYTEST_CURRENT_TEST")
            or os.environ.get("HERMETIC_EVAL", "").lower() == "true"
        ):
            return None
        if not self._fs_init_attempted:
            self._fs_init_attempted = True
            try:
                from google.cloud import firestore

                self._firestore_client = firestore.Client(project=self.project_id)
            except Exception as exc:
                logger.debug("FirestoreSessionService falling back to L1 memory only: %s", exc)
                self._firestore_client = None
        return self._firestore_client

    @staticmethod
    def _doc_key(app_name: str, user_id: str, session_id: str) -> str:
        safe_app = app_name.replace("/", "_")
        safe_user = user_id.replace("/", "_")
        safe_sess = session_id.replace("/", "_")
        return f"{safe_app}__{safe_user}__{safe_sess}"

    def _persist_session_to_firestore(self, session: Session) -> None:
        """Write-through session state and event summary to Cloud Firestore."""
        db = self._get_firestore_client()
        if db is None:
            return
        try:
            doc_id = self._doc_key(session.app_name, session.user_id, session.id)
            serialized_events = []
            for evt in (session.events or [])[-25:]:
                evt_summary: dict[str, Any] = {
                    "author": getattr(evt, "author", "agent"),
                    "timestamp": getattr(evt, "timestamp", time.time()),
                }
                if getattr(evt, "content", None) and getattr(evt.content, "parts", None):
                    parts_summary = []
                    for p in evt.content.parts:
                        if getattr(p, "text", None):
                            parts_summary.append({"type": "text", "text": p.text[:500]})
                        elif getattr(p, "function_call", None):
                            parts_summary.append(
                                {
                                    "type": "function_call",
                                    "name": getattr(p.function_call, "name", ""),
                                }
                            )
                        elif getattr(p, "function_response", None):
                            parts_summary.append(
                                {
                                    "type": "function_response",
                                    "name": getattr(p.function_response, "name", ""),
                                }
                            )
                    evt_summary["parts"] = parts_summary
                serialized_events.append(evt_summary)

            payload = {
                "app_name": session.app_name,
                "user_id": session.user_id,
                "session_id": session.id,
                "state": dict(session.state) if session.state else {},
                "event_count": len(session.events or []),
                "events_summary": serialized_events,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            db.collection(self.collection_name).document(doc_id).set(payload, merge=True)
        except Exception as exc:
            logger.debug("Firestore session write-through note: %s", exc)

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        session = await super().create_session(
            app_name=app_name,
            user_id=user_id,
            state=state,
            session_id=session_id,
        )
        self._persist_session_to_firestore(session)
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Any = None,
    ) -> Session | None:
        session = await super().get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            config=config,
        )
        if session is not None:
            return session

        # Read-through from Cloud Firestore if another Cloud Run instance created this session
        db = self._get_firestore_client()
        if db is not None:
            try:
                doc_id = self._doc_key(app_name, user_id, session_id)
                snap = db.collection(self.collection_name).document(doc_id).get()
                if snap.exists:
                    data = snap.to_dict() or {}
                    restored_state = data.get("state")
                    session = await super().create_session(
                        app_name=app_name,
                        user_id=user_id,
                        state=restored_state if isinstance(restored_state, dict) else {},
                        session_id=session_id,
                    )
                    return session
            except Exception as exc:
                logger.debug("Firestore session read-through note: %s", exc)

        return None

    async def append_event(self, session: Session, event: Event) -> Event:
        updated_event = await super().append_event(session=session, event=event)
        self._persist_session_to_firestore(session)
        return updated_event

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        await super().delete_session(app_name=app_name, user_id=user_id, session_id=session_id)
        db = self._get_firestore_client()
        if db is not None:
            try:
                doc_id = self._doc_key(app_name, user_id, session_id)
                db.collection(self.collection_name).document(doc_id).delete()
            except Exception as exc:
                logger.debug("Firestore session delete note: %s", exc)


class CatalogAdkRunner(InMemoryRunner):
    """Production ADK Runner backed by FirestoreSessionService with auto_create_session=True."""

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
_DEFAULT_SESSION_SERVICE: FirestoreSessionService | None = None
_DEFAULT_RUNNER: CatalogAdkRunner | None = None


def get_default_session_service(hermetic: bool = False) -> FirestoreSessionService:
    """Retrieve or initialize the global Firestore-backed ADK session service."""
    global _DEFAULT_SESSION_SERVICE
    if _DEFAULT_SESSION_SERVICE is None:
        _DEFAULT_SESSION_SERVICE = FirestoreSessionService(hermetic=hermetic)
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
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, _collect()).result(timeout=20.0)
    else:
        asyncio.run(_collect())

    text_parts: list[str] = []
    for evt in events:
        if getattr(evt, "content", None) and getattr(evt.content, "parts", None):
            for p in evt.content.parts:
                if getattr(p, "text", None):
                    text_parts.append(p.text)

    return "\n".join(text_parts).strip(), events


# Default exported runner for ADK conventions
catalog_runner = get_adk_runner()
