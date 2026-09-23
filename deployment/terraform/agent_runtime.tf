# Vertex AI Agent Runtime (Reasoning Engine) Infrastructure
# Manages the ADK comparison multi-agent runtime configuration (reasoningEngines)

resource "terraform_data" "catalog_agent_engine" {
  input = {
    display_name    = "techbuy-catalog-comparison-agent"
    description     = "TechBuy Retailers Catalog Comparison Multi-Agent (Google ADK on Agent Runtime)"
    project         = var.project_id
    region          = var.region
    agent_framework = "google-adk"
    image_uri       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo_name}/backend:latest"
    class_methods   = jsonencode(["query", "stream_query"])
  }

  depends_on = [
    google_project_service.required_apis,
    google_service_account.catalog_agent_sa,
    google_artifact_registry_repository.catalog_repo,
  ]
}

output "agent_runtime_id" {
  description = "The resource ID of the Vertex AI Agent Runtime reasoning engine"
  value       = terraform_data.catalog_agent_engine.id
}

output "agent_runtime_name" {
  description = "The display name of the Vertex AI Agent Runtime reasoning engine"
  value       = terraform_data.catalog_agent_engine.output.display_name
}
