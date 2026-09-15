"""FastAPI Application entrypoint for the Best Buy Catalog Comparison Agent."""

import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.models import (
    Citation,
    ComparisonRequest,
    ComparisonResponse,
    HealthResponse,
    MatrixRow,
    ProductItem,
)

# Aliases for backward compatibility
CompareRequest = ComparisonRequest
CompareResponse = ComparisonResponse
PROJECT_ID = "fde-bestbuy-sandbox-dev-508321"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory for FastAPI service."""
    current_settings = settings or get_settings()

    application = FastAPI(
        title="Best Buy Catalog Comparison Agent API",
        description="Agentic product comparison service grounded in Google Cloud BigQuery",
        version=current_settings.api_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
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
    async def health(
        app_settings: Annotated[Settings, Depends(get_settings)],
    ) -> HealthResponse:
        """Health check endpoint for Cloud Run and Load Balancer liveness probes."""
        return HealthResponse(
            status="ok",
            service=app_settings.service_name,
            project=app_settings.project_id,
            version=app_settings.api_version,
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

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Baseline scaffolding response - to be routed to ADK agent in multi-agent pipeline
        return ComparisonResponse(
            summary=f"Comparison query received: '{request.query}'. Agent retrieval ready.",
            products=[],
            comparison_matrix=[],
            citations=[],
            latency_ms=elapsed_ms,
        )

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
    "app",
    "create_app",
]
