# Google Cloud Model Armor Security Guardrails Infrastructure

# Enable Google Cloud Model Armor API
resource "google_project_service" "modelarmor_api" {
  project            = var.project_id
  service            = "modelarmor.googleapis.com"
  disable_on_destroy = false
}

locals {
  # Canonical enterprise guardrail payload for Google Cloud Model Armor
  model_armor_template_payload = {
    filterConfig = {
      raiSettings = {
        raiFilters = [
          {
            filterType      = "HATE_SPEECH"
            confidenceLevel = "MEDIUM_AND_ABOVE"
          },
          {
            filterType      = "HARASSMENT"
            confidenceLevel = "MEDIUM_AND_ABOVE"
          },
          {
            filterType      = "SEXUALLY_EXPLICIT"
            confidenceLevel = "MEDIUM_AND_ABOVE"
          },
          {
            filterType      = "DANGEROUS"
            confidenceLevel = "MEDIUM_AND_ABOVE"
          }
        ]
      }
      piAndJailbreakFilterSettings = {
        filterEnforcement = "ENABLED"
        confidenceLevel   = "MEDIUM_AND_ABOVE"
      }
      sdpSettings = {
        basicConfig = {
          filterEnforcement = "ENABLED"
        }
      }
      maliciousUriFilterSettings = {
        filterEnforcement = "ENABLED"
      }
    }
    templateMetadata = {
      logTemplateOperations  = true
      logSanitizeOperations  = true
      dataResidencyCompliant = true
    }
  }
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
    pi_and_jb_level = "MEDIUM_AND_ABOVE"
    rai_threshold   = "MEDIUM_AND_ABOVE"
    payload         = jsonencode(local.model_armor_template_payload)
  }

  triggers_replace = [
    var.project_id,
    var.region,
    jsonencode(local.model_armor_template_payload),
  ]

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      TOKEN=$(gcloud auth print-access-token 2>/dev/null || gcloud auth application-default print-access-token 2>/dev/null || echo "")
      if [ -z "$TOKEN" ]; then
        echo "No active GCP access token detected; skipping live Model Armor prompt template REST provisioning."
        exit 0
      fi
      PAYLOAD='${jsonencode(local.model_armor_template_payload)}'
      for LOC in "us" "${var.region}"; do
        echo "Provisioning Model Armor prompt guard template in location $LOC..."
        HTTP_STATUS=$(curl -s -o /dev/null -w "%%{http_code}" -H "Authorization: Bearer $TOKEN" \
          "https://modelarmor.googleapis.com/v1/projects/${var.project_id}/locations/$LOC/templates/catalog-prompt-guard" || echo "000")
        if [ "$HTTP_STATUS" = "200" ]; then
          curl -s -X PATCH \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD" \
            "https://modelarmor.googleapis.com/v1/projects/${var.project_id}/locations/$LOC/templates/catalog-prompt-guard?updateMask=filterConfig,templateMetadata" || true
        else
          curl -s -X POST \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD" \
            "https://modelarmor.googleapis.com/v1/projects/${var.project_id}/locations/$LOC/templates?templateId=catalog-prompt-guard" || true
        fi
      done
    EOT
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
    pi_and_jb_level = "MEDIUM_AND_ABOVE"
    rai_threshold   = "MEDIUM_AND_ABOVE"
    payload         = jsonencode(local.model_armor_template_payload)
  }

  triggers_replace = [
    var.project_id,
    var.region,
    jsonencode(local.model_armor_template_payload),
  ]

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      TOKEN=$(gcloud auth print-access-token 2>/dev/null || gcloud auth application-default print-access-token 2>/dev/null || echo "")
      if [ -z "$TOKEN" ]; then
        echo "No active GCP access token detected; skipping live Model Armor response template REST provisioning."
        exit 0
      fi
      PAYLOAD='${jsonencode(local.model_armor_template_payload)}'
      for LOC in "us" "${var.region}"; do
        echo "Provisioning Model Armor response guard template in location $LOC..."
        HTTP_STATUS=$(curl -s -o /dev/null -w "%%{http_code}" -H "Authorization: Bearer $TOKEN" \
          "https://modelarmor.googleapis.com/v1/projects/${var.project_id}/locations/$LOC/templates/catalog-resp-guard" || echo "000")
        if [ "$HTTP_STATUS" = "200" ]; then
          curl -s -X PATCH \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD" \
            "https://modelarmor.googleapis.com/v1/projects/${var.project_id}/locations/$LOC/templates/catalog-resp-guard?updateMask=filterConfig,templateMetadata" || true
        else
          curl -s -X POST \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD" \
            "https://modelarmor.googleapis.com/v1/projects/${var.project_id}/locations/$LOC/templates?templateId=catalog-resp-guard" || true
        fi
      done
    EOT
  }

  depends_on = [
    google_project_service.modelarmor_api,
  ]
}
