"""Product data models and validation contracts for BigQuery catalog."""

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProductRecord(BaseModel):
    """Validated representation of an e-commerce catalog product record.

    Conforms to BigQuery table schema: `catalog.products`.
    """

    sku: str = Field(..., min_length=1, max_length=50, description="Best Buy SKU identifier")
    name: str = Field(..., min_length=2, max_length=500, description="Product commercial name")
    brand: str = Field(..., min_length=1, max_length=100, description="Manufacturer brand name")
    category: str = Field(
        ..., min_length=2, max_length=100, description="Product taxonomy category"
    )
    price: float = Field(..., ge=0.0, description="Current retail price in USD")
    shortDescription: str = Field(  # noqa: N815
        ..., min_length=2, description="Brief marketing overview and key features"
    )
    longDescription: str | None = Field(  # noqa: N815
        default=None, description="Complete detailed product summary"
    )
    rating: float | None = Field(
        default=None, ge=0.0, le=5.0, description="Customer review rating (0.0 to 5.0)"
    )
    review_count: int | None = Field(
        default=None, ge=0, description="Total count of customer reviews"
    )
    specifications: dict[str, Any] = Field(
        ..., description="Semi-structured key-value technical specifications"
    )
    url: str | None = Field(default=None, description="Direct product listing URL")
    image_url: str | None = Field(default=None, description="High-resolution product image URL")
    in_stock: bool = Field(default=True, description="Inventory availability flag")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the catalog record was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the catalog record was last updated",
    )

    @field_validator("specifications", mode="before")
    @classmethod
    def validate_specifications_not_empty(cls, v: Any) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("specifications must be a valid dictionary/JSON object.")
        return v

    def to_bigquery_row(self) -> dict[str, Any]:
        """Convert record into BigQuery compatible dictionary."""
        return {
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "price": self.price,
            "shortDescription": self.shortDescription,
            "longDescription": self.longDescription,
            "rating": self.rating,
            "review_count": self.review_count,
            "specifications": self.specifications,
            "url": self.url,
            "image_url": self.image_url,
            "in_stock": self.in_stock,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def model_validate_csv_row(cls, raw: dict[str, Any]) -> "ProductRecord":
        """Parse and validate a dictionary of string values from CSV."""
        data: dict[str, Any] = dict(raw)

        # Cast price
        if "price" in data and isinstance(data["price"], str):
            data["price"] = float(data["price"].strip())

        # Cast rating
        if "rating" in data:
            val = str(data["rating"]).strip()
            data["rating"] = float(val) if val else None

        # Cast review_count
        if "review_count" in data:
            val = str(data["review_count"]).strip()
            data["review_count"] = int(val) if val else None

        # Cast in_stock
        if "in_stock" in data and isinstance(data["in_stock"], str):
            data["in_stock"] = data["in_stock"].strip().lower() in ("true", "1", "yes")

        # Cast specifications from JSON string
        if "specifications" in data and isinstance(data["specifications"], str):
            try:
                data["specifications"] = json.loads(data["specifications"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON string in specifications: {exc}") from exc

        # Clean empty strings for optional fields
        for opt_key in ("longDescription", "url", "image_url"):
            if opt_key in data and isinstance(data[opt_key], str) and not data[opt_key].strip():
                data[opt_key] = None

        return cls(**data)
