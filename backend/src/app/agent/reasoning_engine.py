"""Vertex AI Reasoning Engine interface for TechBuy Catalog Comparison Agent.

Implements the official Vertex AI Agent Runtime (Reasoning Engine) contract:
- `set_up()`: Initializes the internal ADK MultiAgentCoordinator instance.
- `query()`: Serves synchronous query requests from Vertex AI or Cloud Run gateway.
- `stream_query()`: Serves streaming turn events for interactive playground / clients.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from app.agent.multi_agent import MultiAgentCoordinator
from app.config import settings
from app.models.responses import CompareResponse

logger = logging.getLogger(__name__)


class CatalogComparisonReasoningEngine:
    """Vertex AI Reasoning Engine adapter exposing query & stream_query."""

    def __init__(
        self,
        project_id: str | None = None,
        region: str | None = None,
        model: str | None = None,
        synthesis_model: str | None = None,
    ) -> None:
        self.project_id = project_id or settings.gcp_project
        self.region = region or settings.region
        self.model = model
        self.synthesis_model = synthesis_model
        self._coordinator: MultiAgentCoordinator | None = None

    def set_up(self) -> None:
        """Initialize MultiAgentCoordinator upon remote deployment in Agent Runtime."""
        self._coordinator = MultiAgentCoordinator(
            model=self.model,
            synthesis_model=self.synthesis_model,
        )
        logger.info(
            "Initialized CatalogComparisonReasoningEngine coordinator (model=%s, synthesis=%s)",
            self.model,
            self.synthesis_model,
        )

    def query(
        self,
        query: str,
        category: str | None = None,
        session_id: str | None = None,
        agent_version: str | None = None,
        model: str | None = None,
        synthesis_model: str | None = None,
    ) -> dict[str, Any]:
        """Serve comparison query on Vertex AI Agent Runtime."""
        if self._coordinator is None:
            self.set_up()
        assert self._coordinator is not None

        response: CompareResponse = self._coordinator.execute(
            raw_query=query,
            category=category,
            session_id=session_id,
            agent_version=agent_version,
            model=model or self.model,
            synthesis_model=synthesis_model or self.synthesis_model,
        )
        return response.model_dump()

    def stream_query(
        self,
        query: str,
        category: str | None = None,
        session_id: str | None = None,
        agent_version: str | None = None,
        model: str | None = None,
        synthesis_model: str | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Serve streaming turn events for Vertex AI Agent Runtime :streamQuery."""
        result = self.query(
            query=query,
            category=category,
            session_id=session_id,
            agent_version=agent_version,
            model=model,
            synthesis_model=synthesis_model,
        )
        yield {"event_type": "comparison_completed", "data": result}


# Default module instance for Vertex AI Reasoning Engine serialization
reasoning_engine = CatalogComparisonReasoningEngine()
