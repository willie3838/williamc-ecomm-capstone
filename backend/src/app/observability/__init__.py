from typing import Any

from app.config import Settings
from app.observability.logging import CloudLoggingJsonFormatter, get_logger, setup_logging
from app.observability.middleware import ObservabilityMiddleware
from app.observability.tracing import (
    extract_cloud_trace_context,
    extract_w3c_traceparent,
    format_cloud_trace_context,
    get_current_span_id,
    get_current_trace_context,
    get_current_trace_id,
    get_in_memory_exporter,
    get_tracer,
    setup_tracing,
    trace_span,
)


def setup_observability(settings: Settings) -> None:
    """Initialize OpenTelemetry tracing and structured Cloud Logging from application settings."""
    if settings.enable_tracing:
        setup_tracing(
            service_name=settings.service_name,
            project_id=settings.project_id,
            export_to_cloud=settings.export_traces_to_cloud,
        )

    setup_logging(
        project_id=settings.project_id,
        service_name=settings.service_name,
        version=settings.api_version,
        level=settings.log_level,
    )


__all__ = [
    "CloudLoggingJsonFormatter",
    "ObservabilityMiddleware",
    "TelemetryLogger",
    "extract_cloud_trace_context",
    "extract_w3c_traceparent",
    "format_cloud_trace_context",
    "get_current_span_id",
    "get_current_trace_context",
    "get_current_trace_id",
    "get_in_memory_exporter",
    "get_logger",
    "get_tracer",
    "setup_logging",
    "setup_observability",
    "setup_tracing",
    "telemetry_logger",
    "trace_span",
]


def __getattr__(name: str) -> Any:
    if name in ("TelemetryLogger", "telemetry_logger"):
        from app.data import analytics

        return getattr(analytics, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
