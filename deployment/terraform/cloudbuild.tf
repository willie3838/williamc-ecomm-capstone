# Cloud Build Triggers for GitHub CI/CD Automation (PR & Main)

resource "google_cloudbuild_trigger" "pr_trigger" {
  count       = var.enable_cloudbuild_triggers ? 1 : 0
  name        = "pr-quality-gate"
  description = "Pre-merge PR validation gate running unit tests, coverage, benchmark runner, and ADK evaluator"
  project     = var.project_id

  filename = "deployment/cloudbuild-pr.yaml"

  github {
    owner = var.github_repo_owner
    name  = var.github_repo_name
    pull_request {
      branch = "^main$"
    }
  }

  substitutions = {
    _PROJECT_ID = var.project_id
    _REGION     = var.region
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_cloudbuild_trigger" "main_deploy_trigger" {
  count       = var.enable_cloudbuild_triggers ? 1 : 0
  name        = "main-deploy-pipeline"
  description = "Continuous deployment pipeline triggered on push to main with canary release and zero downtime promotion"
  project     = var.project_id

  filename = "deployment/cloudbuild.yaml"

  github {
    owner = var.github_repo_owner
    name  = var.github_repo_name
    push {
      branch = "^main$"
    }
  }

  substitutions = {
    _PROJECT_ID = var.project_id
    _REGION     = var.region
  }

  depends_on = [google_project_service.required_apis]
}
