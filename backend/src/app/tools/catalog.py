"""BigQuery product catalog query tool with parameterized SQL, distributed tracing, TTL cache, and circuit breaker."""

import json
import logging
import random
import re
import threading
import time
from collections import OrderedDict
from typing import Any

from google.cloud import bigquery
from opentelemetry.trace import StatusCode

from app.config import settings
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)


class CatalogCircuitBreaker:
    """Thread-safe three-state circuit breaker (CLOSED -> OPEN -> HALF_OPEN) for BigQuery resilience."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout_sec: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self._state = "CLOSED"
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if (
                self._state == "OPEN"
                and (time.monotonic() - self._last_failure_time) >= self.recovery_timeout_sec
            ):
                self._state = "HALF_OPEN"
            return self._state

    def allow_request(self) -> bool:
        return self.state in ("CLOSED", "HALF_OPEN")

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = "CLOSED"

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = "OPEN"

    def reset(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = "CLOSED"
            self._last_failure_time = 0.0


class CatalogResponseCache:
    """Thread-safe TTL + LRU response cache for deterministic catalog queries."""

    def __init__(self, max_size: int = 256, ttl_seconds: int = 300) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> list[dict[str, Any]] | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, data = entry
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return [dict(item) for item in data]

    def set(self, key: str, value: list[dict[str, Any]]) -> None:
        with self._lock:
            self._store[key] = (
                time.monotonic() + self.ttl_seconds,
                [dict(item) for item in value],
            )
            self._store.move_to_end(key)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


catalog_circuit_breaker = CatalogCircuitBreaker()
catalog_cache = CatalogResponseCache(ttl_seconds=getattr(settings, "cache_ttl_seconds", 300))


def query_catalog(
    keywords: list[str],
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 10,
    client: Any = None,
    use_cache: bool | None = None,
) -> list[dict[str, Any]]:
    """Query the Best Buy BigQuery product catalog using parameterized SQL.

    Wrapped with OpenTelemetry distributed tracing, a 2.5-second timeout,
    TTL/LRU caching, circuit-breaker state management, and randomized full-jitter
    exponential backoff retry for high availability and graceful degradation.

    Args:
        keywords: List of search keywords or product model names.
        category: Optional category filter (e.g. 'Laptops', 'Tablets').
        min_price: Optional minimum price filter in USD.
        max_price: Optional maximum price filter in USD.
        limit: Maximum number of products to return (default 10).
        client: Optional pre-configured BigQuery client (for dependency injection).
        use_cache: Optional flag to enable/disable TTL caching (defaults to True when client is None).

    Returns:
        List of product dictionaries containing specifications and metadata.
    """
    tracer = get_tracer("app.tools")

    with tracer.start_as_current_span("bigquery.query_catalog") as span:
        clean_keywords = [k.strip() for k in keywords if k and k.strip()]
        span.set_attribute("bq.keywords", str(clean_keywords))
        span.set_attribute("bq.category", category or "")
        span.set_attribute("bq.limit", limit)

        try:
            from evals.trajectory_grader import TrajectoryRecorder

            active_recorder = TrajectoryRecorder.get_current()
            if active_recorder is not None:
                active_recorder.record_call(
                    name="query_catalog",
                    args={
                        "keywords": clean_keywords,
                        "category": category,
                        "min_price": min_price,
                        "max_price": max_price,
                        "limit": limit,
                    },
                )
        except Exception:  # noqa: BLE001
            pass

        if not clean_keywords:
            logger.info("query_catalog called with empty keywords; returning empty list.")
            span.set_attribute("bq.result_count", 0)
            span.set_attribute("bq.bytes_billed", 0)
            span.set_status(StatusCode.OK)
            return []

        should_cache = (client is None) if use_cache is None else use_cache
        cache_key = json.dumps(
            {
                "kw": sorted(k.lower() for k in clean_keywords),
                "cat": (category or "").lower(),
                "min": min_price,
                "max": max_price,
                "lim": limit,
            },
            sort_keys=True,
        )
        if should_cache:
            cached_products = catalog_cache.get(cache_key)
            if cached_products is not None:
                span.set_attribute("bq.cache_hit", True)
                span.set_attribute("bq.result_count", len(cached_products))
                span.set_attribute("bq.bytes_billed", 0)
                span.set_status(StatusCode.OK)
                return cached_products
        span.set_attribute("bq.cache_hit", False)

        if client is None:
            import google.auth
            from google.auth.transport.requests import Request

            try:
                creds, _ = google.auth.default()
                creds.refresh(Request())
                client = bigquery.Client(project=settings.gcp_project, credentials=creds)
            except Exception:
                client = bigquery.Client(project=settings.gcp_project)

        patterns = [f"%{k}%" for k in clean_keywords]
        # Also include individual model/brand sub-tokens so non-contiguous catalog names match
        stopwords = {
            "and",
            "or",
            "the",
            "with",
            "vs",
            "versus",
            "to",
            "for",
            "in",
            "on",
            "at",
            "by",
            "from",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "what",
            "which",
            "who",
            "where",
            "when",
            "why",
            "how",
            "top",
            "best",
            "better",
            "good",
            "speed",
            "specs",
            "spec",
            "features",
            "feature",
            "tell",
            "about",
            "show",
            "give",
            "info",
            "information",
            "details",
            "describe",
            "search",
            "find",
            "look",
            "looking",
            "need",
            "want",
        }
        for k in clean_keywords:
            tokens = [
                t.lower()
                for t in re.findall(r"[a-zA-Z0-9]+", k)
                if t.lower() not in stopwords and len(t) >= 3
            ]
            for t in tokens:
                patterns.append(f"%{t}%")
        # Deduplicate while preserving order
        patterns = list(dict.fromkeys(patterns))

        query_params: list[bigquery.ArrayQueryParameter | bigquery.ScalarQueryParameter] = [
            bigquery.ArrayQueryParameter("product_patterns", "STRING", patterns),
        ]

        where_clauses = [
            "(EXISTS (SELECT 1 FROM UNNEST(@product_patterns) AS pat "
            "WHERE LOWER(name) LIKE LOWER(pat) "
            "OR LOWER(brand) LIKE LOWER(pat) "
            "OR LOWER(category) LIKE LOWER(pat)))"
        ]

        if category:
            where_clauses.append("LOWER(category) = LOWER(@category)")
            query_params.append(
                bigquery.ScalarQueryParameter("category", "STRING", category.strip())
            )

        if min_price is not None:
            where_clauses.append("price >= @min_price")
            query_params.append(
                bigquery.ScalarQueryParameter("min_price", "FLOAT64", float(min_price))
            )

        if max_price is not None:
            where_clauses.append("price <= @max_price")
            query_params.append(
                bigquery.ScalarQueryParameter("max_price", "FLOAT64", float(max_price))
            )

        where_sql = " AND ".join(where_clauses)
        query_sql = f"""
        SELECT sku, name, brand, category, price, rating, review_count, specifications, url, image_url, in_stock
        FROM `{settings.catalog_table_id}`
        WHERE {where_sql}
        ORDER BY price ASC
        LIMIT @limit
        """.strip()

        query_params.append(bigquery.ScalarQueryParameter("limit", "INT64", int(limit)))
        max_bytes = int(getattr(settings, "bq_max_bytes_billed", 50 * 1024 * 1024))
        job_config = bigquery.QueryJobConfig(
            query_parameters=query_params,
            maximum_bytes_billed=max_bytes,
        )
        span.set_attribute("bq.max_bytes_billed", max_bytes)
        span.set_attribute("bq.circuit_state", catalog_circuit_breaker.state)

        # Resilient execution with timeout and randomized full-jitter exponential backoff retry
        max_retries = max(0, settings.bq_max_retries)
        timeout_seconds = max(0.1, settings.bq_timeout_seconds)
        total_attempts = max_retries + 1
        last_error: Exception | None = None
        results = None
        query_job = None

        start_time = time.perf_counter()

        for attempt in range(1, total_attempts + 1):
            try:
                logger.info(
                    "Executing BigQuery catalog query (attempt %d/%d) for keywords: %s",
                    attempt,
                    total_attempts,
                    clean_keywords,
                    extra={
                        "sql_query": query_sql,
                        "sql_query_parameters": {
                            "product_patterns": patterns,
                            "category": category,
                            "min_price": min_price,
                            "max_price": max_price,
                            "limit": limit,
                        },
                        "attempt": attempt,
                    },
                )
                query_job = client.query(query_sql, job_config=job_config)
                # Enforce query result timeout
                results = query_job.result(timeout=timeout_seconds)
                catalog_circuit_breaker.record_success()
                break
            except Exception as err:
                last_error = err
                catalog_circuit_breaker.record_failure()
                logger.warning(
                    "BigQuery catalog query attempt %d failed: %s",
                    attempt,
                    err,
                )
                if attempt < total_attempts:
                    max_backoff = min(0.05 * (2 ** (attempt - 1)), 0.5)
                    backoff = random.uniform(0.005, max_backoff)
                    time.sleep(backoff)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        span.set_attribute("bq.latency_ms", latency_ms)

        if results is None:
            # All retry attempts exhausted; record exception and re-raise to avoid muted errors
            if last_error:
                span.record_exception(last_error)
                span.set_status(StatusCode.ERROR, str(last_error))
                logger.error(
                    "BigQuery query failed after %d attempts: %s",
                    total_attempts,
                    last_error,
                    exc_info=True,
                )
                raise last_error
            return []

        # Extract bytes billed metric for Cloud Trace attribute
        bytes_billed = 0
        if query_job is not None:
            raw_billed = getattr(query_job, "total_bytes_billed", None)
            if raw_billed is None:
                raw_billed = getattr(query_job, "bytes_billed", 0)
            try:
                bytes_billed = int(raw_billed)
            except (TypeError, ValueError):
                bytes_billed = 0

        span.set_attribute("bq.bytes_billed", bytes_billed)
        span.set_attribute("bq_bytes_billed", bytes_billed)

        products: list[dict[str, Any]] = []
        seen_skus: set[str] = set()
        for row in results:
            row_dict = dict(row) if hasattr(row, "keys") else row
            sku = str(row_dict.get("sku") or "").strip()

            if not sku:
                logger.warning("Quarantining row with missing primary key SKU: %s", row_dict)
                continue

            if sku in seen_skus:
                logger.debug("Deduplicating already retrieved product with SKU: %s", sku)
                continue

            specs_raw = row_dict.get("specifications")
            if isinstance(specs_raw, str):
                try:
                    specifications = json.loads(specs_raw)
                except Exception as e:
                    logger.warning("Failed to parse specifications JSON for sku %s: %s", sku, e)
                    specifications = {}
            elif isinstance(specs_raw, dict):
                specifications = specs_raw
            else:
                specifications = {}

            url = row_dict.get("url")
            if not url and sku:
                url = f"https://www.bestbuy.com/site/sku/{sku}.p"

            try:
                raw_price = row_dict.get("price")
                price = float(raw_price) if raw_price is not None else 0.0
            except (ValueError, TypeError):
                logger.warning(
                    "Quarantining row with corrupted price '%s' for sku '%s'",
                    row_dict.get("price"),
                    sku,
                )
                continue

            try:
                rating = float(row_dict["rating"]) if row_dict.get("rating") is not None else None
            except (ValueError, TypeError):
                rating = None

            try:
                review_count = (
                    int(row_dict["review_count"])
                    if row_dict.get("review_count") is not None
                    else None
                )
            except (ValueError, TypeError):
                review_count = None

            product = {
                "sku": sku,
                "name": str(row_dict.get("name") or ""),
                "brand": str(row_dict.get("brand") or ""),
                "category": row_dict.get("category"),
                "price": price,
                "rating": rating,
                "review_count": review_count,
                "specifications": specifications,
                "url": url,
                "image_url": row_dict.get("image_url"),
                "in_stock": bool(row_dict.get("in_stock", True)),
            }
            seen_skus.add(sku)
            products.append(product)

        span.set_attribute("bq.result_count", len(products))
        target_skus = [p["sku"] for p in products if p.get("sku")]
        span.set_attribute("target_skus", ",".join(target_skus))
        span.set_status(StatusCode.OK)

        logger.info(
            "Retrieved %d matched products from catalog (bytes billed: %d, latency: %.2fms)",
            len(products),
            bytes_billed,
            latency_ms,
            extra={
                "bq_bytes_billed": bytes_billed,
                "result_count": len(products),
                "target_skus": target_skus,
                "latency_ms": latency_ms,
            },
        )
        if should_cache:
            catalog_cache.set(cache_key, products)
        return products
