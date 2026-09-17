# Nightly Semantic Quality Evaluation Cloud Run Job and Cloud Scheduler Trigger

# Cloud Run v2 Job: Executes 80-pair benchmark against live catalog and Gemini
resource "google_cloud_run_v2_job" "catalog_eval_job" {
  name     = "${var.service_name}-nightly-eval"
  location = var.region
  project  = var.project_id

  template {
    task_count = 1

    template {
      max_retries     = 1
      timeout         = "1200s"
      service_account = google_service_account.catalog_agent_sa.email

      containers {
        image = var.container_image

        args = [
          "python",
          "-m",
          "evals.run_pipeline",
          "--live",
          "--dataset",
          "evals/dataset/benchmark_catalog.evalset.json",
          "--export-bq",
          "--fail-on-threshold",
          "--trigger-source",
          "cloud_scheduler"
        ]

        resources {
          limits = {
            cpu    = "1000m"
            memory = "2Gi"
          }
        }

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "BIGQUERY_DATASET"
          value = var.catalog_dataset_id
        }

        env {
          name  = "BIGQUERY_CATALOG_TABLE"
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
          name  = "GOOGLE_API_USE_CLIENT_CERTIFICATE"
          value = "false"
        }
      }
    }
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    purpose     = "evaluation"
  }

  depends_on = [
    google_project_service.required_apis,
    google_bigquery_table.evaluation_runs
  ]
}

# IAM Role: Allow Service Account to invoke the evaluation job
resource "google_cloud_run_v2_job_iam_member" "scheduler_job_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.catalog_eval_job.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# Cloud Scheduler: Triggers evaluation job nightly at 02:00 UTC
resource "google_cloud_scheduler_job" "nightly_eval" {
  name             = "${var.service_name}-nightly-eval-scheduler"
  project          = var.project_id
  region           = var.region
  description      = "Nightly trigger for Best Buy comparison agent semantic quality evaluation"
  schedule         = "0 2 * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "1200s"

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.catalog_eval_job.name}:run"

    oauth_token {
      service_account_email = google_service_account.catalog_agent_sa.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_cloud_run_v2_job.catalog_eval_job,
    google_cloud_run_v2_job_iam_member.scheduler_job_invoker
  ]
}
