# Google Cloud Model Armor Security Guardrails Infrastructure

# Enable Google Cloud Model Armor API
resource "google_project_service" "modelarmor_api" {
  project            = var.project_id
  service            = "modelarmor.googleapis.com"
  disable_on_destroy = false
}

# Model Armor Prompt Guardrail Template (Prompt Injection, Jailbreak, RAI & Malicious URI Defense)
# Provisioned in multi-region 'us' (for Vertex AI Groot multi-region dataplane) and regional 'us-central1'
resource "terraform_data" "model_armor_prompt_template" {
  input = {
    project_id      = var.project_id
    location        = "us"
    region          = var.region
    template_id     = "catalog-prompt-guard"
    template_name   = "projects/${var.project_id}/locations/us/templates/catalog-prompt-guard"
    regional_name   = "projects/${var.project_id}/locations/${var.region}/templates/catalog-prompt-guard"
    pi_and_jb_level = "LOW_AND_ABOVE"
    rai_threshold   = "MEDIUM_AND_ABOVE"
  }

  depends_on = [
    google_project_service.modelarmor_api,
  ]
}

# Model Armor Response Guardrail Template (Output RAI & Malicious URI Defense)
# Provisioned in multi-region 'us' (for Vertex AI Groot multi-region dataplane) and regional 'us-central1'
resource "terraform_data" "model_armor_response_template" {
  input = {
    project_id      = var.project_id
    location        = "us"
    region          = var.region
    template_id     = "catalog-resp-guard"
    template_name   = "projects/${var.project_id}/locations/us/templates/catalog-resp-guard"
    regional_name   = "projects/${var.project_id}/locations/${var.region}/templates/catalog-resp-guard"
    pi_and_jb_level = "LOW_AND_ABOVE"
    rai_threshold   = "MEDIUM_AND_ABOVE"
  }

  depends_on = [
    google_project_service.modelarmor_api,
  ]
}
