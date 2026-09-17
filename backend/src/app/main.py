"""FastAPI Application entrypoint for the Best Buy Catalog Comparison Agent."""

import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.agent.multi_agent import MultiAgentCoordinator
from app.config import Settings, get_settings
from app.data.analytics import analytics_service
from app.models import (
    Citation,
    CompareRequest,
    CompareResponse,
    ComparisonRequest,
    ComparisonResponse,
    FeedbackRequest,
    HealthResponse,
    MatrixRow,
    ProductItem,
    ProductSpec,
    UserActionRequest,
)
from app.observability import ObservabilityMiddleware, setup_observability

PROJECT_ID = "fde-bestbuy-sandbox-dev-508321"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory for FastAPI service."""
    current_settings = settings or get_settings()

    # Initialize OpenTelemetry distributed tracing and structured Cloud Logging
    setup_observability(current_settings)

    application = FastAPI(
        title="Best Buy Catalog Comparison Agent API",
        description="Agentic product comparison service grounded in Google Cloud BigQuery",
        version=current_settings.api_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.add_middleware(
        ObservabilityMiddleware,
        project_id=current_settings.project_id,
        service_name=current_settings.service_name,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=current_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["Observability"],
        summary="Service Liveness Probe",
    )
    @application.get(
        "/healthz",
        response_model=HealthResponse,
        tags=["Observability"],
        summary="Service Liveness Probe (Kubernetes/Cloud Run Alias)",
    )
    async def health(
        app_settings: Annotated[Settings, Depends(get_settings)],
    ) -> HealthResponse:
        """Health check endpoint for Cloud Run and Load Balancer liveness probes."""
        return HealthResponse(
            status="ok",
            service=app_settings.service_name,
            project=app_settings.project_id,
            version=app_settings.api_version,
            agent_version=app_settings.agent_version,
            model_version=app_settings.model_version,
            prompt_version=app_settings.prompt_version,
            environment=app_settings.environment,
        )

    @application.get(
        "/health/ready",
        response_model=dict[str, Any],
        tags=["Observability"],
        summary="Service Readiness Probe",
    )
    async def readiness(
        app_settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, Any]:
        """Readiness check endpoint verifying backend and configuration readiness."""
        return {
            "status": "ready",
            "service": app_settings.service_name,
            "project": app_settings.project_id,
        }

    @application.post(
        "/api/compare",
        response_model=ComparisonResponse,
        tags=["Comparison"],
        summary="Compare Products by Natural Language Query",
    )
    async def compare(
        request: ComparisonRequest,
        _app_settings: Annotated[Settings, Depends(get_settings)],
    ) -> ComparisonResponse:
        """Compare products based on natural language query grounded in BigQuery catalog."""
        start_time = time.perf_counter()

        if not request.query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query string must not be empty.",
            )

        coordinator = MultiAgentCoordinator()
        result = coordinator.execute(
            raw_query=request.query,
            category=request.category,
            session_id=request.session_id,
        )
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        result.latency_ms = latency_ms

        # Track session comparison count in Firestore if session_id provided
        session_count = 1
        if request.session_id:
            session_count = analytics_service.increment_session_comparisons(request.session_id)
            result.session_comparison_count = session_count

            # Log comparison action to Firestore user_actions
            analytics_service.record_user_action(
                UserActionRequest(
                    action_type="compare_request",
                    session_id=request.session_id,
                    query=request.query,
                    category=request.category,
                    target_skus=[p.sku for p in result.products],
                )
            )

        # Stream operational telemetry and cost analytics to BigQuery
        analytics_service.record_query_telemetry(
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

    @application.post(
        "/api/actions",
        response_model=dict[str, Any],
        tags=["Analytics"],
        summary="Log User Behavior and Engagement Action",
    )
    async def log_action(
        action: UserActionRequest,
        _app_settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, Any]:
        """Log user behavior events such as copy markdown or sku click to Firestore."""
        doc_id = analytics_service.record_user_action(action)
        return {"status": "recorded", "action_id": doc_id}

    @application.post(
        "/api/feedback",
        response_model=dict[str, Any],
        tags=["Analytics"],
        summary="Submit Thumbs-Up / Thumbs-Down Quality Feedback",
    )
    async def submit_feedback(
        feedback: FeedbackRequest,
        _app_settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, Any]:
        """Record thumbs-up / thumbs-down user evaluation feedback to Firestore."""
        doc_id = analytics_service.record_feedback(feedback)
        return {"status": "recorded", "feedback_id": doc_id}

    # Mount static React frontend SPA if bundled
    import os
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    candidates = [
        os.environ.get("FRONTEND_DIST_PATH", ""),
        str(Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"),
        "/app/frontend_dist",
    ]
    for dist_dir in candidates:
        if dist_dir and os.path.isdir(dist_dir):
            application.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
            break

    return application


app = create_app()

__all__ = [
    "PROJECT_ID",
    "Citation",
    "CompareRequest",
    "CompareResponse",
    "ComparisonRequest",
    "ComparisonResponse",
    "HealthResponse",
    "MatrixRow",
    "ProductItem",
    "ProductSpec",
    "app",
    "create_app",
]
