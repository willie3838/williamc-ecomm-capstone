# Identity and Access Management (IAM) - Principle of Least Privilege

# Runtime Service Account for Catalog Agent
resource "google_service_account" "catalog_agent_sa" {
  account_id   = "catalog-agent-sa"
  display_name = "Best Buy Catalog Comparison Agent Service Account"
  project      = var.project_id
  description  = "Dedicated runtime identity for catalog comparison agent Cloud Run service"
}

# IAM Role: BigQuery Job User (Required to run query jobs in the project)
resource "google_project_iam_member" "sa_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# IAM Role: Cloud Trace Agent (Required to emit distributed OpenTelemetry traces)
resource "google_project_iam_member" "sa_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# IAM Role: Logging Log Writer (Required to emit structured application logs)
resource "google_project_iam_member" "sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# IAM Role: Vertex AI User (Required to invoke Gemini models)
resource "google_project_iam_member" "sa_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# BigQuery Dataset Access: Data Viewer on catalog (Read-only access to products)
resource "google_bigquery_dataset_iam_member" "sa_catalog_viewer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.catalog.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# BigQuery Dataset Access: Data Editor on telemetry (Write access for logs/metrics)
resource "google_bigquery_dataset_iam_member" "sa_telemetry_editor" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# Storage Bucket Access: Object Viewer on catalog ingestion bucket
resource "google_storage_bucket_iam_member" "sa_catalog_data_viewer" {
  bucket = google_storage_bucket.catalog_data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# Cloud Firestore Access: Datastore User for User Actions, Sessions, and Feedback
resource "google_project_iam_member" "sa_datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# Cloud Deploy Access: Job Runner for executing progressive delivery rollouts
resource "google_project_iam_member" "sa_clouddeploy_runner" {
  project = var.project_id
  role    = "roles/clouddeploy.jobRunner"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# Cloud Deploy Access: Releaser for creating releases from Cloud Build / pipeline
resource "google_project_iam_member" "sa_clouddeploy_releaser" {
  project = var.project_id
  role    = "roles/clouddeploy.releaser"
  member  = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# IAP Service Identity (Required for Cloud Run native IAP request dispatching)
resource "google_project_service_identity" "iap_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "iap.googleapis.com"
}

# Grant IAP Service Agent permission to invoke Cloud Run
resource "google_cloud_run_v2_service_iam_member" "iap_service_agent_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.catalog_comparison_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_project_service_identity.iap_sa.email}"
}

# Grant user browser access to IAP protected web resources
resource "google_iap_web_iam_member" "user_access" {
  project = var.project_id
  role    = "roles/iap.httpsResourceAccessor"
  member  = "user:admin@williamwlchan.altostrat.com"
}


