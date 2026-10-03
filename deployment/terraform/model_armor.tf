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
  prompt_guard_template_id   = "catalog-prompt-guard"
  response_guard_template_id = "catalog-resp-guard"
  prompt_guard_body          = jsonencode(local.model_armor_template_payload)
  response_guard_body        = jsonencode(local.model_armor_template_payload)
}

# Model Armor Prompt Guardrail Template (Prompt Injection, Jailbreak, RAI & Malicious URI Defense)
# Provisioned via the Regional Endpoint in var.region (us-central1)
resource "terraform_data" "model_armor_prompt_template" {
  input = {
    project_id      = var.project_id
    region          = var.region
    template_id     = local.prompt_guard_template_id
    template_name   = "projects/${var.project_id}/locations/${var.region}/templates/${local.prompt_guard_template_id}"
    pi_and_jb_level = "MEDIUM_AND_ABOVE"
    rai_threshold   = "MEDIUM_AND_ABOVE"
    payload         = local.prompt_guard_body
  }

  triggers_replace = [
    var.project_id,
    var.region,
    local.prompt_guard_template_id,
    sha256(local.prompt_guard_body),
  ]

  provisioner "local-exec" {
    command = <<-EOT
      set -euo pipefail
      TOKEN=$(gcloud auth print-access-token 2>/dev/null || gcloud auth application-default print-access-token 2>/dev/null || echo "")
      if [ -z "$TOKEN" ]; then
        echo "No active GCP access token detected; skipping live Model Armor prompt template REST provisioning."
        exit 0
      fi
      BASE_URL="https://modelarmor.${var.region}.rep.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/templates"
      STATUS=$(curl -s -o /dev/null -w "%%{http_code}" -H "Authorization: Bearer $${TOKEN}" "$${BASE_URL}/${local.prompt_guard_template_id}")
      if [ "$${STATUS}" = "200" ]; then
        RESP=$(curl -s -w "\n%%{http_code}" -X PATCH \
          -H "Authorization: Bearer $${TOKEN}" \
          -H "Content-Type: application/json" \
          -d '${local.prompt_guard_body}' \
          "$${BASE_URL}/${local.prompt_guard_template_id}?updateMask=filterConfig,templateMetadata")
      else
        RESP=$(curl -s -w "\n%%{http_code}" -X POST \
          -H "Authorization: Bearer $${TOKEN}" \
          -H "Content-Type: application/json" \
          -d '${local.prompt_guard_body}' \
          "$${BASE_URL}?templateId=${local.prompt_guard_template_id}")
      fi
      HTTP_CODE=$(echo "$${RESP}" | tail -n1)
      BODY=$(echo "$${RESP}" | sed '$d')
      echo "Model Armor prompt template (${local.prompt_guard_template_id}) HTTP $${HTTP_CODE}"
      if [ "$${HTTP_CODE}" -lt 200 ] || [ "$${HTTP_CODE}" -ge 300 ]; then
        echo "ERROR provisioning Model Armor prompt template: $${BODY}" >&2
        exit 1
      fi
    EOT
  }

  depends_on = [
    google_project_service.modelarmor_api,
  ]
}

# Model Armor Response Guardrail Template (Output RAI & Malicious URI Defense)
# Provisioned via the Regional Endpoint in var.region (us-central1)
resource "terraform_data" "model_armor_response_template" {
  input = {
    project_id      = var.project_id
    region          = var.region
    template_id     = local.response_guard_template_id
    template_name   = "projects/${var.project_id}/locations/${var.region}/templates/${local.response_guard_template_id}"
    pi_and_jb_level = "MEDIUM_AND_ABOVE"
    rai_threshold   = "MEDIUM_AND_ABOVE"
    payload         = local.response_guard_body
  }

  triggers_replace = [
    var.project_id,
    var.region,
    local.response_guard_template_id,
    sha256(local.response_guard_body),
  ]

  provisioner "local-exec" {
    command = <<-EOT
      set -euo pipefail
      TOKEN=$(gcloud auth print-access-token 2>/dev/null || gcloud auth application-default print-access-token 2>/dev/null || echo "")
      if [ -z "$TOKEN" ]; then
        echo "No active GCP access token detected; skipping live Model Armor response template REST provisioning."
        exit 0
      fi
      BASE_URL="https://modelarmor.${var.region}.rep.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/templates"
      STATUS=$(curl -s -o /dev/null -w "%%{http_code}" -H "Authorization: Bearer $${TOKEN}" "$${BASE_URL}/${local.response_guard_template_id}")
      if [ "$${STATUS}" = "200" ]; then
        RESP=$(curl -s -w "\n%%{http_code}" -X PATCH \
          -H "Authorization: Bearer $${TOKEN}" \
          -H "Content-Type: application/json" \
          -d '${local.response_guard_body}' \
          "$${BASE_URL}/${local.response_guard_template_id}?updateMask=filterConfig,templateMetadata")
      else
        RESP=$(curl -s -w "\n%%{http_code}" -X POST \
          -H "Authorization: Bearer $${TOKEN}" \
          -H "Content-Type: application/json" \
          -d '${local.response_guard_body}' \
          "$${BASE_URL}?templateId=${local.response_guard_template_id}")
      fi
      HTTP_CODE=$(echo "$${RESP}" | tail -n1)
      BODY=$(echo "$${RESP}" | sed '$d')
      echo "Model Armor response template (${local.response_guard_template_id}) HTTP $${HTTP_CODE}"
      if [ "$${HTTP_CODE}" -lt 200 ] || [ "$${HTTP_CODE}" -ge 300 ]; then
        echo "ERROR provisioning Model Armor response template: $${BODY}" >&2
        exit 1
      fi
    EOT
  }

  depends_on = [
    google_project_service.modelarmor_api,
  ]
}

