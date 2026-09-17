"""Unit tests for Terraform IaC definitions and IAM least privilege configuration."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
TERRAFORM_DIR = REPO_ROOT / "deployment" / "terraform"

EXPECTED_HCL_FILES = [
    "providers.tf",
    "variables.tf",
    "main.tf",
    "bigquery.tf",
    "cloudrun.tf",
    "iam.tf",
    "vpc_sc.tf",
    "cloudbuild.tf",
    "outputs.tf",
    "eval_job.tf",
]


def _get_terraform_bin() -> str | None:
    """Locate terraform binary in PATH or common user locations."""
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    user_local_bin = str(Path.home() / ".local" / "bin")
    if user_local_bin not in path_dirs:
        os.environ["PATH"] = f"{user_local_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    tf_bin = shutil.which("terraform")
    if not tf_bin and (Path.home() / ".local" / "bin" / "terraform").exists():
        tf_bin = str(Path.home() / ".local" / "bin" / "terraform")
    return tf_bin


def test_terraform_files_exist():
    """Verify all expected Terraform files exist in deployment/terraform/."""
    assert TERRAFORM_DIR.exists(), f"Terraform directory {TERRAFORM_DIR} does not exist"
    for filename in EXPECTED_HCL_FILES:
        filepath = TERRAFORM_DIR / filename
        assert filepath.exists(), f"Missing required Terraform file: {filepath}"

    example_tfvars = TERRAFORM_DIR / "terraform.tfvars.example"
    assert example_tfvars.exists(), f"Missing example tfvars file: {example_tfvars}"


def test_terraform_fmt_check():
    """Verify all Terraform files are formatted correctly with terraform fmt."""
    tf_bin = _get_terraform_bin()
    if not tf_bin:
        pytest.skip("terraform binary not installed in environment")

    result = subprocess.run(
        [tf_bin, "fmt", "-check", "-diff", str(TERRAFORM_DIR)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Terraform formatting diff detected:\n{result.stdout}\n{result.stderr}"
    )


def test_terraform_validate():
    """Verify terraform validate passes cleanly."""
    tf_bin = _get_terraform_bin()
    if not tf_bin:
        pytest.skip("terraform binary not installed in environment")

    # Ensure terraform is initialized
    init_result = subprocess.run(
        [tf_bin, "init", "-backend=false"],
        cwd=TERRAFORM_DIR,
        capture_output=True,
        text=True,
    )
    assert init_result.returncode == 0, (
        f"terraform init failed:\n{init_result.stderr}\n{init_result.stdout}"
    )

    val_result = subprocess.run(
        [tf_bin, "validate"],
        cwd=TERRAFORM_DIR,
        capture_output=True,
        text=True,
    )
    assert val_result.returncode == 0, (
        f"terraform validate failed:\n{val_result.stderr}\n{val_result.stdout}"
    )


def test_variables_definitions():
    """Verify variables.tf declares all required variables with appropriate defaults."""
    var_file = TERRAFORM_DIR / "variables.tf"
    assert var_file.exists()
    content = var_file.read_text()

    required_vars = [
        "project_id",
        "region",
        "environment",
        "service_name",
        "artifact_repo_name",
        "container_image",
        "catalog_dataset_id",
        "telemetry_dataset_id",
    ]
    for var_name in required_vars:
        pattern = rf'variable\s+"{var_name}"\s+{{'
        assert re.search(pattern, content), f"Variable '{var_name}' not defined in variables.tf"

    assert 'default     = "fde-bestbuy-sandbox-dev-508321"' in content
    assert 'default     = "us-central1"' in content


def test_no_hardcoded_project_ids_in_resources():
    """Assert resource HCL files reference var.project_id rather than hardcoded project IDs."""
    resource_files = [
        "main.tf",
        "bigquery.tf",
        "cloudrun.tf",
        "iam.tf",
        "outputs.tf",
        "eval_job.tf",
        "firestore.tf",
        "audit_logs.tf",
    ]
    hardcoded_id = "fde-bestbuy-sandbox-dev-508321"

    for fname in resource_files:
        fpath = TERRAFORM_DIR / fname
        if not fpath.exists():
            continue
        content = fpath.read_text()
        # Look for literal hardcoded project ID outside of comments
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            if hardcoded_id in stripped:
                pytest.fail(
                    f"Hardcoded project ID '{hardcoded_id}' found in {fname}:{line_num}: {line}"
                )


def test_iam_least_privilege_enforcement():
    """Assert service account and least privilege IAM roles are configured."""
    iam_file = TERRAFORM_DIR / "iam.tf"
    assert iam_file.exists(), "iam.tf does not exist"
    content = iam_file.read_text()

    # Must define catalog-agent-sa
    assert 'resource "google_service_account" "catalog_agent_sa"' in content
    assert 'account_id   = "catalog-agent-sa"' in content

    # Disallowed dangerous / overly permissive roles
    prohibited_roles = [
        "roles/owner",
        "roles/editor",
        "roles/viewer",
        "roles/resourcemanager.organizationAdmin",
        "roles/iam.serviceAccountAdmin",
    ]
    for role in prohibited_roles:
        assert role not in content, f"Overly permissive role '{role}' found in iam.tf"

    # Required least-privilege roles
    required_roles = [
        "roles/bigquery.jobUser",
        "roles/bigquery.dataViewer",
        "roles/bigquery.dataEditor",
        "roles/cloudtrace.agent",
        "roles/logging.logWriter",
        "roles/aiplatform.user",
    ]
    for role in required_roles:
        assert role in content, f"Missing required least-privilege role '{role}' in iam.tf"


def test_bigquery_schema_and_partitioning():
    """Verify BigQuery catalog and telemetry tables have required schemas, partitioning, and clustering."""
    bq_file = TERRAFORM_DIR / "bigquery.tf"
    assert bq_file.exists(), "bigquery.tf does not exist"
    content = bq_file.read_text()

    # Datasets
    assert 'resource "google_bigquery_dataset" "catalog"' in content
    assert 'resource "google_bigquery_dataset" "telemetry"' in content

    # Catalog products table
    assert 'resource "google_bigquery_table" "products"' in content
    assert 'type  = "DAY"' in content
    assert 'field = "updated_at"' in content
    assert '"category", "brand", "sku"' in content or '["category", "brand", "sku"]' in content

    # 15 Schema fields in products table
    schema_fields = [
        "sku",
        "name",
        "brand",
        "category",
        "price",
        "shortDescription",
        "longDescription",
        "rating",
        "review_count",
        "specifications",
        "url",
        "image_url",
        "in_stock",
        "created_at",
        "updated_at",
    ]
    for field in schema_fields:
        assert f'name = "{field}"' in content or f'"{field}"' in content, (
            f"Field '{field}' missing from products schema in bigquery.tf"
        )

    # Telemetry table
    assert 'resource "google_bigquery_table" "telemetry_logs"' in content
    telemetry_fields = [
        "query_id",
        "timestamp",
        "query_text",
        "latency_ms",
        "bq_bytes_billed",
        "status",
    ]
    for field in telemetry_fields:
        assert f'name = "{field}"' in content or f'"{field}"' in content, (
            f"Field '{field}' missing from telemetry table schema"
        )

    # Evaluation runs table
    assert 'resource "google_bigquery_table" "evaluation_runs"' in content
    eval_fields = [
        "eval_run_id",
        "timestamp",
        "total_cases",
        "passed_cases",
        "avg_spec_accuracy",
        "avg_citation_faithfulness",
        "status",
        "trigger_source",
        "adk_hallucination_score",
        "adk_tool_trajectory_score",
    ]
    for field in eval_fields:
        assert f'name = "{field}"' in content or f'"{field}"' in content, (
            f"Field '{field}' missing from evaluation_runs table schema"
        )


def test_cloud_run_and_artifact_registry():
    """Verify Cloud Run v2 service and Artifact Registry repository definitions."""
    cr_file = TERRAFORM_DIR / "cloudrun.tf"
    assert cr_file.exists(), "cloudrun.tf does not exist"
    content = cr_file.read_text()

    # Artifact Registry
    assert 'resource "google_artifact_registry_repository" "catalog_repo"' in content
    assert 'format        = "DOCKER"' in content

    # Cloud Run v2 service
    assert 'resource "google_cloud_run_v2_service" "catalog_comparison_service"' in content
    assert re.search(r"service_account\s+=", content), "service_account not found in cloudrun.tf"
    assert "catalog_agent_sa" in content

    # Health probes
    assert "/healthz" in content
    assert "startup_probe" in content or "liveness_probe" in content

    # Environment variables
    assert "GCP_PROJECT_ID" in content
    assert "BIGQUERY_DATASET" in content


def test_main_apis_and_storage():
    """Verify main.tf enables essential APIs and provisions storage buckets."""
    main_file = TERRAFORM_DIR / "main.tf"
    assert main_file.exists(), "main.tf does not exist"
    content = main_file.read_text()

    # Enabled APIs
    required_apis = [
        "run.googleapis.com",
        "artifactregistry.googleapis.com",
        "cloudbuild.googleapis.com",
        "aiplatform.googleapis.com",
        "bigquery.googleapis.com",
        "cloudtrace.googleapis.com",
        "logging.googleapis.com",
        "storage.googleapis.com",
    ]
    for api in required_apis:
        assert api in content, f"API '{api}' not enabled in main.tf"

    # Storage buckets
    assert 'resource "google_storage_bucket" "catalog_data"' in content
    assert 'resource "google_storage_bucket" "terraform_state"' in content


def test_outputs_coverage():
    """Verify outputs.tf exposes all essential resource identifiers and URLs."""
    out_file = TERRAFORM_DIR / "outputs.tf"
    assert out_file.exists(), "outputs.tf does not exist"
    content = out_file.read_text()

    expected_outputs = [
        "cloud_run_service_url",
        "artifact_registry_repo_id",
        "service_account_email",
        "bigquery_catalog_dataset_id",
        "bigquery_catalog_table_id",
        "bigquery_telemetry_dataset_id",
        "catalog_bucket_name",
        "terraform_state_bucket",
        "vpc_sc_perimeter_name",
        "vpc_sc_restricted_services",
        "cloud_run_eval_job_name",
        "cloud_scheduler_eval_job_id",
        "bigquery_evaluation_table_id",
    ]
    for output_name in expected_outputs:
        pattern = rf'output\s+"{output_name}"\s+{{'
        assert re.search(pattern, content), f"Output '{output_name}' not defined in outputs.tf"


def test_cloud_run_eval_job_and_scheduler():
    """Verify Cloud Run v2 Job and Cloud Scheduler for nightly semantic evaluation."""
    eval_file = TERRAFORM_DIR / "eval_job.tf"
    assert eval_file.exists(), "eval_job.tf does not exist"
    content = eval_file.read_text()

    # Cloud Run Job
    assert 'resource "google_cloud_run_v2_job" "catalog_eval_job"' in content
    assert '"evals.run_pipeline"' in content
    assert '"evals/dataset/benchmark_catalog.evalset.json"' in content
    assert '"--export-bq"' in content
    assert '"--fail-on-threshold"' in content

    # Cloud Scheduler
    assert 'resource "google_cloud_scheduler_job" "nightly_eval"' in content
    assert 'schedule         = "0 2 * * *"' in content
    assert 'time_zone        = "Etc/UTC"' in content

    # IAM invoker
    assert 'resource "google_cloud_run_v2_job_iam_member" "scheduler_job_invoker"' in content
    assert 'role     = "roles/run.invoker"' in content

    # API enablement in main.tf
    main_file = TERRAFORM_DIR / "main.tf"
    assert "cloudscheduler.googleapis.com" in main_file.read_text()


def test_vpc_service_controls_configuration():
    """Verify VPC Service Controls perimeter and anti-exfiltration rules are defined."""
    vpc_sc_file = TERRAFORM_DIR / "vpc_sc.tf"
    assert vpc_sc_file.exists(), "vpc_sc.tf does not exist"
    content = vpc_sc_file.read_text()

    # Resources
    assert (
        'resource "google_access_context_manager_service_perimeter" "catalog_perimeter"' in content
    )
    assert (
        'resource "google_access_context_manager_access_level" "catalog_agent_access_level"'
        in content
    )

    # Protected services strictly targeting data exfiltration
    assert '"bigquery.googleapis.com"' in content
    assert '"storage.googleapis.com"' in content

    # Verify public front door and foundation models are kept clean of perimeter friction
    assert '"run.googleapis.com"' not in content
    assert '"aiplatform.googleapis.com"' not in content

    # Dry-run and enforcement blocks
    assert "spec {" in content
    assert 'dynamic "status"' in content
    assert "use_explicit_dry_run_spec = true" in content

    # Verify variables.tf has corresponding controls
    var_file = TERRAFORM_DIR / "variables.tf"
    var_content = var_file.read_text()
    assert 'variable "enable_vpc_sc"' in var_content
    assert 'variable "vpc_sc_dry_run"' in var_content
    assert 'variable "access_policy_id"' in var_content
    assert 'variable "project_number"' in var_content


def test_analytics_and_audit_terraform():
    """Verify Firestore database, IAM roles, Audit logs, and BI views exist in Terraform."""
    firestore_file = TERRAFORM_DIR / "firestore.tf"
    assert firestore_file.exists(), "firestore.tf missing"
    assert 'resource "google_firestore_database" "analytics_db"' in firestore_file.read_text()
    assert 'type        = "FIRESTORE_NATIVE"' in firestore_file.read_text()

    iam_file = TERRAFORM_DIR / "iam.tf"
    iam_content = iam_file.read_text()
    assert "roles/datastore.user" in iam_content

    audit_file = TERRAFORM_DIR / "audit_logs.tf"
    assert audit_file.exists(), "audit_logs.tf missing"
    audit_content = audit_file.read_text()
    assert 'resource "google_project_iam_audit_config" "bigquery_audit"' in audit_content
    assert 'log_type = "DATA_READ"' in audit_content

    bq_file = TERRAFORM_DIR / "bigquery.tf"
    bq_content = bq_file.read_text()
    assert 'resource "google_bigquery_table" "vw_most_compared_categories"' in bq_content
    assert 'resource "google_bigquery_table" "vw_latency_performance_trends"' in bq_content
    assert 'resource "google_bigquery_table" "vw_token_and_cost_analytics"' in bq_content


def test_cloudbuild_triggers_configuration():
    """Verify Cloud Build triggers for GitHub PR and push events are declared in cloudbuild.tf."""
    cb_tf_file = TERRAFORM_DIR / "cloudbuild.tf"
    assert cb_tf_file.exists(), "cloudbuild.tf does not exist"
    content = cb_tf_file.read_text()

    # Resources
    assert 'resource "google_cloudbuild_trigger" "pr_trigger"' in content
    assert 'resource "google_cloudbuild_trigger" "main_deploy_trigger"' in content

    # PR trigger checks
    assert 'filename = "deployment/cloudbuild-pr.yaml"' in content
    assert "pull_request {" in content
    assert 'branch = "^main$"' in content

    # Main deploy trigger checks
    assert 'filename = "deployment/cloudbuild.yaml"' in content
    assert "push {" in content

    # Feature toggle check
    assert "var.enable_cloudbuild_triggers ? 1 : 0" in content

    # Variables check
    var_file = TERRAFORM_DIR / "variables.tf"
    var_content = var_file.read_text()
    assert 'variable "enable_cloudbuild_triggers"' in var_content
    assert 'variable "github_repo_owner"' in var_content
    assert 'variable "github_repo_name"' in var_content
