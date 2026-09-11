# Service Account for Catalog Agent
resource "google_service_account" "catalog_agent_sa" {
  account_id   = "catalog-agent-sa"
  display_name = "Best Buy Catalog Comparison Agent Service Account"
  project      = var.project_id
}

# BigQuery Dataset: catalog
resource "google_bigquery_dataset" "catalog" {
  dataset_id  = "catalog"
  project     = var.project_id
  location    = var.region
  description = "E-commerce product catalog for comparison agent"
}

# BigQuery Table: products
resource "google_bigquery_table" "products" {
  dataset_id = google_bigquery_dataset.catalog.dataset_id
  table_id   = "products"
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
    { name = "rating", type = "FLOAT", mode = "NULLABLE", description = "Customer review rating" },
    { name = "review_count", type = "INTEGER", mode = "NULLABLE", description = "Number of customer reviews" },
    { name = "specifications", type = "JSON", mode = "REQUIRED", description = "Key-value technical specs" },
    { name = "url", type = "STRING", mode = "NULLABLE", description = "Product listing URL" },
    { name = "image_url", type = "STRING", mode = "NULLABLE", description = "Product image URL" },
    { name = "in_stock", type = "BOOLEAN", mode = "REQUIRED", description = "Stock availability" },
    { name = "created_at", type = "TIMESTAMP", mode = "NULLABLE", description = "Record creation timestamp" },
    { name = "updated_at", type = "TIMESTAMP", mode = "REQUIRED", description = "Record update timestamp" }
  ])
}

# BigQuery Dataset: Telemetry
resource "google_bigquery_dataset" "telemetry" {
  dataset_id  = "catalog_agent_telemetry"
  project     = var.project_id
  location    = var.region
  description = "Operational telemetry and evaluation logs"
}

# IAM Role: BigQuery Job User
resource "google_project_iam_member" "sa_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# IAM Role: Cloud Trace Agent
resource "google_project_iam_member" "sa_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# IAM Role: Logging Log Writer
resource "google_project_iam_member" "sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# BigQuery Dataset Access: Data Viewer on catalog
resource "google_bigquery_dataset_iam_member" "sa_catalog_viewer" {
  dataset_id = google_bigquery_dataset.catalog.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# BigQuery Dataset Access: Data Editor on telemetry
resource "google_bigquery_dataset_iam_member" "sa_telemetry_editor" {
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}
