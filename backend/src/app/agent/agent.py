"""Google ADK entrypoint module for ADK CLI and Playground.

Exposes `root_agent` for `adk web` / `adk run` / `adk eval`.
"""

from __future__ import annotations

from app.agent.orchestrator import catalog_agent

# Standard ADK Agent entrypoint symbol
root_agent = catalog_agent
agent = catalog_agent

__all__ = ["agent", "catalog_agent", "root_agent"]
