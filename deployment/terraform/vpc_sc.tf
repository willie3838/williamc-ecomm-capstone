# VPC Service Controls (VPC-SC) - Catalog & Telemetry Data Exfiltration Prevention

locals {
  # Strictly target data storage services to prevent BigQuery catalog & telemetry exfiltration
  vpc_sc_restricted_services = [
    "bigquery.googleapis.com",
    "storage.googleapis.com",
  ]
}

# Access Level allowing Catalog Agent runtime identity and authorized CIDRs
resource "google_access_context_manager_access_level" "catalog_agent_access_level" {
  count  = var.enable_vpc_sc && var.access_policy_id != "" ? 1 : 0
  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/accessLevels/${replace(var.service_name, "-", "_")}_access_level"
  title  = "${var.service_name}-access-level"

  basic {
    conditions {
      members = [
        "serviceAccount:${google_service_account.catalog_agent_sa.email}"
      ]
      ip_subnetworks = var.authorized_ip_subnetworks
    }
  }
}

# Service Perimeter enclosing BigQuery and Storage
resource "google_access_context_manager_service_perimeter" "catalog_perimeter" {
  count  = var.enable_vpc_sc && var.access_policy_id != "" ? 1 : 0
  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/${replace(var.service_name, "-", "_")}_perimeter"
  title  = "${var.service_name}-perimeter"

  # Dry-run spec mode for safe auditing before hard enforcement
  spec {
    resources           = ["projects/${var.project_number}"]
    restricted_services = local.vpc_sc_restricted_services
    access_levels = [
      google_access_context_manager_access_level.catalog_agent_access_level[0].name
    ]
  }

  # Hard enforcement status block (enabled when vpc_sc_dry_run is false)
  dynamic "status" {
    for_each = var.vpc_sc_dry_run ? [] : [1]
    content {
      resources           = ["projects/${var.project_number}"]
      restricted_services = local.vpc_sc_restricted_services
      access_levels = [
        google_access_context_manager_access_level.catalog_agent_access_level[0].name
      ]
    }
  }

  use_explicit_dry_run_spec = true

  depends_on = [
    google_service_account.catalog_agent_sa,
    google_bigquery_dataset.catalog,
    google_storage_bucket.catalog_data,
  ]
}
