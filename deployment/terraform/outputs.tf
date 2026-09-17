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

output "vpc_sc_perimeter_name" {
  description = "The resource name of the VPC Service Controls perimeter if enabled"
  value       = length(google_access_context_manager_service_perimeter.catalog_perimeter) > 0 ? google_access_context_manager_service_perimeter.catalog_perimeter[0].name : null
}

output "vpc_sc_restricted_services" {
  description = "The services restricted within the VPC Service Controls perimeter"
  value       = local.vpc_sc_restricted_services
}

output "cloud_run_eval_job_name" {
  description = "The resource name of the nightly semantic evaluation Cloud Run Job"
  value       = google_cloud_run_v2_job.catalog_eval_job.name
}

output "cloud_scheduler_eval_job_id" {
  description = "The resource ID of the Cloud Scheduler job triggering nightly evaluation"
  value       = google_cloud_scheduler_job.nightly_eval.id
}

output "bigquery_evaluation_table_id" {
  description = "The BigQuery table ID for nightly evaluation runs"
  value       = google_bigquery_table.evaluation_runs.table_id
}
