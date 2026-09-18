"""Request schemas for the Best Buy Catalog Comparison Agent."""

from pydantic import BaseModel, Field, field_validator


class ComparisonRequest(BaseModel):
    """Payload for initiating an agentic product comparison."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language product comparison query",
        examples=["Compare MacBook Air M3 and Dell XPS 13"],
    )
    category: str | None = Field(
        default=None,
        max_length=100,
        description="Optional category filter (e.g. Laptops, Tablets, Headphones, Smart Home, TVs)",
        examples=["Laptops"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of candidate products to retrieve from catalog",
        examples=[5],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional client session identifier for distributed tracing and analytics",
        examples=["session-xyz-1234"],
    )
    agent_version: str | None = Field(
        default=None,
        description="Optional registered agent version to execute (e.g., '1.0.0', '1.1.0-flash'). Defaults to active production release.",
        examples=["1.0.0"],
    )

    @field_validator("category")
    @classmethod
    def sanitize_category(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped if stripped else None


# Backward compatibility alias
CompareRequest = ComparisonRequest


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


class QueryIntentAnalysis(BaseModel):
    """Structured LLM intent classification result."""

    intent_type: str = Field(
        default="COMPARISON",
        description="Detected intent: COMPARISON, PRODUCT_SEARCH, or OPINION_OR_CHATTER",
    )
    is_comparison_eligible: bool = Field(
        default=True,
        description="Whether the query is eligible for generating a side-by-side product comparison matrix",
    )
    detected_category: str | None = Field(
        default=None,
        description="Detected product category if discernible from query (Laptops, Tablets, Headphones, Smart Home, TVs)",
    )
    target_keywords: list[str] = Field(
        default_factory=list,
        description="Product model, brand, or attribute keywords extracted from query",
    )
    reasoning: str = Field(
        default="",
        description="Reasoning explaining intent classification and eligibility verdict",
    )
