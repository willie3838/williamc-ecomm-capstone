"""Response schemas for the Best Buy Catalog Comparison Agent."""

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness and health probe status response."""

    status: str = Field(
        default="ok",
        description="Current health status of the service",
        examples=["ok"],
    )
    service: str = Field(
        default="catalog-backend",
        description="Logical service identifier",
        examples=["catalog-backend"],
    )
    project: str = Field(
        ...,
        description="Google Cloud Project hosting the backend",
        examples=["fde-bestbuy-sandbox-dev-508321"],
    )
    version: str = Field(
        default="1.0.0",
        description="Current application release version",
        examples=["1.0.0"],
    )
    agent_version: str = Field(
        default="1.0.0",
        description="Semantic version of comparison agent orchestration logic",
        examples=["1.0.0"],
    )
    model_version: str = Field(
        default="gemini-2.5-pro@001",
        description="Pinned Vertex AI foundation model checkpoint",
        examples=["gemini-2.5-pro@001"],
    )
    prompt_version: str = Field(
        default="2026.03-v1",
        description="Version identifier of active system prompt templates",
        examples=["2026.03-v1"],
    )
    environment: str = Field(
        default="development",
        description="Target deployment environment",
        examples=["development"],
    )


class ProductSpec(BaseModel):
    """Grounded product entity retrieved from the BigQuery catalog."""

    sku: str = Field(..., description="Unique Best Buy product SKU identifier")
    name: str = Field(..., description="Full commercial product name")
    brand: str = Field(..., description="Brand or manufacturer")
    category: str | None = Field(default=None, description="Product taxonomy category")
    price: float = Field(..., description="Current retail price in USD")
    rating: float | None = Field(default=None, description="Customer review rating (1.0 - 5.0)")
    review_count: int | None = Field(default=None, description="Total customer reviews")
    specifications: dict[str, Any] = Field(
        default_factory=dict, description="Hardware and technical specifications"
    )
    url: str | None = Field(default=None, description="Canonical Best Buy product URL")
    image_url: str | None = Field(default=None, description="Product image CDN URL")
    in_stock: bool = Field(default=True, description="Stock availability flag")

    @property
    def specs(self) -> dict[str, Any]:
        """Backward compatibility property."""
        return self.specifications


# Backward compatibility alias
ProductItem = ProductSpec


class MatrixRow(BaseModel):
    """Single row in the side-by-side comparison matrix."""

    feature: str = Field(..., description="Feature or specification name being compared")
    values: dict[str, Any] = Field(
        ..., description="Map of product SKU to this product's feature value"
    )
    winner_sku: str | None = Field(
        default=None,
        description="SKU of the winning product for this feature, or None if tied/neutral",
    )


class Citation(BaseModel):
    """Verifiable SKU citation pointing to catalog product."""

    sku: str = Field(..., description="Referenced product SKU")
    url: str = Field(..., description="Canonical TechBuy Retailers product URL")
    description: str | None = Field(
        default=None,
        description="Contextual note or spec citation rationale",
    )


class ComparisonResponse(BaseModel):
    """Complete structured comparison response."""

    summary: str = Field(
        ..., description="Agent synthesis narrative highlighting key differences and trade-offs"
    )
    products: list[ProductSpec] = Field(
        default_factory=list, description="List of matched products from BigQuery catalog"
    )
    comparison_matrix: list[MatrixRow] = Field(
        default_factory=list, description="Side-by-side specification comparison matrix"
    )
    citations: list[Citation] = Field(
        default_factory=list, description="List of verified product citations"
    )
    recommendations: str | None = Field(
        default=None, description="Optional targeted recommendations based on use-cases"
    )
    latency_ms: float | None = Field(
        default=None,
        ge=0.0,
        description="End-to-end request processing latency in milliseconds",
    )
    session_id: str | None = Field(
        default=None,
        description="Client session identifier correlated with distributed trace",
    )
    session_comparison_count: int | None = Field(
        default=None,
        description="Total number of comparisons executed in this session",
    )
    trace_id: str | None = Field(
        default=None,
        description="Distributed OpenTelemetry trace ID (32-character hex)",
    )
    input_tokens: int | None = Field(
        default=None,
        description="Number of prompt/input tokens consumed by model reasoning",
    )
    output_tokens: int | None = Field(
        default=None,
        description="Number of candidate/output tokens produced by model reasoning",
    )
    bq_bytes_billed: int | None = Field(
        default=None,
        description="Total BigQuery catalog query bytes billed",
    )
    agent_version: str | None = Field(
        default=None,
        description="Semantic version of agent orchestration logic executed",
        examples=["1.0.0"],
    )
    model_version: str | None = Field(
        default=None,
        description="Pinned foundation model version that generated response",
        examples=["gemini-2.5-pro@001"],
    )
    synthesis_model: str | None = Field(
        default=None,
        description="Foundation model used for comparison synthesis and trade-off narrative",
        examples=["gemini-2.5-pro"],
    )
    prompt_version: str | None = Field(
        default=None,
        description="System prompt template version identifier executed",
        examples=["2026.03-v1"],
    )
    timing_breakdown_ms: dict[str, float] | None = Field(
        default=None,
        description="Per-stage latency breakdown in milliseconds (intent, retrieval, relevance, synthesis)",
    )


# Backward compatibility alias
CompareResponse = ComparisonResponse


class AgentVersionSummary(BaseModel):
    """Summary information for a registered agent version."""

    version: str
    display_name: str
    description: str
    model: str
    synthesis_model: str | None = None
    model_version: str
    prompt_version: str
    is_default: bool
    skills_count: int
    created_at: str
    changelog: str = ""


class AgentVersionsResponse(BaseModel):
    """List of all registered agent versions in the Agent Registry."""

    active_default: str
    total_versions: int
    versions: list[AgentVersionSummary]
