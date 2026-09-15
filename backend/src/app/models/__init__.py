"""Data models and schemas for Best Buy Catalog Comparison Agent."""

from app.models.product import ProductRecord
from app.models.requests import CatalogQueryInput, CompareRequest, ComparisonRequest
from app.models.responses import (
    Citation,
    CompareResponse,
    ComparisonResponse,
    HealthResponse,
    MatrixRow,
    ProductItem,
    ProductSpec,
)

__all__ = [
    "CatalogQueryInput",
    "Citation",
    "CompareRequest",
    "CompareResponse",
    "ComparisonRequest",
    "ComparisonResponse",
    "HealthResponse",
    "MatrixRow",
    "ProductItem",
    "ProductRecord",
    "ProductSpec",
]
