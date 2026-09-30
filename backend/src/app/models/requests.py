from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.responses import MatrixRow, ProductSpec


class ChatMessage(BaseModel):
    """Single message in a conversational comparison chat history."""

    role: Literal["user", "assistant", "system"] = Field(
        ...,
        description="Role of the message sender",
        examples=["user"],
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Text content of the message",
        examples=["Which laptop has longer battery life?"],
    )


class ComparisonRequest(BaseModel):
    """Payload for initiating an agentic product comparison."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=4000,
        description="Natural language product comparison query or rich attribute-grounded prompt",
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
        description="Optional registered agent version to execute (e.g., '1.0.0', '1.1.0-flash', '1.2.0-tiered'). Defaults to active production release.",
        examples=["1.0.0"],
    )
    model: str | None = Field(
        default=None,
        description="Optional foundation model override for routing, intent, and reranking (e.g., 'gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-1.5-flash', 'tiered-hybrid').",
        examples=["gemini-2.5-flash"],
    )
    synthesis_model: str | None = Field(
        default=None,
        description="Optional foundation model override for comparison narrative and trade-off synthesis (e.g., 'gemini-2.5-pro').",
        examples=["gemini-2.5-pro"],
    )
    conversation_history: list["ChatMessage"] = Field(
        default_factory=list,
        description="Optional prior multi-turn conversational chat history for context",
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


class ComparisonSynthesis(BaseModel):
    """Structured response schema for LLM comparison narrative synthesis and persona recommendations."""

    summary: str = Field(
        ...,
        description="Comprehensive grounded narrative comparing the products across key features, strictly citing [SKU: <sku>].",
    )
    recommendations: str | None = Field(
        default=None,
        description="Optional tailored buying guidance explaining which product to choose based on user persona or priority use cases, strictly citing [SKU: <sku>].",
    )

    @field_validator("summary", mode="before")
    @classmethod
    def coerce_summary_to_str(cls, v: object) -> str:
        if isinstance(v, list):
            return " ".join(str(item) for item in v if item is not None)
        return str(v) if v is not None else ""

    @field_validator("recommendations", mode="before")
    @classmethod
    def coerce_recommendations_to_str(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, list):
            return "\n".join(str(item) for item in v if item is not None)
        if isinstance(v, dict):
            return "\n".join(f"{k}: {val}" for k, val in v.items())
        return str(v)


class CandidateRankItem(BaseModel):
    """Individual SKU relevance score from the LLM reranker."""

    sku: str = Field(..., description="Product SKU identifier")
    score: float = Field(..., ge=0.0, le=10.0, description="Relevance score from 0.0 to 10.0")


class CandidateRankingResponse(BaseModel):
    """Structured response schema for LLM candidate product reranking."""

    rankings: list[CandidateRankItem] = Field(
        default_factory=list,
        description="Candidate products scored and sorted by relevance descending",
    )


class ChatRequest(BaseModel):
    """Payload for conversational follow-up questions grounded in compared products."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User follow-up question regarding the compared products or specifications",
        examples=["Which laptop has longer battery life for cross-country flights?"],
    )
    conversation_history: list[ChatMessage] = Field(
        default_factory=list,
        description="Prior conversational messages in this multi-turn thread",
    )
    products: list[ProductSpec] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of compared product entities grounding the conversation",
    )
    comparison_matrix: list[MatrixRow] = Field(
        default_factory=list,
        description="Side-by-side specification comparison matrix for reference",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional client session identifier for distributed tracing and analytics",
        examples=["session-xyz-1234"],
    )
    model: str | None = Field(
        default=None,
        description="Optional model override for follow-up reasoning",
        examples=["gemini-2.5-flash"],
    )
    synthesis_model: str | None = Field(
        default=None,
        description="Optional model override for synthesis response",
    )
    agent_version: str | None = Field(
        default=None,
        description="Optional agent version identifier",
        examples=["1.0.0"],
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message cannot be empty or whitespace only.")
        return stripped


ChatRequest.model_rebuild()
