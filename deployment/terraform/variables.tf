variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID"
  default     = "fde-bestbuy-sandbox-dev-508321"
}

variable "region" {
  type        = string
  description = "The Google Cloud region for compute and regional resources"
  default     = "us-central1"
}

variable "environment" {
  type        = string
  description = "Deployment environment name (dev, staging, prod)"
  default     = "dev"
}

variable "service_name" {
  type        = string
  description = "Name of the Cloud Run comparison service"
  default     = "catalog-comparison-service"
}

variable "artifact_repo_name" {
  type        = string
  description = "Name of the Artifact Registry repository"
  default     = "catalog-agent-repo"
}

variable "container_image" {
  type        = string
  description = "Container image URL deployed to Cloud Run"
  default     = "us-central1-docker.pkg.dev/fde-bestbuy-sandbox-dev-508321/catalog-agent-repo/backend:latest"
}

variable "container_concurrency" {
  type        = number
  description = "Maximum concurrent requests per Cloud Run container instance"
  default     = 80
}

variable "container_cpu" {
  type        = string
  description = "CPU allocated per Cloud Run instance"
  default     = "1000m"
}

variable "container_memory" {
  type        = string
  description = "Memory allocated per Cloud Run instance"
  default     = "512Mi"
}

variable "min_instances" {
  type        = number
  description = "Minimum number of Cloud Run instances (0 for serverless scale-to-zero)"
  default     = 0
}

variable "max_instances" {
  type        = number
  description = "Maximum number of Cloud Run instances for autoscaling"
  default     = 10
}

variable "catalog_dataset_id" {
  type        = string
  description = "BigQuery dataset ID for product catalog"
  default     = "catalog"
}

variable "catalog_table_id" {
  type        = string
  description = "BigQuery table ID for products"
  default     = "products"
}

variable "telemetry_dataset_id" {
  type        = string
  description = "BigQuery dataset ID for telemetry and audit logs"
  default     = "catalog_agent_telemetry"
}

variable "telemetry_table_id" {
  type        = string
  description = "BigQuery table ID for query telemetry logs"
  default     = "query_telemetry"
}

variable "evaluation_table_id" {
  type        = string
  description = "BigQuery table ID for nightly semantic evaluation run results"
  default     = "evaluation_runs"
}

variable "gcs_bucket_location" {
  type        = string
  description = "Location for Cloud Storage buckets (single-region data residency)"
  default     = "us-central1"
}

variable "allow_unauthenticated" {
  type        = bool
  description = "Whether to allow public unauthenticated ingress to Cloud Run service"
  default     = true
}

variable "project_number" {
  type        = string
  description = "The Google Cloud numeric Project Number"
  default     = "499572810092"
}

variable "enable_vpc_sc" {
  type        = bool
  description = "Whether to provision VPC Service Controls perimeter"
  default     = false
}

variable "access_policy_id" {
  type        = string
  description = "The Access Context Manager policy ID"
  default     = ""
}

variable "vpc_sc_dry_run" {
  type        = bool
  description = "Whether the VPC-SC perimeter is in dry-run mode"
  default     = true
}

variable "authorized_ip_subnetworks" {
  type        = list(string)
  description = "List of CIDRs allowed into the perimeter"
  default     = []
}

variable "enable_cloudbuild_triggers" {
  type        = bool
  description = "Whether to create Cloud Build triggers for GitHub PR and push events"
  default     = true
}

variable "github_repo_owner" {
  type        = string
  description = "Owner/organization of the GitHub repository"
  default     = "willie3838"
}

variable "github_repo_name" {
  type        = string
  description = "Name of the GitHub repository"
  default     = "williamc-ecomm-capstone"
}

variable "github_pat" {
  type        = string
  description = "GitHub OAuth / Personal Access Token for Cloud Build v2 connection"
  default     = ""
  sensitive   = true
}

variable "github_app_installation_id" {
  type        = number
  description = "Numeric GitHub App Installation ID for Google Cloud Build"
  default     = 0
}

variable "iap_authorized_user" {
  type        = string
  description = "IAM principal member granted IAP HTTPS resource access"
  default     = "user:admin@williamwlchan.altostrat.com"
}


