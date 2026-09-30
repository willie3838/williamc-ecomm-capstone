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

output "model_armor_prompt_template" {
  description = "The Google Cloud Model Armor prompt guardrail template resource name"
  value       = terraform_data.model_armor_prompt_template.output.template_name
}

output "model_armor_response_template" {
  description = "The Google Cloud Model Armor response guardrail template resource name"
  value       = terraform_data.model_armor_response_template.output.template_name
}

output "monitoring_dashboard_id" {
  description = "The Terraform-provisioned Google Cloud Monitoring dashboard resource ID"
  value       = google_monitoring_dashboard.catalog_agent_dashboard.id
}

output "looker_studio_linking_urls" {
  description = "Pre-bound 1-click Looker Studio Linking API URLs for the Unified Executive Dashboard and BI reporting views"
  value = {
    unified_dashboard   = "https://lookerstudio.google.com/reporting/create?c.mode=edit&r.reportName=TechBuy_Unified_Executive_Dashboard&ds.datasourceName=UnifiedExecutiveTelemetry&ds.connector=bigQuery&ds.type=TABLE&ds.projectId=${var.project_id}&ds.datasetId=${var.telemetry_dataset_id}&ds.tableId=${google_bigquery_table.vw_unified_executive_dashboard.table_id}"
    category_engagement = "https://lookerstudio.google.com/reporting/create?c.mode=edit&r.reportName=TechBuy_Category_Engagement&ds.datasourceName=CategoryEngagement&ds.connector=bigQuery&ds.type=TABLE&ds.projectId=${var.project_id}&ds.datasetId=${var.telemetry_dataset_id}&ds.tableId=${google_bigquery_table.vw_most_compared_categories.table_id}"
    latency_trends      = "https://lookerstudio.google.com/reporting/create?c.mode=edit&r.reportName=TechBuy_Latency_SLA_Trends&ds.datasourceName=LatencyTrends&ds.connector=bigQuery&ds.type=TABLE&ds.projectId=${var.project_id}&ds.datasetId=${var.telemetry_dataset_id}&ds.tableId=${google_bigquery_table.vw_latency_performance_trends.table_id}"
    token_cost          = "https://lookerstudio.google.com/reporting/create?c.mode=edit&r.reportName=TechBuy_Token_Cost_Analytics&ds.datasourceName=TokenCostAnalytics&ds.connector=bigQuery&ds.type=TABLE&ds.projectId=${var.project_id}&ds.datasetId=${var.telemetry_dataset_id}&ds.tableId=${google_bigquery_table.vw_token_and_cost_analytics.table_id}"
  }
}


