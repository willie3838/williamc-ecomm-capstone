# Serverless Cloud Run and Artifact Registry Infrastructure

# Artifact Registry Repository for Docker images
resource "google_artifact_registry_repository" "catalog_repo" {
  repository_id = var.artifact_repo_name
  project       = var.project_id
  location      = var.region
  format        = "DOCKER"
  description   = "Docker repository for Best Buy Catalog Comparison Agent container images"

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }

  depends_on = [google_project_service.required_apis]
}

# Cloud Run v2 Service
resource "google_cloud_run_v2_service" "catalog_comparison_service" {
  name         = var.service_name
  location     = var.region
  project      = var.project_id
  ingress      = "INGRESS_TRAFFIC_ALL"
  launch_stage = "BETA"

  # Native Identity-Aware Proxy (IAP) is enforced on Cloud Run via deployment/clouddeploy/service.yaml
  # and gcloud run services update --iap (run.googleapis.com/iap-enabled)


  template {
    service_account                  = google_service_account.catalog_agent_sa.email
    max_instance_request_concurrency = var.container_concurrency

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = var.container_cpu
          memory = var.container_memory
        }
      }

      ports {
        container_port = 8080
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }

      env {
        name  = "BIGQUERY_DATASET"
        value = var.catalog_dataset_id
      }

      env {
        name  = "BQ_DATASET"
        value = var.catalog_dataset_id
      }

      env {
        name  = "BIGQUERY_CATALOG_TABLE"
        value = var.catalog_table_id
      }

      env {
        name  = "BQ_TABLE"
        value = var.catalog_table_id
      }

      env {
        name  = "BIGQUERY_TELEMETRY_DATASET"
        value = var.telemetry_dataset_id
      }

      env {
        name  = "SERVICE_REGION"
        value = var.region
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "GOOGLE_CLOUD_AGENT_ENGINE_ID"
        value = "2445220951441276928"
      }

      env {
        name  = "AGENT_RUNTIME_RESOURCE_NAME"
        value = "projects/${var.project_number}/locations/${var.region}/reasoningEngines/2445220951441276928"
      }

      env {
        name  = "ENABLE_MODEL_ARMOR"
        value = "true"
      }

      env {
        name  = "MODEL_ARMOR_PROMPT_TEMPLATE"
        value = "projects/${var.project_id}/locations/us/templates/catalog-prompt-guard"
      }

      env {
        name  = "MODEL_ARMOR_RESPONSE_TEMPLATE"
        value = "projects/${var.project_id}/locations/us/templates/catalog-resp-guard"
      }

      startup_probe {
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3

        http_get {
          path = "/healthz"
          port = 8080
        }
      }

      liveness_probe {
        timeout_seconds   = 3
        period_seconds    = 15
        failure_threshold = 3

        http_get {
          path = "/healthz"
          port = 8080
        }
      }
    }
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
  }

  lifecycle {
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
      traffic,
    ]
  }

  depends_on = [
    google_project_service.required_apis,
    google_service_account.catalog_agent_sa,
    google_artifact_registry_repository.catalog_repo,
  ]
}

# Cloud Run Public Invoker IAM Member (Controlled by var.allow_unauthenticated)
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.catalog_comparison_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
