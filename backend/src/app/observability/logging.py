"""Structured Google Cloud Logging integration with JSON formatting and trace correlation."""

import datetime
import json
import logging
import re
import sys
from typing import Any

from app.observability.tracing import (
    get_current_trace_context,
)

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "[REDACTED_CC]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (
        re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
        "[REDACTED_PHONE]",
    ),
]


def scrub_pii(text: str) -> str:
    """Deterministic DLP scrubber redacting SSN, credit cards, email addresses, and phone numbers."""
    if not text:
        return ""
    scrubbed = str(text)
    for pattern, token in _PII_PATTERNS:
        scrubbed = pattern.sub(token, scrubbed)
    return scrubbed


# Map Python logging levels to Google Cloud Logging severity levels
LOG_LEVEL_TO_SEVERITY: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

RESERVED_RECORD_ATTRS: set[str] = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class CloudLoggingJsonFormatter(logging.Formatter):
    """Formats LogRecords into structured JSON conforming to Google Cloud Logging standards."""

    def __init__(
        self,
        project_id: str,
        service_name: str,
        version: str = "0.1.0",
    ) -> None:
        super().__init__()
        self.project_id = project_id
        self.service_name = service_name
        self.version = version

    def format(self, record: logging.LogRecord) -> str:
        """Format the specified record as a serialized JSON string with automatic PII scrubbing."""
        message = scrub_pii(record.getMessage())

        payload: dict[str, Any] = {
            "message": message,
            "severity": LOG_LEVEL_TO_SEVERITY.get(record.levelno, "DEFAULT"),
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.UTC
            ).isoformat(),
            "serviceContext": {
                "service": self.service_name,
                "version": self.version,
            },
            "logging.googleapis.com/sourceLocation": {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            },
        }

        # Correlate active OpenTelemetry trace context if available
        trace_id, span_id, sampled = get_current_trace_context()

        # Check if record has explicit trace_id/span_id overrides
        if hasattr(record, "trace_id") and record.trace_id:
            trace_id = str(record.trace_id)
        if hasattr(record, "span_id") and record.span_id:
            span_id = str(record.span_id)

        if trace_id:
            payload["logging.googleapis.com/trace"] = (
                f"projects/{self.project_id}/traces/{trace_id}"
            )
        if span_id:
            payload["logging.googleapis.com/spanId"] = span_id
        if trace_id and span_id:
            payload["logging.googleapis.com/trace_sampled"] = sampled

        # Include stack trace if exception occurred
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Include extra custom attributes attached to log record
        for key, value in record.__dict__.items():
            if key not in RESERVED_RECORD_ATTRS and not key.startswith("_"):
                # Avoid overwriting reserved GCP payload fields
                if key not in payload:
                    payload[key] = value

        return json.dumps(payload, default=str)


def setup_logging(
    project_id: str,
    service_name: str,
    version: str = "0.1.0",
    level: str = "INFO",
) -> logging.Handler:
    """Configure the root Python logger with CloudLoggingJsonFormatter."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Remove existing stream handlers to prevent duplicate formatting
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    formatter = CloudLoggingJsonFormatter(
        project_id=project_id,
        service_name=service_name,
        version=version,
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    return handler
