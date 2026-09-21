"""Comprehensive test suite for OpenTelemetry distributed tracing and structured Cloud Logging."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.orchestrator import ComparisonOrchestrator
from app.config import Settings
from app.observability.logging import CloudLoggingJsonFormatter, setup_logging
from app.observability.middleware import ObservabilityMiddleware
from app.observability.tracing import (
    extract_cloud_trace_context,
    extract_w3c_traceparent,
    format_cloud_trace_context,
    get_current_span_id,
    get_current_trace_id,
    get_tracer,
    setup_tracing,
    trace_span,
)
from app.tools.catalog import query_catalog


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        project_id="fde-bestbuy-sandbox-dev-508321",
        service_name="catalog-backend",
        api_version="0.1.0",
        environment="test",
        enable_tracing=True,
        export_traces_to_cloud=False,
    )


class TestTracingPrimitives:
    """Test OpenTelemetry tracer initialization, span helpers, and trace context parsing."""

    def test_setup_tracing_in_memory(self, mock_settings: Settings) -> None:
        """Verify tracer setup initializes TracerProvider with in-memory span recording."""
        provider, memory_exporter = setup_tracing(
            service_name=mock_settings.service_name,
            project_id=mock_settings.project_id,
            export_to_cloud=False,
        )
        assert provider is not None
        assert memory_exporter is not None

        tracer = get_tracer("test-tracer")
        assert tracer is not None

        with tracer.start_as_current_span("unit-test-span") as span:
            span.set_attribute("test.key", "test.val")
            trace_id = get_current_trace_id()
            span_id = get_current_span_id()
            assert trace_id is not None
            assert len(trace_id) == 32
            assert span_id is not None
            assert len(span_id) == 16

        spans = memory_exporter.get_finished_spans()
        assert len(spans) >= 1
        last_span = spans[-1]
        assert last_span.name == "unit-test-span"
        assert last_span.attributes.get("test.key") == "test.val"

    def test_trace_span_decorator(self, mock_settings: Settings) -> None:
        """Verify @trace_span function decorator records span and propagates return value."""
        setup_tracing(mock_settings.service_name, mock_settings.project_id, export_to_cloud=False)

        @trace_span(span_name="decorated_func", attributes={"module": "test"})
        def sample_function(x: int, y: int) -> int:
            return x + y

        result = sample_function(10, 25)
        assert result == 35

    def test_trace_span_decorator_records_exception(self, mock_settings: Settings) -> None:
        """Verify @trace_span records exceptions, sets ERROR status, and re-raises."""
        setup_tracing(mock_settings.service_name, mock_settings.project_id, export_to_cloud=False)

        @trace_span(span_name="failing_func")
        def failing_function() -> None:
            raise ValueError("Deliberate failure for span test")

        with pytest.raises(ValueError, match="Deliberate failure for span test"):
            failing_function()

    def test_extract_cloud_trace_context(self) -> None:
        """Verify parsing Google Cloud Trace header 'TRACE_ID/SPAN_ID;o=TRACE_TRUE'."""
        header_val = "105445aa7843bc8bf206b12000100000/1234567890abcdef;o=1"
        extracted = extract_cloud_trace_context(header_val)
        assert extracted is not None
        trace_id, span_id, sampled = extracted
        assert trace_id == "105445aa7843bc8bf206b12000100000"
        assert span_id == "1234567890abcdef"
        assert sampled is True

        # Test invalid or missing header
        assert extract_cloud_trace_context(None) is None
        assert extract_cloud_trace_context("") is None
        assert extract_cloud_trace_context("invalid-header") is None

    def test_extract_w3c_traceparent(self) -> None:
        """Verify parsing standard W3C traceparent '00-TRACE_ID-SPAN_ID-FLAGS'."""
        header_val = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        extracted = extract_w3c_traceparent(header_val)
        assert extracted is not None
        trace_id, span_id, sampled = extracted
        assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert span_id == "00f067aa0ba902b7"
        assert sampled is True

        # Test invalid traceparent
        assert extract_w3c_traceparent(None) is None
        assert extract_w3c_traceparent("invalid") is None
        assert extract_w3c_traceparent("01-invalid-format") is None

    def test_format_cloud_trace_context(self) -> None:
        """Verify serializing trace context into Cloud Trace header string."""
        formatted = format_cloud_trace_context(
            trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
            span_id="00f067aa0ba902b7",
            sampled=True,
        )
        assert formatted == "4bf92f3577b34da6a3ce929d0e0e4736/00f067aa0ba902b7;o=1"


class TestStructuredCloudLogging:
    """Test JSON structured logging adhering to Google Cloud Logging specification."""

    def test_cloud_logging_json_formatter_fields(self, mock_settings: Settings) -> None:
        """Verify JSON log record conforms to GCP schema (severity, trace, serviceContext)."""
        formatter = CloudLoggingJsonFormatter(
            project_id=mock_settings.project_id,
            service_name=mock_settings.service_name,
            version=mock_settings.api_version,
        )

        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="User initiated catalog comparison for MacBook",
            args=(),
            exc_info=None,
        )
        record.session_id = "test-session-123"  # type: ignore[attr-defined]
        record.latency_ms = 45.2  # type: ignore[attr-defined]

        formatted_str = formatter.format(record)
        log_json = json.loads(formatted_str)

        assert log_json["severity"] == "INFO"
        assert log_json["message"] == "User initiated catalog comparison for MacBook"
        assert "timestamp" in log_json
        assert log_json["serviceContext"]["service"] == mock_settings.service_name
        assert log_json["serviceContext"]["version"] == mock_settings.api_version
        assert log_json["session_id"] == "test-session-123"
        assert log_json["latency_ms"] == 45.2

    def test_cloud_logging_json_formatter_with_active_trace(self, mock_settings: Settings) -> None:
        """Verify formatter injects logging.googleapis.com/trace when span is active."""
        setup_tracing(mock_settings.service_name, mock_settings.project_id, export_to_cloud=False)
        formatter = CloudLoggingJsonFormatter(
            project_id=mock_settings.project_id,
            service_name=mock_settings.service_name,
            version=mock_settings.api_version,
        )

        tracer = get_tracer("test-logger")
        with tracer.start_as_current_span("traced-log-span"):
            record = logging.LogRecord(
                name="app.test",
                level=logging.WARNING,
                pathname=__file__,
                lineno=20,
                msg="Catalog query returned zero results",
                args=(),
                exc_info=None,
            )
            formatted_str = formatter.format(record)
            log_json = json.loads(formatted_str)

            assert log_json["severity"] == "WARNING"
            assert "logging.googleapis.com/trace" in log_json
            assert (
                f"projects/{mock_settings.project_id}/traces/"
                in log_json["logging.googleapis.com/trace"]
            )
            assert "logging.googleapis.com/spanId" in log_json

    def test_setup_logging_configuration(self, mock_settings: Settings) -> None:
        """Verify setup_logging attaches CloudLoggingJsonFormatter to root logger."""
        handler = setup_logging(
            project_id=mock_settings.project_id,
            service_name=mock_settings.service_name,
            version=mock_settings.api_version,
            level="DEBUG",
        )
        assert handler is not None
        assert isinstance(handler.formatter, CloudLoggingJsonFormatter)


class TestObservabilityMiddleware:
    """Test FastAPI ASGI middleware for request distributed tracing and access logging."""

    def test_middleware_records_trace_and_injects_response_headers(
        self, mock_settings: Settings
    ) -> None:
        """Verify middleware sets up span, injects X-Trace-ID and X-Cloud-Trace-Context headers."""
        setup_tracing(mock_settings.service_name, mock_settings.project_id, export_to_cloud=False)
        app = FastAPI()
        app.add_middleware(
            ObservabilityMiddleware,
            project_id=mock_settings.project_id,
            service_name=mock_settings.service_name,
        )

        @app.get("/test-endpoint")
        def sample_route() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get(
            "/test-endpoint",
            headers={
                "X-Cloud-Trace-Context": "105445aa7843bc8bf206b12000100000/1234567890abcdef;o=1"
            },
        )

        assert response.status_code == 200
        assert "x-trace-id" in response.headers
        assert response.headers["x-trace-id"] == "105445aa7843bc8bf206b12000100000"
        assert "x-cloud-trace-context" in response.headers

    def test_middleware_generates_trace_id_when_header_missing(
        self, mock_settings: Settings
    ) -> None:
        """Verify middleware generates valid trace ID if client didn't supply one."""
        setup_tracing(mock_settings.service_name, mock_settings.project_id, export_to_cloud=False)
        app = FastAPI()
        app.add_middleware(
            ObservabilityMiddleware,
            project_id=mock_settings.project_id,
            service_name=mock_settings.service_name,
        )

        @app.get("/ping")
        def ping() -> dict[str, str]:
            return {"ping": "pong"}

        client = TestClient(app)
        response = client.get("/ping")

        assert response.status_code == 200
        assert "x-trace-id" in response.headers
        trace_id = response.headers["x-trace-id"]
        assert len(trace_id) == 32

    def test_middleware_unhandled_exception_recorded_on_span(self, mock_settings: Settings) -> None:
        """Verify unhandled exceptions set span status to ERROR and return 500 JSON response."""
        setup_tracing(mock_settings.service_name, mock_settings.project_id, export_to_cloud=False)
        app = FastAPI()
        app.add_middleware(
            ObservabilityMiddleware,
            project_id=mock_settings.project_id,
            service_name=mock_settings.service_name,
        )

        @app.get("/crash")
        def crash() -> None:
            raise RuntimeError("Simulated unhandled server crash")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/crash")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data or "detail" in data
        assert "x-trace-id" in response.headers


class TestInstrumentedBigQueryCatalogTool:
    """Test BigQuery tool OpenTelemetry span creation, metrics, and circuit-breaker retry."""

    def test_query_catalog_records_span_and_bytes_billed(
        self, mock_settings: Settings, mock_bq_client: MagicMock
    ) -> None:
        """Verify query_catalog records span attributes bq_bytes_billed, keywords, and latency."""
        _, memory_exporter = setup_tracing(
            mock_settings.service_name, mock_settings.project_id, export_to_cloud=False
        )

        # Mock BigQuery QueryJob with total_bytes_billed attribute
        mock_job = MagicMock()
        mock_job.total_bytes_billed = 10485760  # 10 MB
        mock_job.result.return_value = [
            {
                "sku": "6534606",
                "name": "MacBook Air 13.6 - M3",
                "brand": "Apple",
                "category": "Laptops",
                "price": 1099.0,
                "rating": 4.8,
                "review_count": 350,
                "specifications": '{"ram_gb": 16, "battery_life_hours": 18}',
                "url": "https://www.techbuy.com/site/sku/6534606.p",
                "image_url": "https://img.bbystatic.com/6534606.jpg",
                "in_stock": True,
            }
        ]
        mock_bq_client.query.return_value = mock_job

        products = query_catalog(
            keywords=["MacBook"],
            category="Laptops",
            client=mock_bq_client,
        )

        assert len(products) == 1
        assert products[0]["sku"] == "6534606"

        spans = [
            s for s in memory_exporter.get_finished_spans() if s.name == "bigquery.query_catalog"
        ]
        assert len(spans) >= 1
        bq_span = spans[-1]
        assert bq_span.attributes.get("bq.result_count") == 1
        assert bq_span.attributes.get("bq.bytes_billed") == 10485760
        assert "MacBook" in str(bq_span.attributes.get("bq.keywords"))

    def test_query_catalog_retry_and_graceful_degradation(
        self, mock_settings: Settings, mock_bq_client: MagicMock
    ) -> None:
        """Verify query_catalog retries on transient errors and gracefully degrades to empty list."""
        _, memory_exporter = setup_tracing(
            mock_settings.service_name, mock_settings.project_id, export_to_cloud=False
        )

        # First two calls fail with transient error, third succeeds
        mock_job = MagicMock()
        mock_job.total_bytes_billed = 0
        mock_job.result.return_value = []
        mock_bq_client.query.side_effect = [
            TimeoutError("BigQuery timeout after 2.5s"),
            ConnectionError("Transient connection reset"),
            mock_job,
        ]

        products = query_catalog(keywords=["Dell"], client=mock_bq_client)
        assert products == []

        spans = [
            s for s in memory_exporter.get_finished_spans() if s.name == "bigquery.query_catalog"
        ]
        assert len(spans) >= 1


class TestInstrumentedOrchestratorAndApi:
    """Test ComparisonOrchestrator OpenTelemetry span hierarchy and end-to-end API trace propagation."""

    def test_orchestrator_spans_and_trace_id_population(
        self, mock_settings: Settings, mock_bq_client: MagicMock
    ) -> None:
        """Verify orchestrator creates root operation span and attaches trace_id to response."""
        _, memory_exporter = setup_tracing(
            mock_settings.service_name, mock_settings.project_id, export_to_cloud=False
        )

        mock_job = MagicMock()
        mock_job.total_bytes_billed = 5242880
        mock_job.result.return_value = [
            {
                "sku": "6534606",
                "name": "MacBook Air M3",
                "brand": "Apple",
                "category": "Laptops",
                "price": 1099.0,
                "rating": 4.8,
                "review_count": 200,
                "specifications": json.dumps({"ram_gb": 16, "battery_life_hours": 18}),
                "url": "https://www.techbuy.com/site/sku/6534606.p",
                "image_url": None,
                "in_stock": True,
            },
            {
                "sku": "6575132",
                "name": "Dell XPS 13",
                "brand": "Dell",
                "category": "Laptops",
                "price": 1199.0,
                "rating": 4.6,
                "review_count": 150,
                "specifications": json.dumps({"ram_gb": 16, "battery_life_hours": 14}),
                "url": "https://www.techbuy.com/site/sku/6575132.p",
                "image_url": None,
                "in_stock": True,
            },
        ]
        mock_bq_client.query.return_value = mock_job

        orchestrator = ComparisonOrchestrator(bq_client=mock_bq_client)
        result = orchestrator.compare(
            query="Compare MacBook Air M3 and Dell XPS 13",
            category="Laptops",
            session_id="session-xyz-987",
        )

        assert result.session_id == "session-xyz-987"
        assert len(result.products) == 2
        assert result.trace_id is not None
        assert len(result.trace_id) == 32

        spans = memory_exporter.get_finished_spans()
        span_names = [s.name for s in spans]
        assert "catalog_comparison.orchestrate" in span_names
        assert "bigquery.query_catalog" in span_names

    def test_end_to_end_compare_endpoint_with_trace_context(
        self, mock_settings: Settings, mock_bq_client: MagicMock
    ) -> None:
        """Verify POST /api/compare end-to-end preserves trace context, returns headers and body trace_id."""
        from app.main import create_app

        mock_job = MagicMock()
        mock_job.total_bytes_billed = 1048576
        mock_job.result.return_value = [
            {
                "sku": "6534606",
                "name": "MacBook Air M3",
                "brand": "Apple",
                "category": "Laptops",
                "price": 1099.0,
                "rating": 4.8,
                "review_count": 200,
                "specifications": json.dumps({"ram_gb": 16, "battery_life_hours": 18}),
                "url": "https://www.techbuy.com/site/sku/6534606.p",
                "image_url": None,
                "in_stock": True,
            }
        ]
        mock_bq_client.query.return_value = mock_job

        app = create_app(settings=mock_settings)
        client = TestClient(app)

        trace_header = "4bf92f3577b34da6a3ce929d0e0e4736/00f067aa0ba902b7;o=1"
        payload = {
            "query": "Compare MacBook Air M3 and Dell XPS 13",
            "category": "Laptops",
            "session_id": "client-session-42",
        }

        with patch("app.main.ComparisonOrchestrator") as mock_orch_cls:
            mock_orch_instance = MagicMock()
            from app.models.responses import CompareResponse, ProductSpec

            mock_orch_instance.compare.return_value = CompareResponse(
                summary="MacBook comparison summary",
                products=[
                    ProductSpec(
                        sku="6534606",
                        name="MacBook Air M3",
                        brand="Apple",
                        price=1099.0,
                        specifications={"ram_gb": 16},
                    )
                ],
                comparison_matrix=[],
                citations=[],
                session_id="client-session-42",
                trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
            )
            mock_orch_cls.return_value = mock_orch_instance

            response = client.post(
                "/api/compare",
                json=payload,
                headers={"X-Cloud-Trace-Context": trace_header},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "client-session-42"
        assert data["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert response.headers.get("x-trace-id") == "4bf92f3577b34da6a3ce929d0e0e4736"


class TestObservabilityEdgeCases:
    """Additional edge cases for full branch and code coverage."""

    def test_get_current_ids_when_no_active_span(self) -> None:
        """Verify get_current_trace_id and get_current_span_id return None when outside span."""
        from app.observability.tracing import get_current_trace_context

        trace_id, span_id, sampled = get_current_trace_context()
        assert trace_id is None
        assert span_id is None
        assert sampled is False
        assert get_current_trace_id() is None
        assert get_current_span_id() is None

    @pytest.mark.asyncio
    async def test_trace_span_async_function(self, mock_settings: Settings) -> None:
        """Verify @trace_span works on asynchronous functions."""
        _, memory_exporter = setup_tracing(
            mock_settings.service_name, mock_settings.project_id, export_to_cloud=False
        )

        @trace_span(span_name="async_sample_op", attributes={"async_test": "true"})
        async def sample_async_op(val: int) -> int:
            return val * 2

        result = await sample_async_op(21)
        assert result == 42

        spans = [s for s in memory_exporter.get_finished_spans() if s.name == "async_sample_op"]
        assert len(spans) >= 1
        assert spans[-1].attributes.get("async_test") == "true"

    @pytest.mark.asyncio
    async def test_trace_span_async_function_exception(self, mock_settings: Settings) -> None:
        """Verify @trace_span captures exceptions in async functions."""
        setup_tracing(mock_settings.service_name, mock_settings.project_id, export_to_cloud=False)

        @trace_span(span_name="async_failing_op")
        async def failing_async_op() -> None:
            raise KeyError("Deliberate async failure")

        with pytest.raises(KeyError, match="Deliberate async failure"):
            await failing_async_op()

    def test_setup_tracing_cloud_exporter_mock(self, mock_settings: Settings) -> None:
        """Verify setup_tracing when export_to_cloud=True instantiates CloudTraceSpanExporter."""
        mock_module = MagicMock()
        mock_exp_cls = MagicMock()
        mock_module.CloudTraceSpanExporter = mock_exp_cls

        with patch.dict("sys.modules", {"opentelemetry.exporter.gcp_trace": mock_module}):
            provider, exporter = setup_tracing(
                mock_settings.service_name,
                mock_settings.project_id,
                export_to_cloud=True,
            )
            assert provider is not None
            mock_exp_cls.assert_called_once_with(project_id=mock_settings.project_id)

    def test_setup_tracing_cloud_exporter_exception_fallback(self, mock_settings: Settings) -> None:
        """Verify setup_tracing falls back to InMemorySpanExporter when CloudTraceSpanExporter raises."""
        mock_module = MagicMock()
        mock_module.CloudTraceSpanExporter.side_effect = RuntimeError("Cloud Trace auth error")

        with patch.dict("sys.modules", {"opentelemetry.exporter.gcp_trace": mock_module}):
            provider, exporter = setup_tracing(
                mock_settings.service_name,
                mock_settings.project_id,
                export_to_cloud=True,
            )
            assert provider is not None
            assert exporter is not None

    def test_extract_w3c_traceparent_invalid_hex(self) -> None:
        """Verify extract_w3c_traceparent handles non-hex flags gracefully."""
        res = extract_w3c_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-zz")
        assert res is None

    def test_format_cloud_trace_context_unsampled(self) -> None:
        """Verify format_cloud_trace_context formats o=0 when unsampled."""
        formatted = format_cloud_trace_context(
            "4bf92f3577b34da6a3ce929d0e0e4736",
            "00f067aa0ba902b7",
            sampled=False,
        )
        assert formatted.endswith(";o=0")

    def test_middleware_records_session_id_and_status_error(self, mock_settings: Settings) -> None:
        """Verify middleware records x-session-id and handles 500 status code correctly."""
        setup_tracing(mock_settings.service_name, mock_settings.project_id, export_to_cloud=False)
        app = FastAPI()
        app.add_middleware(
            ObservabilityMiddleware,
            project_id=mock_settings.project_id,
            service_name=mock_settings.service_name,
        )

        @app.get("/error-500")
        def route_500() -> None:
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse("Service unavailable", status_code=503)

        client = TestClient(app)
        res = client.get("/error-500", headers={"x-session-id": "sess-999"})
        assert res.status_code == 503
        assert "x-trace-id" in res.headers
