"""OpenTelemetry distributed tracing setup, context propagation, and span instrumentation."""

import functools
import inspect
import logging
import re
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanContext, StatusCode, TraceFlags

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

_GLOBAL_IN_MEMORY_EXPORTER: InMemorySpanExporter | None = None
_GLOBAL_TRACER_PROVIDER: TracerProvider | None = None


def setup_tracing(
    service_name: str,
    project_id: str,
    export_to_cloud: bool = False,
) -> tuple[TracerProvider, InMemorySpanExporter | None]:
    """Initialize OpenTelemetry TracerProvider with Cloud Trace or In-Memory exporter.

    Args:
        service_name: Logical service name (e.g. catalog-backend).
        project_id: Google Cloud project ID.
        export_to_cloud: Whether to export traces to Google Cloud Trace.

    Returns:
        Tuple of (TracerProvider, optional InMemorySpanExporter).
    """
    global _GLOBAL_IN_MEMORY_EXPORTER, _GLOBAL_TRACER_PROVIDER

    resource = Resource.create(
        {
            "service.name": service_name,
            "cloud.provider": "gcp",
            "cloud.platform": "gcp_cloud_run",
            "gcp.project_id": project_id,
        }
    )

    provider = TracerProvider(resource=resource)
    memory_exporter: InMemorySpanExporter | None = None

    if export_to_cloud:
        try:
            from opentelemetry.exporter.gcp_trace import CloudTraceSpanExporter

            cloud_exporter = CloudTraceSpanExporter(project_id=project_id)
            provider.add_span_processor(BatchSpanProcessor(cloud_exporter))
            logger.info(
                "Configured OpenTelemetry CloudTraceSpanExporter for project %s", project_id
            )
        except Exception as e:
            logger.warning("CloudTraceSpanExporter unavailable; using memory exporter: %s", e)
            memory_exporter = InMemorySpanExporter()
            provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
    else:
        memory_exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(memory_exporter))

    try:
        trace.set_tracer_provider(provider)
    except Exception:
        pass
    # Explicitly assign to guarantee override in unit test runners
    trace._TRACER_PROVIDER = provider

    _GLOBAL_IN_MEMORY_EXPORTER = memory_exporter
    _GLOBAL_TRACER_PROVIDER = provider

    return provider, memory_exporter


def get_tracer(name: str = "app.catalog_agent") -> trace.Tracer:
    """Return an OpenTelemetry Tracer instance."""
    return trace.get_tracer(name)


def get_current_trace_id() -> str | None:
    """Return the active span's 32-character hexadecimal trace ID if valid."""
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        return f"{ctx.trace_id:032x}"
    return None


def get_current_span_id() -> str | None:
    """Return the active span's 16-character hexadecimal span ID if valid."""
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        return f"{ctx.span_id:016x}"
    return None


def get_current_trace_context() -> tuple[str | None, str | None, bool]:
    """Return (trace_id, span_id, is_sampled) from current active span."""
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        return (
            f"{ctx.trace_id:032x}",
            f"{ctx.span_id:016x}",
            bool(ctx.trace_flags & TraceFlags.SAMPLED),
        )
    return (None, None, False)


def extract_cloud_trace_context(header: str | None) -> tuple[str, str, bool] | None:
    """Parse Google Cloud Trace header `X-Cloud-Trace-Context`.

    Format: `TRACE_ID/SPAN_ID;o=TRACE_TRUE`
    Example: `105445aa7843bc8bf206b12000100000/1234567890abcdef;o=1`
    """
    if not header or not isinstance(header, str):
        return None

    # Matches {trace_id}/{span_id};o={options}
    match = re.match(
        r"^(?P<trace_id>[0-9a-fA-F]{32})(?:/(?P<span_id>[0-9a-fA-F]+|\d+))?(?:;o=(?P<sampled>[01]))?$",
        header.strip(),
    )
    if not match:
        return None

    trace_id_str = match.group("trace_id").lower()
    span_id_raw = match.group("span_id")
    sampled_str = match.group("sampled")

    span_id_str = "0000000000000001"
    if span_id_raw:
        # Check if span_id_raw is decimal integer or hex
        if span_id_raw.isdigit() and len(span_id_raw) <= 20:
            val = int(span_id_raw)
            span_id_str = f"{val:016x}"
        else:
            span_id_str = span_id_raw.lower().zfill(16)[:16]

    sampled = sampled_str == "1"
    return trace_id_str, span_id_str, sampled


def extract_w3c_traceparent(header: str | None) -> tuple[str, str, bool] | None:
    """Parse W3C traceparent header.

    Format: `00-TRACE_ID-SPAN_ID-FLAGS`
    Example: `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
    """
    if not header or not isinstance(header, str):
        return None

    parts = header.strip().split("-")
    if len(parts) != 4 or parts[0] != "00":
        return None

    trace_id_str, span_id_str, flags_str = parts[1].lower(), parts[2].lower(), parts[3]
    if len(trace_id_str) != 32 or len(span_id_str) != 16:
        return None

    try:
        flags = int(flags_str, 16)
        sampled = bool(flags & 1)
        return trace_id_str, span_id_str, sampled
    except ValueError:
        return None


def format_cloud_trace_context(trace_id: str, span_id: str, sampled: bool = True) -> str:
    """Format trace context into Google Cloud Trace header value."""
    sample_flag = "1" if sampled else "0"
    return f"{trace_id}/{span_id};o={sample_flag}"


def create_span_context(
    trace_id_str: str,
    span_id_str: str,
    sampled: bool = True,
) -> SpanContext:
    """Construct an OpenTelemetry SpanContext from hex strings."""
    trace_id = int(trace_id_str, 16)
    span_id = int(span_id_str, 16)
    trace_flags = TraceFlags(TraceFlags.SAMPLED if sampled else TraceFlags.DEFAULT)
    return SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=True,
        trace_flags=trace_flags,
    )


def annotate_ai_span_metadata(span: Any) -> None:
    """Standardized OpenTelemetry AI semantic conventions for end-to-end auditability."""
    try:
        from app.config import settings

        span.set_attribute("ai.agent.name", "catalog_comparison_orchestrator")
        span.set_attribute("ai.agent.version", getattr(settings, "agent_version", "1.0.0"))
        span.set_attribute("ai.model.name", getattr(settings, "gemini_model", "gemini-2.5-pro"))
        span.set_attribute(
            "ai.model.version", getattr(settings, "model_version", "gemini-2.5-pro@001")
        )
        span.set_attribute("ai.prompt.version", getattr(settings, "prompt_version", "2026.03-v1"))
    except Exception:
        pass


def trace_span(
    span_name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to trace synchronous or asynchronous functions with OpenTelemetry.

    Args:
        span_name: Optional explicit name for the span (defaults to function name).
        attributes: Initial span attributes.
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        name = span_name or fn.__name__
        tracer = get_tracer("app.catalog_agent")

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                with tracer.start_as_current_span(name) as span:
                    annotate_ai_span_metadata(span)
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, v)
                    try:
                        result = await fn(*args, **kwargs)
                        span.set_status(StatusCode.OK)
                        return result
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(StatusCode.ERROR, str(e))
                        raise

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with tracer.start_as_current_span(name) as span:
                annotate_ai_span_metadata(span)
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = fn(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, str(e))
                    raise

        return sync_wrapper

    return decorator
