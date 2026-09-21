"""FastAPI Application entrypoint for the Best Buy Catalog Comparison Agent."""

from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.agent_card import build_a2a_agent_card
from app.agent.orchestrator import ComparisonOrchestrator
from app.config import Settings, get_settings
from app.models import (
    AgentVersionsResponse,
    AgentVersionSummary,
    Citation,
    CompareRequest,
    CompareResponse,
    ComparisonRequest,
    ComparisonResponse,
    HealthResponse,
    MatrixRow,
    ProductItem,
    ProductSpec,
)
from app.observability import ObservabilityMiddleware, setup_observability
from app.routes import compare_router
from app.tools.catalog import catalog_circuit_breaker

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
        allow_credentials=("*" not in current_settings.cors_origins),
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
        """Readiness check endpoint verifying BigQuery, Vertex AI, and circuit breaker readiness."""
        circuit_state = catalog_circuit_breaker.state
        bq_ready = bool(
            app_settings.gcp_project and app_settings.bq_dataset and circuit_state != "OPEN"
        )
        vertex_ready = bool(app_settings.gemini_model and app_settings.gcp_project)
        return {
            "status": "ready" if (bq_ready and vertex_ready) else "degraded",
            "service": app_settings.service_name,
            "project": app_settings.project_id,
            "api_version": "v1",
            "dependencies": {
                "bigquery": "ready" if bq_ready else "degraded",
                "vertex_ai": "ready" if vertex_ready else "degraded",
                "circuit_breaker": circuit_state,
            },
        }

    @application.get(
        "/.well-known/agent-card.json",
        tags=["Agent Registry"],
        summary="A2A Agent Card Discovery Endpoint",
    )
    async def well_known_agent_card(request: Request) -> JSONResponse:
        """Expose A2A Agent Card conforming to Google Cloud Agent Registry protocol."""
        base_url = str(request.base_url).rstrip("/")
        card = build_a2a_agent_card(base_url=base_url)
        return JSONResponse(content=card)

    # Mount versioned API router (/api/v1) and backward-compatible alias (/api)
    application.include_router(compare_router, prefix="/api/v1")
    application.include_router(compare_router, prefix="/api")

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
    "AgentVersionSummary",
    "AgentVersionsResponse",
    "Citation",
    "CompareRequest",
    "CompareResponse",
    "ComparisonOrchestrator",
    "ComparisonRequest",
    "ComparisonResponse",
    "HealthResponse",
    "MatrixRow",
    "ProductItem",
    "ProductSpec",
    "app",
    "create_app",
]
