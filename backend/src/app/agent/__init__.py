"""ADK Agent definitions and comparison orchestrator."""

from app.agent.orchestrator import ComparisonOrchestrator, catalog_agent
from app.agent.prompts import SYSTEM_INSTRUCTION

root_agent = catalog_agent

__all__ = ["ComparisonOrchestrator", "SYSTEM_INSTRUCTION", "catalog_agent", "root_agent"]
