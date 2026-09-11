"""FastAPI Application entrypoint for the Best Buy Catalog Comparison Agent."""

from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

PROJECT_ID = "fde-bestbuy-sandbox-dev-508321"

app = FastAPI(
    title="Best Buy Catalog Comparison Agent API",
    description="Agentic product comparison service grounded in Google Cloud BigQuery",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    service: str = Field(..., examples=["catalog-backend"])
    project: str = Field(..., examples=[PROJECT_ID])
    version: str = Field(..., examples=["0.1.0"])


class CompareRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural language comparison query")
    category: str | None = Field(
        default=None, description="Optional category filter (e.g. Laptops)"
    )


class MatrixRow(BaseModel):
    feature: str
    values: dict[str, Any]
    winner_sku: str | None = None


class CompareResponse(BaseModel):
    summary: str
    products: list[dict[str, Any]]
    comparison_matrix: list[MatrixRow]
    citations: list[dict[str, str]]


@app.get("/health", response_model=HealthResponse, tags=["Observability"])
async def health() -> HealthResponse:
    """Health check endpoint for Cloud Run and Load Balancer liveness probes."""
    return HealthResponse(
        status="ok",
        service="catalog-backend",
        project=PROJECT_ID,
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

    # Initial scaffolding response - fully replaced when ADK agent is executed
    return CompareResponse(
        summary=f"Comparison query received: '{request.query}'. Agent retrieval ready.",
        products=[],
        comparison_matrix=[],
        citations=[],
    )
