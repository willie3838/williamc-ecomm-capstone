"""Google ADK entrypoint module for ADK CLI, Playground, and Vertex AI Agent Engine.

Exposes `root_agent` for `adk web` / `adk run` / `adk eval`, and registers the
structured `query` method on `AdkApp` so Vertex AI Reasoning Engine supports both
the interactive Console Playground (`stream_query` / `async_stream_query`) and
structured `CompareResponse` RPCs (`query`) from the Cloud Run gateway.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.orchestrator import catalog_agent
from app.agent.reasoning_engine import reasoning_engine
from app.agent.runner import catalog_app

logger = logging.getLogger(__name__)

# Standard ADK Agent and App entrypoint symbols
root_agent = catalog_agent
agent = catalog_agent
app = catalog_app
adk_app = catalog_app


def _extract_message_text(message: Any) -> str | None:
    """Extract plain user query text from a string or ADK Content dict."""
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, dict):
        parts = message.get("parts")
        if isinstance(parts, list):
            texts = [
                str(p.get("text"))
                for p in parts
                if isinstance(p, dict) and p.get("text") is not None
            ]
            if texts:
                return " ".join(texts).strip()
    return None


def _format_playground_event(result: dict[str, Any]) -> dict[str, Any]:
    """Format a structured CompareResponse dict into an ADK Event dict for Vertex AI Console Playground."""
    summary = str(result.get("summary") or "")
    recs = str(result.get("recommendations") or "")
    matrix = result.get("comparison_matrix") or []
    lines = [summary]
    if isinstance(matrix, list) and matrix:
        lines.append("\n**Specification Comparison:**")
        for row in matrix:
            if isinstance(row, dict):
                feat = row.get("feature", "")
                vals = row.get("values") or {}
                winner = row.get("winner_sku")
                val_str = " vs. ".join(f"[SKU: {k}] {v}" for k, v in vals.items())
                win_str = f" *(Winner: [SKU: {winner}])*" if winner else ""
                lines.append(f"- **{feat}**: {val_str}{win_str}")
    if recs:
        lines.append(f"\n**Recommendations:**\n{recs}")
    full_text = "\n".join(lines).strip()
    try:
        from google.adk.events.event import Event
        from google.genai import types
        from vertexai.agent_engines import _utils

        ev = Event(
            author="catalog_comparison_orchestrator",
            content=types.Content(role="model", parts=[types.Part(text=full_text)]),
        )
        return _utils.dump_event_for_json(ev)
    except Exception:
        return {
            "author": "catalog_comparison_orchestrator",
            "content": {"role": "model", "parts": [{"text": full_text}]},
        }


def _register_reasoning_engine_query_method() -> None:
    """Attach structured `query()`, `stream_query`, and `async_stream_query` dispatch onto Vertex AI `AdkApp`."""
    try:
        import asyncio
        import json

        from vertexai.agent_engines import AdkApp

        def _adk_query(
            _self: Any,
            query: str,
            category: str | None = None,
            session_id: str | None = None,
            agent_version: str | None = None,
            model: str | None = None,
            synthesis_model: str | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            return reasoning_engine.query(
                query=query,
                category=category,
                session_id=session_id,
                agent_version=agent_version,
                model=model,
                synthesis_model=synthesis_model,
                **kwargs,
            )

        AdkApp.query = _adk_query  # type: ignore[attr-defined]

        orig_reg = getattr(AdkApp, "register_operations", None)
        if orig_reg is not None and not getattr(orig_reg, "_is_catalog_wrapped", False):

            def _wrapped_register_operations(self: Any) -> dict[str, list[str]]:
                ops = dict(orig_reg(self))
                sync_ops = list(ops.get("", []))
                if "query" not in sync_ops:
                    sync_ops.append("query")
                ops[""] = sync_ops
                return ops

            _wrapped_register_operations._is_catalog_wrapped = True  # type: ignore[attr-defined]
            AdkApp.register_operations = _wrapped_register_operations  # type: ignore[method-assign]

        orig_stream_query = getattr(AdkApp, "stream_query", None)
        if orig_stream_query is not None and not getattr(
            orig_stream_query, "_is_catalog_wrapped", False
        ):

            def _wrapped_stream_query(
                self: Any,
                *,
                message: Any,
                user_id: str,
                session_id: str | None = None,
                run_config: dict[str, Any] | None = None,
                **kwargs: Any,
            ) -> Any:
                parsed_msg = message
                if isinstance(message, str) and '"__compare_request__"' in message:
                    try:
                        parsed_msg = json.loads(message)
                    except Exception:
                        parsed_msg = message
                if isinstance(parsed_msg, dict) and parsed_msg.get("__compare_request__"):
                    yield reasoning_engine.query(
                        query=str(parsed_msg.get("query") or ""),
                        category=parsed_msg.get("category"),
                        session_id=parsed_msg.get("session_id") or session_id,
                        agent_version=parsed_msg.get("agent_version"),
                        model=parsed_msg.get("model"),
                        synthesis_model=parsed_msg.get("synthesis_model"),
                        stage1_model=parsed_msg.get("stage1_model"),
                        stage2_model=parsed_msg.get("stage2_model"),
                        stage3_model=parsed_msg.get("stage3_model"),
                    )
                    return
                user_text = _extract_message_text(message)
                if user_text:
                    res = reasoning_engine.query(query=user_text, session_id=session_id)
                    yield _format_playground_event(res)
                    return
                yield from orig_stream_query(
                    self,
                    message=message,
                    user_id=user_id,
                    session_id=session_id,
                    run_config=run_config,
                    **kwargs,
                )

            _wrapped_stream_query._is_catalog_wrapped = True  # type: ignore[attr-defined]
            AdkApp.stream_query = _wrapped_stream_query  # type: ignore[method-assign]

        orig_async_stream_query = getattr(AdkApp, "async_stream_query", None)
        if orig_async_stream_query is not None and not getattr(
            orig_async_stream_query, "_is_catalog_wrapped", False
        ):

            async def _wrapped_async_stream_query(
                self: Any,
                *,
                message: Any,
                user_id: str,
                session_id: str | None = None,
                session_events: list[dict[str, Any]] | None = None,
                run_config: dict[str, Any] | None = None,
                **kwargs: Any,
            ) -> Any:
                parsed_msg = message
                if isinstance(message, str) and '"__compare_request__"' in message:
                    try:
                        parsed_msg = json.loads(message)
                    except Exception:
                        parsed_msg = message
                if isinstance(parsed_msg, dict) and parsed_msg.get("__compare_request__"):
                    res = await asyncio.to_thread(
                        reasoning_engine.query,
                        query=str(parsed_msg.get("query") or ""),
                        category=parsed_msg.get("category"),
                        session_id=parsed_msg.get("session_id") or session_id,
                        agent_version=parsed_msg.get("agent_version"),
                        model=parsed_msg.get("model"),
                        synthesis_model=parsed_msg.get("synthesis_model"),
                        stage1_model=parsed_msg.get("stage1_model"),
                        stage2_model=parsed_msg.get("stage2_model"),
                        stage3_model=parsed_msg.get("stage3_model"),
                    )
                    yield res
                    return
                user_text = _extract_message_text(message)
                if user_text:
                    res = await asyncio.to_thread(
                        reasoning_engine.query,
                        query=user_text,
                        session_id=session_id,
                    )
                    yield _format_playground_event(res)
                    return
                async for event in orig_async_stream_query(
                    self,
                    message=message,
                    user_id=user_id,
                    session_id=session_id,
                    session_events=session_events,
                    run_config=run_config,
                    **kwargs,
                ):
                    yield event

            _wrapped_async_stream_query._is_catalog_wrapped = True  # type: ignore[attr-defined]
            AdkApp.async_stream_query = _wrapped_async_stream_query  # type: ignore[method-assign]
    except Exception as exc:
        logger.debug("Could not attach query method to AdkApp: %s", exc)

    try:
        import google.adk.cli.fast_api as _adk_fast_api

        allowed = getattr(_adk_fast_api, "_ALLOWED_AGENT_ENGINE_CLASS_METHODS", frozenset())
        if "query" not in allowed:
            _adk_fast_api._ALLOWED_AGENT_ENGINE_CLASS_METHODS = frozenset({*allowed, "query"})
    except Exception as exc:
        logger.debug("Could not update _ALLOWED_AGENT_ENGINE_CLASS_METHODS: %s", exc)


_register_reasoning_engine_query_method()

__all__ = [
    "adk_app",
    "agent",
    "app",
    "catalog_agent",
    "catalog_app",
    "reasoning_engine",
    "root_agent",
]
