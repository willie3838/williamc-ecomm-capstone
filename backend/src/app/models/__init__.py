"""Data models and schemas for Best Buy Catalog Comparison Agent."""

from app.models.analytics import FeedbackRequest, SessionMetricsResponse, UserActionRequest
from app.models.product import ProductRecord
from app.models.requests import (
    CatalogQueryInput,
    ChatMessage,
    ChatRequest,
    CompareRequest,
    ComparisonRequest,
    QueryIntentAnalysis,
)
from app.models.responses import (
    AgentVersionsResponse,
    AgentVersionSummary,
    CatalogResponse,
    ChatResponse,
    Citation,
    CompareResponse,
    ComparisonResponse,
    HealthResponse,
    MatrixRow,
    ProductItem,
    ProductSpec,
)

__all__ = [
    "AgentVersionSummary",
    "AgentVersionsResponse",
    "CatalogQueryInput",
    "CatalogResponse",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "Citation",
    "CompareRequest",
    "CompareResponse",
    "ComparisonRequest",
    "ComparisonResponse",
    "FeedbackRequest",
    "HealthResponse",
    "MatrixRow",
    "ProductItem",
    "ProductRecord",
    "ProductSpec",
    "QueryIntentAnalysis",
    "SessionMetricsResponse",
    "UserActionRequest",
]
