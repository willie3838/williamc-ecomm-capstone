"""ADK Agent definitions and comparison orchestrator."""

from typing import TYPE_CHECKING, Any

from app.agent.prompts import SYSTEM_INSTRUCTION

if TYPE_CHECKING:
    from app.agent.multi_agent import (
        CatalogRetrievalAgent,
        ComparisonAgentState,
        MultiAgentCoordinator,
        QueryIntentAgent,
        RelevanceDetectorAgent,
        RelevanceRerankerAgent,
        SpecComparisonAgent,
    )
    from app.agent.orchestrator import ComparisonOrchestrator, catalog_agent
    from app.agent.orchestrator import catalog_agent as root_agent
    from app.agent.runner import (
        catalog_runner,
        create_catalog_runner,
        get_adk_runner,
        run_adk_agent,
    )

__all__ = [
    "CatalogRetrievalAgent",
    "ComparisonAgentState",
    "ComparisonOrchestrator",
    "MultiAgentCoordinator",
    "QueryIntentAgent",
    "RelevanceDetectorAgent",
    "RelevanceRerankerAgent",
    "SYSTEM_INSTRUCTION",
    "SpecComparisonAgent",
    "catalog_agent",
    "catalog_runner",
    "create_catalog_runner",
    "get_adk_runner",
    "root_agent",
    "run_adk_agent",
]


def __getattr__(name: str) -> Any:
    """Lazy-load heavy ADK and Vertex AI agent classes on demand."""
    if name in {
        "CatalogRetrievalAgent",
        "ComparisonAgentState",
        "MultiAgentCoordinator",
        "QueryIntentAgent",
        "RelevanceDetectorAgent",
        "RelevanceRerankerAgent",
        "SpecComparisonAgent",
    }:
        from app.agent import multi_agent

        val = getattr(multi_agent, name)
        globals()[name] = val
        return val

    if name in {"ComparisonOrchestrator", "catalog_agent", "root_agent"}:
        from app.agent.agent import _register_reasoning_engine_query_method
        from app.agent.orchestrator import ComparisonOrchestrator, catalog_agent

        _register_reasoning_engine_query_method()
        globals()["ComparisonOrchestrator"] = ComparisonOrchestrator
        globals()["catalog_agent"] = catalog_agent
        globals()["root_agent"] = catalog_agent
        return globals()[name]

    if name in {
        "catalog_runner",
        "create_catalog_runner",
        "get_adk_runner",
        "run_adk_agent",
    }:
        from app.agent import runner

        val = getattr(runner, name)
        globals()[name] = val
        return val

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


import os as _os  # noqa: E402

if "PYTEST_CURRENT_TEST" not in _os.environ:
    try:
        from app.agent.agent import _register_reasoning_engine_query_method as _reg_re

        _reg_re()
    except Exception:
        pass
