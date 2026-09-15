"""FastAPI ASGI middleware for distributed tracing, Cloud Trace context propagation, and access logging."""

import logging
import os
import time
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.observability.tracing import (
    create_span_context,
    extract_cloud_trace_context,
    extract_w3c_traceparent,
    format_cloud_trace_context,
    get_tracer,
)

logger = logging.getLogger("app.access")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware to instrument HTTP requests with OpenTelemetry spans and structured logging."""

    def __init__(
        self,
        app: Any,
        project_id: str,
        service_name: str = "catalog-backend",
    ) -> None:
        super().__init__(app)
        self.project_id = project_id
        self.service_name = service_name
        self.tracer = get_tracer("app.http")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process incoming request, propagate or create trace context, and log outcome."""
        start_time = time.perf_counter()

        # 1. Extract or generate trace context
        cloud_trace_header = request.headers.get("x-cloud-trace-context")
        w3c_traceparent = request.headers.get("traceparent")

        extracted_context = extract_cloud_trace_context(
            cloud_trace_header
        ) or extract_w3c_traceparent(w3c_traceparent)

        if extracted_context:
            trace_id_str, parent_span_id_str, sampled = extracted_context
            parent_ctx = create_span_context(trace_id_str, parent_span_id_str, sampled=sampled)
            parent_otel_context = trace.set_span_in_context(trace.NonRecordingSpan(parent_ctx))
        else:
            trace_id_str = os.urandom(16).hex()
            parent_span_id_str = os.urandom(8).hex()
            sampled = True
            parent_ctx = create_span_context(trace_id_str, parent_span_id_str, sampled=sampled)
            parent_otel_context = trace.set_span_in_context(trace.NonRecordingSpan(parent_ctx))

        span_name = f"HTTP {request.method} {request.url.path}"
        span_id_str = parent_span_id_str

        with self.tracer.start_as_current_span(
            span_name,
            context=parent_otel_context,
            kind=trace.SpanKind.SERVER,
        ) as span:
            current_ctx = span.get_span_context()
            if current_ctx and current_ctx.is_valid:
                trace_id_str = f"{current_ctx.trace_id:032x}"
                span_id_str = f"{current_ctx.span_id:016x}"

            # Set standard semantic convention attributes
            client_ip = request.client.host if request.client else "unknown"
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.target", request.url.path)
            span.set_attribute("http.route", request.url.path)
            span.set_attribute("http.client_ip", client_ip)
            span.set_attribute("http.user_agent", request.headers.get("user-agent", ""))
            span.set_attribute("gcp.project_id", self.project_id)
            span.set_attribute("service.name", self.service_name)

            session_id = request.headers.get("x-session-id")
            if session_id:
                span.set_attribute("session_id", session_id)

            try:
                response = await call_next(request)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("latency_ms", latency_ms)

                if response.status_code >= 500:
                    span.set_status(
                        StatusCode.ERROR, f"Server responded with HTTP {response.status_code}"
                    )
                else:
                    span.set_status(StatusCode.OK)

                # Inject trace context headers into response
                response.headers["x-trace-id"] = trace_id_str
                response.headers["x-cloud-trace-context"] = format_cloud_trace_context(
                    trace_id_str, span_id_str, sampled=sampled
                )

                logger.info(
                    "HTTP %s %s completed with %d in %.2fms",
                    request.method,
                    request.url.path,
                    response.status_code,
                    latency_ms,
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "http_status": response.status_code,
                        "latency_ms": latency_ms,
                        "client_ip": client_ip,
                        "trace_id": trace_id_str,
                        "span_id": span_id_str,
                    },
                )
                return response

            except Exception as exc:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc))

                logger.error(
                    "Unhandled exception during HTTP %s %s after %.2fms: %s",
                    request.method,
                    request.url.path,
                    latency_ms,
                    exc,
                    exc_info=True,
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "http_status": 500,
                        "latency_ms": latency_ms,
                        "client_ip": client_ip,
                        "trace_id": trace_id_str,
                        "span_id": span_id_str,
                    },
                )

                error_response = JSONResponse(
                    status_code=500,
                    content={
                        "error": "InternalServerError",
                        "detail": "An unexpected error occurred during request processing.",
                        "trace_id": trace_id_str,
                    },
                    headers={
                        "x-trace-id": trace_id_str,
                        "x-cloud-trace-context": format_cloud_trace_context(
                            trace_id_str, span_id_str, sampled=sampled
                        ),
                    },
                )
                return error_response
