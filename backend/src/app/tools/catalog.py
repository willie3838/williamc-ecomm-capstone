"""BigQuery product catalog query tool with parameterized SQL, distributed tracing, and retry circuit breaker."""

import json
import logging
import time
from typing import Any

from google.cloud import bigquery
from opentelemetry.trace import StatusCode

from app.config import settings
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)


def query_catalog(
    keywords: list[str],
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 10,
    client: bigquery.Client | None = None,
) -> list[dict[str, Any]]:
    """Query the Best Buy BigQuery product catalog using parameterized SQL.

    Wrapped with OpenTelemetry distributed tracing, a 2.5-second timeout,
    and exponential backoff retry for high availability and graceful degradation.

    Args:
        keywords: List of search keywords or product model names.
        category: Optional category filter (e.g. 'Laptops', 'Tablets').
        min_price: Optional minimum price filter in USD.
        max_price: Optional maximum price filter in USD.
        limit: Maximum number of products to return (default 10).
        client: Optional pre-configured BigQuery client (for dependency injection).

    Returns:
        List of product dictionaries containing specifications and metadata.
    """
    tracer = get_tracer("app.tools")

    with tracer.start_as_current_span("bigquery.query_catalog") as span:
        clean_keywords = [k.strip() for k in keywords if k and k.strip()]
        span.set_attribute("bq.keywords", str(clean_keywords))
        span.set_attribute("bq.category", category or "")
        span.set_attribute("bq.limit", limit)

        if not clean_keywords:
            logger.info("query_catalog called with empty keywords; returning empty list.")
            span.set_attribute("bq.result_count", 0)
            span.set_attribute("bq.bytes_billed", 0)
            span.set_status(StatusCode.OK)
            return []

        if client is None:
            client = bigquery.Client(project=settings.gcp_project)

        patterns = [f"%{k}%" for k in clean_keywords]
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
        job_config = bigquery.QueryJobConfig(query_parameters=query_params)

        # Resilient execution with timeout and exponential backoff retry
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
                )
                query_job = client.query(query_sql, job_config=job_config)
                # Enforce query result timeout
                results = query_job.result(timeout=timeout_seconds)
                break
            except Exception as err:
                last_error = err
                logger.warning(
                    "BigQuery catalog query attempt %d failed: %s",
                    attempt,
                    err,
                )
                if attempt < total_attempts:
                    backoff = min(0.05 * (2 ** (attempt - 1)), 0.5)
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
        for row in results:
            row_dict = dict(row) if hasattr(row, "keys") else row
            sku = str(row_dict.get("sku") or "").strip()

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

            product = {
                "sku": sku,
                "name": str(row_dict.get("name") or ""),
                "brand": str(row_dict.get("brand") or ""),
                "category": row_dict.get("category"),
                "price": float(row_dict.get("price") or 0.0),
                "rating": (
                    float(row_dict["rating"]) if row_dict.get("rating") is not None else None
                ),
                "review_count": (
                    int(row_dict["review_count"])
                    if row_dict.get("review_count") is not None
                    else None
                ),
                "specifications": specifications,
                "url": url,
                "image_url": row_dict.get("image_url"),
                "in_stock": bool(row_dict.get("in_stock", True)),
            }
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
        return products
