"""BigQuery product catalog query tool with parameterized SQL."""

import json
import logging
from typing import Any

from google.cloud import bigquery

from app.config import settings

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
    clean_keywords = [k.strip() for k in keywords if k and k.strip()]
    if not clean_keywords:
        logger.info("query_catalog called with empty keywords; returning empty list.")
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
        query_params.append(bigquery.ScalarQueryParameter("category", "STRING", category.strip()))

    if min_price is not None:
        where_clauses.append("price >= @min_price")
        query_params.append(bigquery.ScalarQueryParameter("min_price", "FLOAT64", float(min_price)))

    if max_price is not None:
        where_clauses.append("price <= @max_price")
        query_params.append(bigquery.ScalarQueryParameter("max_price", "FLOAT64", float(max_price)))

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
    logger.info("Executing BigQuery catalog query with %d keywords", len(clean_keywords))

    query_job = client.query(query_sql, job_config=job_config)
    results = query_job.result()

    products: list[dict[str, Any]] = []
    for row in results:
        # Support both Row mapping and raw dict (e.g. in tests)
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
            "rating": (float(row_dict["rating"]) if row_dict.get("rating") is not None else None),
            "review_count": (
                int(row_dict["review_count"]) if row_dict.get("review_count") is not None else None
            ),
            "specifications": specifications,
            "url": url,
            "image_url": row_dict.get("image_url"),
            "in_stock": bool(row_dict.get("in_stock", True)),
        }
        products.append(product)

    logger.info("Retrieved %d matched products from catalog", len(products))
    return products
