"""ADK Agent definitions and comparison orchestrator."""

from app.agent.multi_agent import (
    CatalogRetrievalAgent,
    ComparisonAgentState,
    MultiAgentCoordinator,
    QueryIntentAgent,
    SpecComparisonAgent,
)
from app.agent.orchestrator import ComparisonOrchestrator, catalog_agent
from app.agent.prompts import SYSTEM_INSTRUCTION
from app.agent.runner import (
    catalog_runner,
    create_catalog_runner,
    get_adk_runner,
    run_adk_agent,
)

root_agent = catalog_agent

__all__ = [
    "CatalogRetrievalAgent",
    "ComparisonAgentState",
    "ComparisonOrchestrator",
    "MultiAgentCoordinator",
    "QueryIntentAgent",
    "SYSTEM_INSTRUCTION",
    "SpecComparisonAgent",
    "catalog_agent",
    "catalog_runner",
    "create_catalog_runner",
    "get_adk_runner",
    "root_agent",
    "run_adk_agent",
]
