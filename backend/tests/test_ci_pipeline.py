"""Unit and validation tests for Cloud Build CI/CD pipeline and deployment assets.

Ensures compliance with Rubric 6.1 (CI/CD & Deployment), Rubric 6.2 (IaC & Parity),
and SPEC.md requirements:
- Ruff linting and formatting gates.
- Pytest coverage gate (>=80%).
- Multi-stage container build with Artifact Registry tagging.
- Safe canary / blue-green deployment strategy (--no-traffic, --tag candidate).
- Post-deployment smoke probes on /health and /health/ready.
- Automated traffic promotion and rollback protection.
- Container security hardening (non-root execution, healthchecks).
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

# Repository root relative to this test file
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOYMENT_DIR = REPO_ROOT / "deployment"
CLOUDBUILD_FILE = DEPLOYMENT_DIR / "cloudbuild.yaml"
ROLLBACK_BUILD_FILE = DEPLOYMENT_DIR / "cloudbuild-rollback.yaml"
DOCKERFILE = DEPLOYMENT_DIR / "Dockerfile"
ROLLBACK_SCRIPT = DEPLOYMENT_DIR / "rollback.sh"
VALIDATOR_SCRIPT = DEPLOYMENT_DIR / "validate_pipeline.py"


@pytest.fixture(scope="module")
def cloudbuild_config() -> dict:
    """Loads and parses deployment/cloudbuild.yaml."""
    assert CLOUDBUILD_FILE.exists(), f"Missing {CLOUDBUILD_FILE}"
    with open(CLOUDBUILD_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "cloudbuild.yaml must be a valid YAML mapping"
    return data


@pytest.fixture(scope="module")
def rollback_build_config() -> dict:
    """Loads and parses deployment/cloudbuild-rollback.yaml."""
    assert ROLLBACK_BUILD_FILE.exists(), f"Missing {ROLLBACK_BUILD_FILE}"
    with open(ROLLBACK_BUILD_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "cloudbuild-rollback.yaml must be a valid YAML mapping"
    return data


@pytest.fixture(scope="module")
def dockerfile_content() -> str:
    """Reads deployment/Dockerfile content."""
    assert DOCKERFILE.exists(), f"Missing {DOCKERFILE}"
    return DOCKERFILE.read_text(encoding="utf-8")


# ==============================================================================
# 1. Cloud Build Pipeline Schema & Step Structure Tests
# ==============================================================================


def test_cloudbuild_basic_structure(cloudbuild_config: dict):
    """Asserts required top-level keys exist in cloudbuild.yaml."""
    assert "steps" in cloudbuild_config, "cloudbuild.yaml must declare 'steps'"
    assert "substitutions" in cloudbuild_config, "cloudbuild.yaml must declare 'substitutions'"
    assert "images" in cloudbuild_config, "cloudbuild.yaml must declare 'images'"
    assert "options" in cloudbuild_config, "cloudbuild.yaml must declare 'options'"
    assert len(cloudbuild_config["steps"]) >= 5, "Pipeline must contain at least 5 distinct steps"


def test_cloudbuild_substitutions(cloudbuild_config: dict):
    """Verifies default substitutions conform to FDE Capstone environment."""
    subs = cloudbuild_config.get("substitutions", {})
    assert subs.get("_REGION") == "us-central1", "Default _REGION must be us-central1"
    assert subs.get("_PROJECT_ID") == "fde-bestbuy-sandbox-dev-508321", (
        "Default _PROJECT_ID must match project fde-bestbuy-sandbox-dev-508321"
    )


def test_cloudbuild_step_sequence_and_ids(cloudbuild_config: dict):
    """Verifies logical step sequencing from lint to test, build, deploy, and promote."""
    steps = cloudbuild_config["steps"]
    step_ids = [s.get("id") for s in steps]

    expected_order = [
        "lint",
        "unit-tests",
        "build-image",
        "push-image",
        "deploy-candidate",
        "smoke-test",
        "promote-traffic",
    ]

    for expected_id in expected_order:
        assert expected_id in step_ids, f"Step '{expected_id}' must be present in cloudbuild.yaml"

    # Verify relative ordering
    indices = [step_ids.index(s_id) for s_id in expected_order]
    assert indices == sorted(indices), (
        f"Steps must execute in order: {expected_order}, got {step_ids}"
    )


# ==============================================================================
# 2. Quality Gates: Linting & Unit Test Coverage Gates
# ==============================================================================


def test_lint_step_configuration(cloudbuild_config: dict):
    """Verifies lint step enforces both ruff check and ruff format --check."""
    lint_step = next(s for s in cloudbuild_config["steps"] if s.get("id") == "lint")
    args_str = " ".join(lint_step.get("args", []))

    assert "ruff check" in args_str, "Lint step must run 'ruff check'"
    assert "ruff format --check" in args_str, "Lint step must run 'ruff format --check'"
    assert "backend" in args_str, "Lint step must target backend directory"


def test_unit_test_step_coverage_gate(cloudbuild_config: dict):
    """Verifies unit-tests step enforces Pytest with coverage gate >= 80%."""
    test_step = next(s for s in cloudbuild_config["steps"] if s.get("id") == "unit-tests")
    args_str = " ".join(test_step.get("args", []))

    assert "pytest" in args_str, "Unit tests step must execute pytest"
    assert "--cov" in args_str, "Unit tests step must enable pytest coverage"

    # Match --cov-fail-under=XX and verify threshold >= 80
    match = re.search(r"--cov-fail-under=(\d+)", args_str)
    assert match is not None, "Unit tests step must specify --cov-fail-under flag"
    threshold = int(match.group(1))
    assert threshold >= 80, f"Coverage threshold must be >= 80%, found {threshold}%"


# ==============================================================================
# 3. Artifact Registry & Container Packaging Tests
# ==============================================================================


def test_container_build_and_push_tags(cloudbuild_config: dict):
    """Verifies build-image step produces both commit SHA and latest tags in Artifact Registry."""
    build_step = next(s for s in cloudbuild_config["steps"] if s.get("id") == "build-image")
    args = build_step.get("args", [])

    expected_repo = "${_REGION}-docker.pkg.dev/${_PROJECT_ID}/catalog-agent-repo/backend"
    sha_tag = f"{expected_repo}:${{SHORT_SHA}}"
    latest_tag = f"{expected_repo}:latest"

    assert "-t" in args, "Docker build must define tags"
    assert sha_tag in args, f"Docker build must tag with {sha_tag}"
    assert latest_tag in args, f"Docker build must tag with {latest_tag}"
    assert "deployment/Dockerfile" in args, "Docker build must reference deployment/Dockerfile"

    # Check images section
    images = cloudbuild_config.get("images", [])
    assert sha_tag in images, f"Top-level images list must include {sha_tag}"


# ==============================================================================
# 4. Safe Deployment: Canary Strategy & Zero-Downtime Rollout
# ==============================================================================


def test_deploy_candidate_flags(cloudbuild_config: dict):
    """Verifies revision is deployed with canary tags and no initial traffic."""
    deploy_step = next(s for s in cloudbuild_config["steps"] if s.get("id") == "deploy-candidate")
    args = deploy_step.get("args", [])

    assert "run" in args and "deploy" in args, "Step must execute 'gcloud run deploy'"
    assert "catalog-comparison-service" in args, "Service name must be catalog-comparison-service"
    assert "--no-traffic" in args, (
        "Deployment must use --no-traffic for safe canary verification before promotion"
    )
    assert "--tag" in args, "Deployment must assign a revision tag"
    tag_idx = args.index("--tag")
    assert args[tag_idx + 1] == "candidate", "Revision tag must be 'candidate'"

    # Verify service account binding
    assert "--service-account" in args, "Deployment must specify a dedicated service account"
    sa_idx = args.index("--service-account")
    assert args[sa_idx + 1] == "catalog-agent-sa@${_PROJECT_ID}.iam.gserviceaccount.com"


def test_smoke_test_health_probe(cloudbuild_config: dict):
    """Verifies smoke test probes candidate revision /health and /health/ready."""
    smoke_step = next(s for s in cloudbuild_config["steps"] if s.get("id") == "smoke-test")
    args_str = " ".join(smoke_step.get("args", []))

    assert "/health" in args_str, "Smoke test step must probe /health endpoint"
    assert "/health/ready" in args_str, "Smoke test step must probe /health/ready endpoint"
    assert "candidate" in args_str, "Smoke test step must query candidate revision tag URL"


def test_promote_traffic_step(cloudbuild_config: dict):
    """Verifies promotion step cuts over traffic to the verified latest revision."""
    promote_step = next(s for s in cloudbuild_config["steps"] if s.get("id") == "promote-traffic")
    args = promote_step.get("args", [])

    assert "services" in args and "update-traffic" in args, (
        "Promote step must execute 'gcloud run services update-traffic'"
    )
    assert "catalog-comparison-service" in args, "Target must be catalog-comparison-service"
    assert "--to-latest" in args or any("--to-revisions" in arg for arg in args), (
        "Promote step must route traffic to verified latest revision"
    )


def test_cloud_deploy_integration(cloudbuild_config: dict):
    """Verifies Cloud Build integrates with Google Cloud Deploy for automated progressive delivery."""
    deploy_step = next(
        (s for s in cloudbuild_config["steps"] if s.get("id") == "cloud-deploy-release"),
        None,
    )
    assert deploy_step is not None, "Pipeline must declare 'cloud-deploy-release' step"
    args_str = " ".join(deploy_step.get("args", []))
    assert "gcloud deploy releases create" in args_str
    assert "catalog-service-pipeline" in args_str
    assert "deployment/clouddeploy" in args_str


# ==============================================================================
# 5. Multi-Stage Hardened Dockerfile Tests
# ==============================================================================


def test_dockerfile_multi_stage_architecture(dockerfile_content: str):
    """Verifies Dockerfile utilizes multi-stage build (builder + runner)."""
    assert re.search(r"FROM\s+python:[\w\.-]+\s+as\s+builder", dockerfile_content, re.IGNORECASE), (
        "Dockerfile must declare a builder stage"
    )
    assert re.search(r"FROM\s+python:[\w\.-]+\s+as\s+runner", dockerfile_content, re.IGNORECASE), (
        "Dockerfile must declare a runner stage"
    )


def test_dockerfile_security_least_privilege(dockerfile_content: str):
    """Verifies Dockerfile executes under a dedicated non-root user."""
    assert "useradd" in dockerfile_content or "adduser" in dockerfile_content, (
        "Dockerfile must create a dedicated system user"
    )
    assert re.search(r"USER\s+(?!root\b)\w+", dockerfile_content), (
        "Dockerfile must specify a non-root USER instruction"
    )


def test_dockerfile_port_and_healthcheck(dockerfile_content: str):
    """Verifies Dockerfile exposes port 8080 and defines a container healthcheck."""
    assert "EXPOSE 8080" in dockerfile_content, "Dockerfile must expose port 8080"
    assert "HEALTHCHECK" in dockerfile_content, "Dockerfile must define a HEALTHCHECK instruction"
    assert "uvicorn" in dockerfile_content, "Dockerfile CMD must execute uvicorn"


# ==============================================================================
# 6. Rollback Automation Tests
# ==============================================================================


def test_rollback_script_exists_and_executable():
    """Verifies deployment/rollback.sh exists with proper structure."""
    assert ROLLBACK_SCRIPT.exists(), f"Missing rollback script at {ROLLBACK_SCRIPT}"
    content = ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in content or "#!/bin/bash" in content, (
        "Rollback script must have valid bash shebang"
    )
    assert "gcloud run services update-traffic" in content, (
        "Rollback script must execute gcloud run services update-traffic"
    )
    assert "catalog-comparison-service" in content, (
        "Rollback script must target catalog-comparison-service"
    )


def test_rollback_cloudbuild_pipeline(rollback_build_config: dict):
    """Verifies cloudbuild-rollback.yaml executes automated rollback and health verification."""
    steps = rollback_build_config.get("steps", [])
    assert len(steps) >= 2, "Rollback pipeline must have at least 2 steps"
    all_args = " ".join([" ".join(s.get("args", [])) for s in steps])

    assert "update-traffic" in all_args, "Rollback pipeline must update traffic"
    assert "catalog-comparison-service" in all_args, (
        "Rollback pipeline must target catalog-comparison-service"
    )
    assert "/health" in all_args, "Rollback pipeline must verify service health post-rollback"


# ==============================================================================
# 7. Standalone Pipeline Validator CLI Tests
# ==============================================================================


def test_validate_pipeline_cli():
    """Verifies deployment/validate_pipeline.py runs and exits 0 on valid deployment config."""
    assert VALIDATOR_SCRIPT.exists(), f"Missing pipeline validator at {VALIDATOR_SCRIPT}"
    result = subprocess.run(
        ["python3", str(VALIDATOR_SCRIPT), "--repo-root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"validate_pipeline.py failed with exit code {result.returncode}:\n{result.stderr}\n{result.stdout}"
    )
    assert "All CI/CD pipeline validation checks passed" in result.stdout
