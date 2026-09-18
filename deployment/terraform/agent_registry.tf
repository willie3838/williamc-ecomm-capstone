# Google Cloud Agent Registry & Vertex AI Prompt Management Infrastructure

# Enable Google Cloud Agent Registry API
resource "google_project_service" "agentregistry_api" {
  project            = var.project_id
  service            = "agentregistry.googleapis.com"
  disable_on_destroy = false
}

# Grant Discovery Engine / Agent Registry invocation access on Cloud Run
resource "google_cloud_run_v2_service_iam_member" "agent_registry_discovery_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.catalog_comparison_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.catalog_agent_sa.email}"
}

# Register Cloud Run A2A Service in Google Cloud Agent Registry
resource "terraform_data" "gcp_agent_registry_registration" {
  input = {
    project_id       = var.project_id
    location         = var.region
    service_id       = var.service_name
    endpoint_url     = "${google_cloud_run_v2_service.catalog_comparison_service.uri}/api/compare"
    agent_card_url   = "${google_cloud_run_v2_service.catalog_comparison_service.uri}/.well-known/agent-card.json"
    protocol_binding = "http-json"
  }

  depends_on = [
    google_project_service.agentregistry_api,
    google_cloud_run_v2_service.catalog_comparison_service,
  ]
}
