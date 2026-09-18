# Cloud Build v2 GitHub Connection, Repository & Triggers (100% Terraform Managed)

# 1. Secret Manager Secret for GitHub OAuth / PAT Token
resource "google_secret_manager_secret" "github_token" {
  count     = var.enable_cloudbuild_triggers ? 1 : 0
  project   = var.project_id
  secret_id = "cloudbuild-github-token"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "github_token_version" {
  count       = var.enable_cloudbuild_triggers && var.github_pat != "" ? 1 : 0
  secret      = google_secret_manager_secret.github_token[0].id
  secret_data = var.github_pat
}

# 2. Grant Cloud Build P4SA access to Secret Manager
resource "google_project_service_identity" "cloudbuild_p4sa" {
  provider = google-beta
  project  = var.project_id
  service  = "cloudbuild.googleapis.com"
}

resource "google_project_iam_member" "cloudbuild_p4sa_secret_admin" {
  count   = var.enable_cloudbuild_triggers ? 1 : 0
  project = var.project_id
  role    = "roles/secretmanager.admin"
  member  = "serviceAccount:service-${var.project_number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}

resource "google_secret_manager_secret_iam_member" "cloudbuild_secret_accessor" {
  count     = var.enable_cloudbuild_triggers ? 1 : 0
  project   = var.project_id
  secret_id = google_secret_manager_secret.github_token[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:service-${var.project_number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}

# 3. Cloud Build v2 GitHub Connection
resource "google_cloudbuildv2_connection" "github_connection" {
  count    = var.enable_cloudbuild_triggers ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = "github-connection"

  github_config {
    app_installation_id = var.github_app_installation_id != 0 ? var.github_app_installation_id : null
    authorizer_credential {
      oauth_token_secret_version = var.github_pat != "" ? google_secret_manager_secret_version.github_token_version[0].id : null
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_project_iam_member.cloudbuild_p4sa_secret_admin,
    google_secret_manager_secret_iam_member.cloudbuild_secret_accessor
  ]
}

# 4. Cloud Build v2 Repository Link (willie3838/williamc-ecomm-capstone)
resource "google_cloudbuildv2_repository" "ecomm_repo" {
  count             = var.enable_cloudbuild_triggers && var.github_app_installation_id != 0 ? 1 : 0
  project           = var.project_id
  location          = var.region
  name              = var.github_repo_name
  parent_connection = google_cloudbuildv2_connection.github_connection[0].id
  remote_uri        = "https://github.com/${var.github_repo_owner}/${var.github_repo_name}.git"
}

# 5. Pre-merge Pull Request Quality Gate Trigger (cloudbuild-pr.yaml)
resource "google_cloudbuild_trigger" "pr_trigger" {
  count           = var.enable_cloudbuild_triggers && var.github_app_installation_id != 0 ? 1 : 0
  name            = "pr-quality-gate"
  description     = "Pre-merge PR validation gate running unit tests, coverage, benchmark runner, and ADK evaluator"
  project         = var.project_id
  location        = var.region
  service_account = google_service_account.catalog_agent_sa.id
  filename        = "deployment/cloudbuild-pr.yaml"

  repository_event_config {
    repository = google_cloudbuildv2_repository.ecomm_repo[0].id
    pull_request {
      branch = "^main$"
    }
  }

  substitutions = {
    _PROJECT_ID = var.project_id
    _REGION     = var.region
  }

  depends_on = [
    google_project_service.required_apis,
    google_service_account.catalog_agent_sa
  ]
}

# 6. Continuous Deployment Pipeline Trigger on Push to Main (cloudbuild.yaml)
resource "google_cloudbuild_trigger" "main_deploy_trigger" {
  count           = var.enable_cloudbuild_triggers && var.github_app_installation_id != 0 ? 1 : 0
  name            = "main-deploy-pipeline"
  description     = "Continuous deployment pipeline triggered on push to main with canary release and zero downtime promotion"
  project         = var.project_id
  location        = var.region
  service_account = google_service_account.catalog_agent_sa.id
  filename        = "deployment/cloudbuild.yaml"

  repository_event_config {
    repository = google_cloudbuildv2_repository.ecomm_repo[0].id
    push {
      branch = "^main$"
    }
  }

  substitutions = {
    _PROJECT_ID = var.project_id
    _REGION     = var.region
  }

  depends_on = [
    google_project_service.required_apis,
    google_service_account.catalog_agent_sa
  ]
}

# 7. Dedicated Infrastructure Pipeline Trigger on Push to Main (Runs Terraform Apply ONLY when deployment/terraform/** changes)
resource "google_cloudbuild_trigger" "infra_deploy_trigger" {
  count           = var.enable_cloudbuild_triggers && var.github_app_installation_id != 0 ? 1 : 0
  name            = "infra-deploy-pipeline"
  description     = "GitOps infrastructure pipeline triggered on push to main when deployment/terraform/** changes"
  project         = var.project_id
  location        = var.region
  service_account = google_service_account.catalog_agent_sa.id
  filename        = "deployment/cloudbuild-tf.yaml"

  included_files = ["deployment/terraform/**"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.ecomm_repo[0].id
    push {
      branch = "^main$"
    }
  }

  substitutions = {
    _PROJECT_ID = var.project_id
    _REGION     = var.region
  }

  depends_on = [
    google_project_service.required_apis,
    google_service_account.catalog_agent_sa
  ]
}

output "cloudbuild_github_connection_state" {
  description = "Installation state and action URI of the Cloud Build v2 GitHub connection"
  value       = var.enable_cloudbuild_triggers ? google_cloudbuildv2_connection.github_connection[0].installation_state : null
}
