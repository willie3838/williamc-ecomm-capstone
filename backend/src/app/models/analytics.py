"""Pydantic models for analytics, user actions, session tracking, and feedback."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserActionRequest(BaseModel):
    """Payload for logging user behavior and engagement events."""

    action_type: Literal[
        "compare_request",
        "copy_markdown",
        "category_filter",
        "sample_click",
        "sku_click",
    ] = Field(..., description="Type of user action recorded")
    session_id: str = Field(..., description="Client session identifier")
    query: str | None = Field(default=None, description="Current search or comparison query")
    category: str | None = Field(default=None, description="Selected category filter")
    target_skus: list[str] = Field(default_factory=list, description="Target product SKUs involved")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional contextual metadata"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event creation timestamp (UTC)",
    )


class FeedbackRequest(BaseModel):
    """Payload for submitting thumbs-up / thumbs-down evaluation feedback."""

    rating: Literal["thumbs_up", "thumbs_down"] = Field(
        ..., description="User rating value (thumbs_up or thumbs_down)"
    )
    session_id: str = Field(..., description="Client session identifier")
    query: str = Field(..., description="Comparison query being evaluated")
    target_skus: list[str] = Field(default_factory=list, description="SKUs compared in the result")
    trace_id: str | None = Field(default=None, description="OpenTelemetry trace ID for correlation")
    comment: str | None = Field(default=None, description="Optional textual user feedback")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Feedback submission timestamp (UTC)",
    )


class SessionMetricsResponse(BaseModel):
    """Cumulative session comparison metrics."""

    session_id: str
    comparison_count: int
    first_seen: str
    last_seen: str
