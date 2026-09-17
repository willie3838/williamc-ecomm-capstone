# Google Cloud Deploy Delivery Pipeline & Target for Cloud Run Canary Releases

# Cloud Deploy Target pointing to the Cloud Run Service
resource "google_clouddeploy_target" "cloudrun_prod" {
  name        = "cloudrun-prod"
  location    = var.region
  project     = var.project_id
  description = "Production Cloud Run deployment target for catalog-comparison-service"

  run {
    location = "projects/${var.project_id}/locations/${var.region}"
  }

  execution_configs {
    usages            = ["RENDER", "DEPLOY", "VERIFY"]
    service_account   = google_service_account.catalog_agent_sa.email
    execution_timeout = "600s"
  }

  depends_on = [
    google_project_service.required_apis,
    google_cloud_run_v2_service.catalog_comparison_service,
  ]
}

# Cloud Deploy Delivery Pipeline with Automated Canary Progression
resource "google_clouddeploy_delivery_pipeline" "catalog_pipeline" {
  name        = "catalog-service-pipeline"
  location    = var.region
  project     = var.project_id
  description = "Continuous Delivery pipeline managing canary 0% verification to 100% traffic cutover"

  serial_pipeline {
    stages {
      target_id = google_clouddeploy_target.cloudrun_prod.target_id
      strategy {
        canary {
          runtime_config {
            cloud_run {
              automatic_traffic_control = true
            }
          }
          canary_deployment {
            percentages = [0, 100]
            verify      = false
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_clouddeploy_target.cloudrun_prod,
  ]
}
