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
        default="0.1.0",
        description="Current application release version",
        examples=["0.1.0"],
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
    url: str = Field(..., description="Canonical Best Buy product URL")
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


# Backward compatibility alias
CompareResponse = ComparisonResponse
