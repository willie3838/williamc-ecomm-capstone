# Output values exposed after Terraform provisioning

output "cloud_run_service_url" {
  description = "The deployed Cloud Run service URL"
  value       = google_cloud_run_v2_service.catalog_comparison_service.uri
}

output "artifact_registry_repo_id" {
  description = "The full resource ID of the Artifact Registry repository"
  value       = google_artifact_registry_repository.catalog_repo.id
}

output "service_account_email" {
  description = "The email of the dedicated catalog agent runtime service account"
  value       = google_service_account.catalog_agent_sa.email
}

output "bigquery_catalog_dataset_id" {
  description = "The BigQuery dataset ID for the product catalog"
  value       = google_bigquery_dataset.catalog.dataset_id
}

output "bigquery_catalog_table_id" {
  description = "The BigQuery table ID for products"
  value       = google_bigquery_table.products.table_id
}

output "bigquery_telemetry_dataset_id" {
  description = "The BigQuery dataset ID for telemetry and audit logs"
  value       = google_bigquery_dataset.telemetry.dataset_id
}

output "catalog_bucket_name" {
  description = "The Cloud Storage bucket name for catalog seed data and assets"
  value       = google_storage_bucket.catalog_data.name
}

output "terraform_state_bucket" {
  description = "The Cloud Storage bucket name for Terraform remote state"
  value       = google_storage_bucket.terraform_state.name
}
