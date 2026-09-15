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

    @field_validator("category")
    @classmethod
    def sanitize_category(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped if stripped else None
