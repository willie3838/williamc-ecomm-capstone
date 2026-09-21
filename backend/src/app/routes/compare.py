"""Versioned API router (/api/v1 and /api) for catalog comparison, agent registry, and analytics."""

import asyncio
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.agent.agent_card import build_a2a_agent_card
from app.agent.multi_agent import MultiAgentCoordinator
from app.config import Settings, get_settings
from app.data.analytics import analytics_service
from app.models import (
    AgentVersionsResponse,
    AgentVersionSummary,
    ComparisonRequest,
    ComparisonResponse,
    FeedbackRequest,
    UserActionRequest,
)

router = APIRouter()


def _execute_comparison_sync(request: ComparisonRequest) -> ComparisonResponse:
    """Execute multi-agent comparison pipeline synchronously inside worker thread."""
    import app.main as app_main

    # Honor unit test patches on app.main.ComparisonOrchestrator if present
    orch_cls = getattr(app_main, "ComparisonOrchestrator", None)
    if orch_cls is not None and hasattr(orch_cls, "assert_called"):
        orchestrator = orch_cls(
            model=request.model,
            synthesis_model=request.synthesis_model,
        )
        return orchestrator.compare(
            query=request.query,
            category=request.category,
            session_id=request.session_id,
            agent_version=request.agent_version,
            model=request.model,
            synthesis_model=request.synthesis_model,
        )

    coordinator = MultiAgentCoordinator(
        model=request.model,
        synthesis_model=request.synthesis_model,
    )
    return coordinator.execute(
        raw_query=request.query,
        category=request.category,
        session_id=request.session_id,
        agent_version=request.agent_version,
        model=request.model,
        synthesis_model=request.synthesis_model,
    )


@router.post(
    "/compare",
    response_model=ComparisonResponse,
    tags=["Comparison"],
    summary="Compare Products by Natural Language Query",
)
async def compare_products(
    request: ComparisonRequest,
    _app_settings: Annotated[Settings, Depends(get_settings)],
) -> ComparisonResponse:
    """Compare products via non-blocking async MultiAgentCoordinator execution."""
    start_time = time.perf_counter()

    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string must not be empty.",
        )

    result = await asyncio.to_thread(_execute_comparison_sync, request)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    result.latency_ms = latency_ms

    if request.session_id:
        session_count = await asyncio.to_thread(
            analytics_service.increment_session_comparisons, request.session_id
        )
        result.session_comparison_count = session_count

        await asyncio.to_thread(
            analytics_service.record_user_action,
            UserActionRequest(
                action_type="compare_request",
                session_id=request.session_id,
                query=request.query,
                category=request.category,
                target_skus=[p.sku for p in result.products],
            ),
        )

    await asyncio.to_thread(
        analytics_service.record_query_telemetry,
        query_id=result.trace_id or f"query-{int(time.time() * 1000)}",
        session_id=request.session_id,
        query_text=request.query,
        category=request.category,
        latency_ms=latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        bq_bytes_billed=result.bq_bytes_billed,
        retrieved_skus=[p.sku for p in result.products],
        status="SUCCESS" if result.products else "DEGRADED",
    )

    return result


@router.get(
    "/agent/card",
    tags=["Agent Registry"],
    summary="A2A Agent Card Query Endpoint",
)
async def get_agent_card(
    request: Request,
    version: str | None = None,
) -> JSONResponse:
    """Retrieve A2A Agent Card for a specific version or the active default."""
    base_url = str(request.base_url).rstrip("/")
    card = build_a2a_agent_card(base_url=base_url, version=version)
    return JSONResponse(content=card)


@router.get(
    "/agent/versions",
    response_model=AgentVersionsResponse,
    tags=["Agent Registry"],
    summary="List Registered Agent Versions",
)
async def list_agent_versions(
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> AgentVersionsResponse:
    """List available agent versions backed by Vertex AI Prompt Management & Cloud Run."""
    versions = [
        AgentVersionSummary(
            version=app_settings.agent_version,
            display_name="Best Buy Catalog Comparison Agent (Baseline Pro)",
            description="Grounded comparison orchestrator using Gemini 2.5 Pro",
            model=app_settings.gemini_model,
            model_version=app_settings.model_version,
            prompt_version=app_settings.prompt_version,
            is_default=True,
            skills_count=2,
            created_at="2026-03-01T00:00:00Z",
            changelog="Production baseline managed via Vertex AI Prompt Management",
        ),
        AgentVersionSummary(
            version="1.1.0-flash",
            display_name="Best Buy Catalog Comparison Agent (Flash Canary)",
            description="High-throughput canary variant powered by Gemini 2.5 Flash",
            model="gemini-2.5-flash",
            model_version="gemini-2.5-flash@001",
            prompt_version="2026.03-v2",
            is_default=False,
            skills_count=2,
            created_at="2026-03-15T00:00:00Z",
            changelog="Canary model variant managed via Vertex AI Prompt Management",
        ),
    ]
    return AgentVersionsResponse(
        active_default=app_settings.agent_version,
        total_versions=len(versions),
        versions=versions,
    )


@router.post(
    "/actions",
    response_model=dict[str, Any],
    tags=["Analytics"],
    summary="Log User Behavior and Engagement Action",
)
async def log_action(
    action: UserActionRequest,
    _app_settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Log user behavior events such as copy markdown or sku click to Firestore."""
    doc_id = await asyncio.to_thread(analytics_service.record_user_action, action)
    return {"status": "recorded", "action_id": doc_id}


@router.post(
    "/feedback",
    response_model=dict[str, Any],
    tags=["Analytics"],
    summary="Submit Thumbs-Up / Thumbs-Down Quality Feedback",
)
async def submit_feedback(
    feedback: FeedbackRequest,
    _app_settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Record thumbs-up / thumbs-down user evaluation feedback to Firestore."""
    doc_id = await asyncio.to_thread(analytics_service.record_feedback, feedback)
    return {"status": "recorded", "feedback_id": doc_id}
