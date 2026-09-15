"""FastAPI Application entrypoint for the Best Buy Catalog Comparison Agent."""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from app.agent.orchestrator import ComparisonOrchestrator
from app.config import settings
from app.models.requests import CompareRequest
from app.models.responses import CompareResponse

PROJECT_ID = settings.gcp_project

app = FastAPI(
    title="Best Buy Catalog Comparison Agent API",
    description="Agentic product comparison service grounded in Google Cloud BigQuery",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    """Health status response schema."""

    status: str = Field(..., examples=["ok"])
    service: str = Field(..., examples=["catalog-backend"])
    project: str = Field(..., examples=[settings.gcp_project])
    version: str = Field(..., examples=["0.1.0"])


@app.get("/health", response_model=HealthResponse, tags=["Observability"])
async def health() -> HealthResponse:
    """Health check endpoint for Cloud Run and Load Balancer liveness probes."""
    return HealthResponse(
        status="ok",
        service="catalog-backend",
        project=settings.gcp_project,
        version="0.1.0",
    )


@app.post("/api/compare", response_model=CompareResponse, tags=["Comparison"])
async def compare(request: CompareRequest) -> CompareResponse:
    """Compare products based on natural language query grounded in BigQuery catalog."""
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string must not be empty.",
        )

    orchestrator = ComparisonOrchestrator()
    return orchestrator.compare(query=request.query, category=request.category)
