"""ADK Agent definitions and comparison orchestrator."""

from typing import TYPE_CHECKING, Any

from app.agent.prompts import SYSTEM_INSTRUCTION

if TYPE_CHECKING:
    from app.agent.compaction import (
        SUMMARY_BANNER_PREFIX,
        CatalogAnchoredEventSummarizer,
        flush_events_to_memory_before_compaction,
        prune_tool_outputs,
        prune_tool_outputs_callback,
    )
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
    "CatalogAnchoredEventSummarizer",
    "CatalogRetrievalAgent",
    "ComparisonAgentState",
    "ComparisonOrchestrator",
    "MultiAgentCoordinator",
    "QueryIntentAgent",
    "RelevanceDetectorAgent",
    "RelevanceRerankerAgent",
    "SUMMARY_BANNER_PREFIX",
    "SYSTEM_INSTRUCTION",
    "SpecComparisonAgent",
    "catalog_agent",
    "catalog_runner",
    "create_catalog_runner",
    "flush_events_to_memory_before_compaction",
    "get_adk_runner",
    "prune_tool_outputs",
    "prune_tool_outputs_callback",
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

    if name in {
        "CatalogAnchoredEventSummarizer",
        "SUMMARY_BANNER_PREFIX",
        "flush_events_to_memory_before_compaction",
        "prune_tool_outputs",
        "prune_tool_outputs_callback",
    }:
        from app.agent import compaction

        val = getattr(compaction, name)
        globals()[name] = val
        return val

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


try:
    from app.agent.agent import _register_reasoning_engine_query_method as _reg_re

    _reg_re()
except Exception:
    pass
