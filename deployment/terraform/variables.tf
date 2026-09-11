variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID"
  default     = "fde-bestbuy-sandbox-dev-508321"
}

variable "region" {
  type        = string
  description = "The Google Cloud region for services"
  default     = "us-central1"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, staging, prod)"
  default     = "dev"
}
