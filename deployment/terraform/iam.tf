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

# Dedicated CI/CD Pipeline Service Account (Separation of Duties from Runtime SA)
resource "google_service_account" "catalog_cicd_sa" {
  account_id   = "catalog-cicd-sa"
  display_name = "Best Buy Catalog CI/CD Pipeline Service Account"
  project      = var.project_id
  description  = "Dedicated least-privilege CI/CD identity for Cloud Build and Cloud Deploy"
}

# Cloud Deploy Access: Job Runner for executing progressive delivery rollouts
resource "google_project_iam_member" "sa_clouddeploy_runner" {
  project = var.project_id
  role    = "roles/clouddeploy.jobRunner"
  member  = "serviceAccount:${google_service_account.catalog_cicd_sa.email}"
}

# Cloud Deploy Access: Releaser for creating releases from Cloud Build / pipeline
resource "google_project_iam_member" "sa_clouddeploy_releaser" {
  project = var.project_id
  role    = "roles/clouddeploy.releaser"
  member  = "serviceAccount:${google_service_account.catalog_cicd_sa.email}"
}

# Artifact Registry Access: Writer for BYOSA Cloud Build triggers pushing Docker images
resource "google_project_iam_member" "sa_artifactregistry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.catalog_cicd_sa.email}"
}

# Service Account User: Allow CI/CD SA to deploy Cloud Run revisions running as runtime SA
resource "google_service_account_iam_member" "sa_act_as_self" {
  service_account_id = google_service_account.catalog_agent_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.catalog_cicd_sa.email}"
}

# Service Account User: Allow CI/CD SA to submit Cloud Build jobs running as itself
resource "google_service_account_iam_member" "sa_cicd_act_as_itself" {
  service_account_id = google_service_account.catalog_cicd_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.catalog_cicd_sa.email}"
}


# Cloud Build Editor: Required to submit and manage builds via gcloud builds submit
resource "google_project_iam_member" "sa_cloudbuild_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.catalog_cicd_sa.email}"
}

# Storage Admin: Required to stage and upload source archive to gs://${PROJECT_ID}_cloudbuild
resource "google_project_iam_member" "sa_cloudbuild_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.catalog_cicd_sa.email}"
}

# Service Usage Consumer: Required for Cloud Build to bill and run APIs
resource "google_project_iam_member" "sa_serviceusage_consumer" {
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.catalog_cicd_sa.email}"
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
  member  = var.iap_authorized_user
}

# Workload Identity Pool for GitHub Actions CI/CD
resource "google_iam_workload_identity_pool" "github_pool" {
  workload_identity_pool_id = "github-actions-pool"
  project                   = var.project_id
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions OIDC integration"
}

# Workload Identity Pool Provider for GitHub OIDC
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Actions Provider"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
  }

  attribute_condition = "assertion.repository == \"${var.github_repo_owner}/${var.github_repo_name}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow GitHub Actions repository identity to impersonate CI/CD Service Account
resource "google_service_account_iam_member" "github_wif_sa_impersonation" {
  service_account_id = google_service_account.catalog_cicd_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.github_repo_owner}/${var.github_repo_name}"
}



