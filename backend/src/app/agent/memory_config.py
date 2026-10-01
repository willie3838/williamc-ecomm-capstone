"""Memory Bank configuration module for Vertex AI Reasoning Engine Context Spec.

Provides `ReasoningEngineContextSpecMemoryBankConfig` and memory configuration utilities
for ADK agents deployed to Vertex AI Agent Runtime (Reasoning Engines).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from vertexai._genai.types import (
        ReasoningEngineContextSpecMemoryBankConfig as _VertexReasoningEngineContextSpecMemoryBankConfig,
    )

    ReasoningEngineContextSpecMemoryBankConfig = _VertexReasoningEngineContextSpecMemoryBankConfig
except ImportError:

    class ReasoningEngineContextSpecMemoryBankConfig(BaseModel):  # type: ignore[no-redef]
        """Specification for a Vertex AI Reasoning Engine Memory Bank."""

        customization_configs: list[dict[str, Any]] | None = Field(
            default=None,
            description="Configuration for how to customize Memory Bank behavior for a particular scope.",
        )
        disable_memory_revisions: bool | None = Field(
            default=None,
            description="If true, no memory revisions will be created for any requests to the Memory Bank.",
        )
        generation_config: dict[str, Any] | None = Field(
            default=None,
            description="Configuration for how to generate memories for the Memory Bank.",
        )
        similarity_search_config: dict[str, Any] | None = Field(
            default=None,
            description="Configuration for similarity search on memories.",
        )
        ttl_config: dict[str, Any] | None = Field(
            default=None,
            description="Configuration for automatic TTL of memories in the Memory Bank.",
        )
        structured_memory_configs: list[dict[str, Any]] | None = Field(
            default=None,
            description="Configuration for organizing structured memories for a particular scope.",
        )


def get_default_memory_bank_config() -> ReasoningEngineContextSpecMemoryBankConfig:
    """Create default ReasoningEngineContextSpecMemoryBankConfig for catalog comparison agent."""
    try:
        return ReasoningEngineContextSpecMemoryBankConfig()
    except Exception as exc:
        logger.debug("Creating default ReasoningEngineContextSpecMemoryBankConfig note: %s", exc)
        return ReasoningEngineContextSpecMemoryBankConfig.model_validate({})


__all__ = [
    "ReasoningEngineContextSpecMemoryBankConfig",
    "get_default_memory_bank_config",
]
