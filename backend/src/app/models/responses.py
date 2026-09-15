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


class ProductItem(BaseModel):
    """Product entity extracted and validated from catalog BigQuery table."""

    sku: str = Field(
        ...,
        description="Unique Best Buy SKU identifier",
        examples=["6534606"],
    )
    name: str = Field(
        ...,
        description="Full commercial product name",
        examples=['MacBook Air 13.6" - M3'],
    )
    brand: str = Field(
        ...,
        description="Manufacturer or brand name",
        examples=["Apple"],
    )
    price: float = Field(
        ...,
        ge=0.0,
        description="Current retail price in USD",
        examples=[1099.0],
    )
    category: str | None = Field(
        default=None,
        description="Product catalog category",
        examples=["Laptops"],
    )
    rating: float | None = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Customer review rating on a 5.0 scale",
        examples=[4.8],
    )
    specs: dict[str, Any] = Field(
        default_factory=dict,
        description="Key technical specifications grounded in catalog data",
        examples=[{"RAM": "16 GB", "Battery Life": "Up to 18 hours"}],
    )


class MatrixRow(BaseModel):
    """A single specification comparison dimension comparing multiple SKUs."""

    feature: str = Field(
        ...,
        description="Feature or specification dimension being compared",
        examples=["Battery Life"],
    )
    values: dict[str, Any] = Field(
        ...,
        description="Mapping from product SKU to verified feature value",
        examples=[{"6534606": "Up to 18 hours", "6575132": "Up to 14 hours"}],
    )
    winner_sku: str | None = Field(
        default=None,
        description="SKU determined to lead on this feature, or null for parity/neutral",
        examples=["6534606"],
    )


class Citation(BaseModel):
    """Verifiable SKU citation ensuring zero hallucination."""

    sku: str = Field(
        ...,
        description="Referenced product SKU",
        examples=["6534606"],
    )
    url: str = Field(
        ...,
        description="Canonical URL to catalog product page",
        examples=["https://www.bestbuy.com/site/sku/6534606.p"],
    )
    description: str | None = Field(
        default=None,
        description="Contextual note or spec citation rationale",
        examples=["Battery spec verified from catalog.products"],
    )


class ComparisonResponse(BaseModel):
    """Complete synthesized product comparison response."""

    summary: str = Field(
        ...,
        description="Executive summary and natural language comparative analysis",
        examples=["Direct comparison between Apple MacBook Air M3 and Dell XPS 13..."],
    )
    products: list[ProductItem] = Field(
        default_factory=list,
        description="List of compared products with grounded catalog details",
    )
    comparison_matrix: list[MatrixRow] = Field(
        default_factory=list,
        description="Structured side-by-side feature comparison rows",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Verifiable source citations matching BigQuery catalog ground truth",
    )
    latency_ms: float | None = Field(
        default=None,
        ge=0.0,
        description="End-to-end request processing latency in milliseconds",
        examples=[1245.0],
    )
