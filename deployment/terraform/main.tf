# Core project services and orchestration resources

# Enable required Google Cloud APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "storage.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# Cloud Storage Bucket: Catalog Ingestion & Asset Data
resource "google_storage_bucket" "catalog_data" {
  name                        = "${var.project_id}-catalog-data"
  project                     = var.project_id
  location                    = var.gcs_bucket_location
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 90
    }
  }

  depends_on = [google_project_service.required_apis]
}

# Cloud Storage Bucket: Terraform Remote State Storage
resource "google_storage_bucket" "terraform_state" {
  name                        = "${var.project_id}-tfstate"
  project                     = var.project_id
  location                    = var.gcs_bucket_location
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 5
    }
  }

  depends_on = [google_project_service.required_apis]
}
