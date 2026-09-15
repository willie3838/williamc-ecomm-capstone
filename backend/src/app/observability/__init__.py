"""Observability package for OpenTelemetry distributed tracing and Google Cloud Logging."""

from app.config import Settings
from app.observability.logging import CloudLoggingJsonFormatter, setup_logging
from app.observability.middleware import ObservabilityMiddleware
from app.observability.tracing import (
    extract_cloud_trace_context,
    extract_w3c_traceparent,
    format_cloud_trace_context,
    get_current_span_id,
    get_current_trace_context,
    get_current_trace_id,
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
    "extract_cloud_trace_context",
    "extract_w3c_traceparent",
    "format_cloud_trace_context",
    "get_current_span_id",
    "get_current_trace_context",
    "get_current_trace_id",
    "get_tracer",
    "setup_logging",
    "setup_observability",
    "setup_tracing",
    "trace_span",
]
