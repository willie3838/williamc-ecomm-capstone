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
