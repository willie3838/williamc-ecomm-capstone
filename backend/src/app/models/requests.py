"""Request schemas for comparison queries and tool inputs."""

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    """User comparison request payload."""

    query: str = Field(..., min_length=3, description="Natural language comparison query")
    category: str | None = Field(
        default=None, description="Optional product category filter (e.g., Laptops, Tablets)"
    )


class CatalogQueryInput(BaseModel):
    """Input parameters for the query_catalog BigQuery tool."""

    keywords: list[str] = Field(
        ...,
        min_length=1,
        description="List of product keywords, brands, or model names to query",
    )
    category: str | None = Field(
        default=None, description="Optional category filter (e.g., Laptops, Tablets)"
    )
    min_price: float | None = Field(default=None, ge=0.0, description="Minimum price filter")
    max_price: float | None = Field(default=None, ge=0.0, description="Maximum price filter")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of products to return")
