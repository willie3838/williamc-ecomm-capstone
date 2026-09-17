# BigQuery Catalog and Telemetry Infrastructure

# BigQuery Dataset: Product Catalog
resource "google_bigquery_dataset" "catalog" {
  dataset_id                 = var.catalog_dataset_id
  project                    = var.project_id
  location                   = var.region
  description                = "E-commerce product catalog for comparison agent"
  delete_contents_on_destroy = false

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }

  depends_on = [google_project_service.required_apis]
}

# BigQuery Table: Products
resource "google_bigquery_table" "products" {
  dataset_id = google_bigquery_dataset.catalog.dataset_id
  table_id   = var.catalog_table_id
  project    = var.project_id

  time_partitioning {
    type  = "DAY"
    field = "updated_at"
  }

  clustering = ["category", "brand", "sku"]

  schema = jsonencode([
    { name = "sku", type = "STRING", mode = "REQUIRED", description = "Best Buy SKU identifier" },
    { name = "name", type = "STRING", mode = "REQUIRED", description = "Product commercial name" },
    { name = "brand", type = "STRING", mode = "REQUIRED", description = "Product brand" },
    { name = "category", type = "STRING", mode = "REQUIRED", description = "Product category" },
    { name = "price", type = "FLOAT", mode = "REQUIRED", description = "Current price in USD" },
    { name = "shortDescription", type = "STRING", mode = "REQUIRED", description = "Brief marketing overview and key features" },
    { name = "longDescription", type = "STRING", mode = "NULLABLE", description = "Complete detailed product summary" },
    { name = "rating", type = "FLOAT", mode = "NULLABLE", description = "Customer review rating" },
    { name = "review_count", type = "INTEGER", mode = "NULLABLE", description = "Number of customer reviews" },
    { name = "specifications", type = "JSON", mode = "REQUIRED", description = "Key-value technical specs" },
    { name = "url", type = "STRING", mode = "NULLABLE", description = "Product listing URL" },
    { name = "image_url", type = "STRING", mode = "NULLABLE", description = "Product image URL" },
    { name = "in_stock", type = "BOOLEAN", mode = "REQUIRED", description = "Stock availability" },
    { name = "created_at", type = "TIMESTAMP", mode = "NULLABLE", description = "Record creation timestamp" },
    { name = "updated_at", type = "TIMESTAMP", mode = "REQUIRED", description = "Record update timestamp" }
  ])

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# BigQuery Dataset: Operational Telemetry & Evaluation Logs
resource "google_bigquery_dataset" "telemetry" {
  dataset_id                 = var.telemetry_dataset_id
  project                    = var.project_id
  location                   = var.region
  description                = "Operational telemetry and evaluation logs"
  delete_contents_on_destroy = false

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }

  depends_on = [google_project_service.required_apis]
}

# BigQuery Table: Query Telemetry Logs
resource "google_bigquery_table" "telemetry_logs" {
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  table_id   = var.telemetry_table_id
  project    = var.project_id

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  clustering = ["status", "query_id"]

  schema = jsonencode([
    { name = "query_id", type = "STRING", mode = "REQUIRED", description = "Unique query trace identifier" },
    { name = "timestamp", type = "TIMESTAMP", mode = "REQUIRED", description = "Timestamp of query invocation" },
    { name = "session_id", type = "STRING", mode = "NULLABLE", description = "Client session identifier" },
    { name = "query_text", type = "STRING", mode = "REQUIRED", description = "Raw user query text" },
    { name = "category", type = "STRING", mode = "NULLABLE", description = "Optional query category scope" },
    { name = "latency_ms", type = "FLOAT", mode = "REQUIRED", description = "End-to-end response latency in milliseconds" },
    { name = "input_tokens", type = "INTEGER", mode = "NULLABLE", description = "Number of input tokens consumed" },
    { name = "output_tokens", type = "INTEGER", mode = "NULLABLE", description = "Number of output tokens generated" },
    { name = "bq_bytes_billed", type = "INTEGER", mode = "NULLABLE", description = "BigQuery bytes scanned and billed" },
    { name = "retrieved_skus", type = "STRING", mode = "NULLABLE", description = "JSON-serialized list of retrieved product SKUs" },
    { name = "status", type = "STRING", mode = "REQUIRED", description = "Execution status (SUCCESS, DEGRADED, ERROR)" },
    { name = "error_message", type = "STRING", mode = "NULLABLE", description = "Error detail if execution failed" }
  ])

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# BigQuery Table: Nightly Semantic Evaluation Runs
resource "google_bigquery_table" "evaluation_runs" {
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  table_id   = var.evaluation_table_id
  project    = var.project_id

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  clustering = ["status", "trigger_source"]

  schema = jsonencode([
    { name = "eval_run_id", type = "STRING", mode = "REQUIRED", description = "Unique evaluation run identifier" },
    { name = "timestamp", type = "TIMESTAMP", mode = "REQUIRED", description = "Timestamp when evaluation run completed" },
    { name = "total_cases", type = "INTEGER", mode = "REQUIRED", description = "Total benchmark cases evaluated" },
    { name = "passed_cases", type = "INTEGER", mode = "REQUIRED", description = "Total benchmark cases passed" },
    { name = "avg_spec_accuracy", type = "FLOAT", mode = "REQUIRED", description = "Mean spec data accuracy across all cases" },
    { name = "avg_citation_faithfulness", type = "FLOAT", mode = "REQUIRED", description = "Mean citation faithfulness score" },
    { name = "avg_semantic_coherence", type = "FLOAT", mode = "REQUIRED", description = "Mean semantic coherence and lack of contradictions" },
    { name = "avg_latency_ms", type = "FLOAT", mode = "REQUIRED", description = "Average response latency in milliseconds" },
    { name = "p95_latency_ms", type = "FLOAT", mode = "REQUIRED", description = "95th percentile response latency in milliseconds" },
    { name = "target_threshold_met", type = "BOOLEAN", mode = "REQUIRED", description = "Whether overall quality gates passed" },
    { name = "status", type = "STRING", mode = "REQUIRED", description = "Overall run status (PASS or FAIL)" },
    { name = "failure_count", type = "INTEGER", mode = "REQUIRED", description = "Number of failed evaluation test cases" },
    { name = "failure_summary", type = "STRING", mode = "NULLABLE", description = "JSON summary of failed queries and errors" },
    { name = "trigger_source", type = "STRING", mode = "REQUIRED", description = "Invocation trigger source (cloud_scheduler, manual, ci)" },
    { name = "adk_hallucination_score", type = "FLOAT", mode = "NULLABLE", description = "ADK model-graded hallucinations_v1 score" },
    { name = "adk_tool_trajectory_score", type = "FLOAT", mode = "NULLABLE", description = "ADK tool_trajectory_avg_score" }
  ])

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }
}

# -----------------------------------------------------------------------------
# BigQuery BI Reporting Views for Looker Studio Dashboards
# -----------------------------------------------------------------------------

# BI View 1: Most Compared Product Categories
resource "google_bigquery_table" "vw_most_compared_categories" {
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  table_id   = "vw_most_compared_categories"
  project    = var.project_id

  view {
    query          = <<-SQL
      SELECT
        COALESCE(category, 'All Categories / Unspecified') AS category,
        DATE(timestamp) AS comparison_date,
        COUNT(1) AS comparison_count,
        ROUND(AVG(latency_ms), 2) AS avg_latency_ms
      FROM `${var.project_id}.${var.telemetry_dataset_id}.${var.telemetry_table_id}`
      GROUP BY category, comparison_date
      ORDER BY comparison_count DESC
    SQL
    use_legacy_sql = false
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    purpose     = "bi_reporting"
  }
}

# BI View 2: Database Latency vs Total Reasoning Latency Performance Trends
resource "google_bigquery_table" "vw_latency_performance_trends" {
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  table_id   = "vw_latency_performance_trends"
  project    = var.project_id

  view {
    query          = <<-SQL
      SELECT
        DATE(timestamp) AS date_bucket,
        status,
        COUNT(1) AS request_count,
        ROUND(AVG(latency_ms), 2) AS avg_total_latency_ms,
        ROUND(APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)], 2) AS p95_total_latency_ms,
        ROUND(AVG(bq_bytes_billed), 0) AS avg_bq_bytes_billed
      FROM `${var.project_id}.${var.telemetry_dataset_id}.${var.telemetry_table_id}`
      GROUP BY date_bucket, status
      ORDER BY date_bucket DESC
    SQL
    use_legacy_sql = false
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    purpose     = "bi_reporting"
  }
}

# BI View 3: Average Token Consumption, Bytes Scanned & Operational Costs
resource "google_bigquery_table" "vw_token_and_cost_analytics" {
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  table_id   = "vw_token_and_cost_analytics"
  project    = var.project_id

  view {
    query          = <<-SQL
      SELECT
        DATE(timestamp) AS date_bucket,
        COUNT(1) AS total_comparisons,
        SUM(COALESCE(input_tokens, 0)) AS total_input_tokens,
        SUM(COALESCE(output_tokens, 0)) AS total_output_tokens,
        ROUND(AVG(COALESCE(input_tokens, 0)), 1) AS avg_input_tokens,
        ROUND(AVG(COALESCE(output_tokens, 0)), 1) AS avg_output_tokens,
        SUM(COALESCE(bq_bytes_billed, 0)) AS total_bytes_scanned,
        -- Cost estimate: BQ $6.25 per TB scanned + Gemini 2.5 Flash ($0.075/1M input, $0.30/1M output)
        ROUND(
          (SUM(COALESCE(bq_bytes_billed, 0)) / (1024 * 1024 * 1024 * 1024) * 6.25) +
          (SUM(COALESCE(input_tokens, 0)) / 1000000.0 * 0.075) +
          (SUM(COALESCE(output_tokens, 0)) / 1000000.0 * 0.30),
          4
        ) AS estimated_cost_usd
      FROM `${var.project_id}.${var.telemetry_dataset_id}.${var.telemetry_table_id}`
      GROUP BY date_bucket
      ORDER BY date_bucket DESC
    SQL
    use_legacy_sql = false
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    purpose     = "bi_reporting"
  }
}
