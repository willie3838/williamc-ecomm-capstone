"""Unit and validation tests for Cloud Build CI/CD pipeline and deployment assets.

Ensures compliance with Rubric 6.1 (CI/CD & Deployment), Rubric 6.2 (IaC & Parity),
and SPEC.md requirements:
- Ruff linting and formatting gates.
- Pytest coverage gate (>=80%).
- Multi-stage container build with Artifact Registry tagging.
- Decoupled Cloud Build CI and Google Cloud Deploy CD.
- Safe canary 0% deployment with candidate verification probes (/health, /health/ready, /openapi.json).
- Automated 100% traffic promotion and rollback protection.
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
CLOUDDEPLOY_DIR = DEPLOYMENT_DIR / "clouddeploy"
CLOUDDEPLOY_FILE = CLOUDDEPLOY_DIR / "clouddeploy.yaml"
SKAFFOLD_FILE = CLOUDDEPLOY_DIR / "skaffold.yaml"
SERVICE_FILE = CLOUDDEPLOY_DIR / "service.yaml"


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


@pytest.fixture(scope="module")
def clouddeploy_docs() -> list[dict]:
    """Loads and parses multi-document deployment/clouddeploy/clouddeploy.yaml."""
    assert CLOUDDEPLOY_FILE.exists(), f"Missing {CLOUDDEPLOY_FILE}"
    with open(CLOUDDEPLOY_FILE, encoding="utf-8") as f:
        data = list(yaml.safe_load_all(f))
    return [d for d in data if isinstance(d, dict)]


@pytest.fixture(scope="module")
def skaffold_config() -> dict:
    """Loads and parses deployment/clouddeploy/skaffold.yaml."""
    assert SKAFFOLD_FILE.exists(), f"Missing {SKAFFOLD_FILE}"
    with open(SKAFFOLD_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "skaffold.yaml must be a valid YAML mapping"
    return data


@pytest.fixture(scope="module")
def service_config() -> dict:
    """Loads and parses deployment/clouddeploy/service.yaml."""
    assert SERVICE_FILE.exists(), f"Missing {SERVICE_FILE}"
    with open(SERVICE_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "service.yaml must be a valid YAML mapping"
    return data


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
        "adk-eval",
        "eval-benchmark",
        "build-image",
        "push-image",
        "create-cloud-deploy-release",
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


def test_adk_eval_step(cloudbuild_config: dict):
    """Verifies adk-eval and eval-benchmark steps execute simple_test.evalset.json, runner.py, and analyze.py."""
    adk_step = next((s for s in cloudbuild_config["steps"] if s.get("id") == "adk-eval"), None)
    assert adk_step is not None, "Pipeline must include 'adk-eval' step"
    adk_args_str = " ".join(adk_step.get("args", []))
    assert "test_eval_adk.py" in adk_args_str, "adk-eval step must run test_eval_adk.py"
    assert "simple_test.evalset.json" in adk_args_str, (
        "adk-eval step must run evals/runner.py on simple_test.evalset.json"
    )

    bench_step = next(
        (s for s in cloudbuild_config["steps"] if s.get("id") == "eval-benchmark"), None
    )
    assert bench_step is not None, "Pipeline must include 'eval-benchmark' step"
    bench_args_str = " ".join(bench_step.get("args", []))
    assert "evals/runner.py" in bench_args_str, "eval-benchmark must run evals/runner.py"
    assert "--fail-on-threshold" in bench_args_str, (
        "eval-benchmark must enforce --fail-on-threshold"
    )
    assert "evals/analyze.py" in bench_args_str, "eval-benchmark must run evals/analyze.py"
    assert "evals/reports/baseline_results.json" in bench_args_str, (
        "eval-benchmark must compare against evals/reports/baseline_results.json"
    )
    assert "--fail-on-regression" in bench_args_str, (
        "eval-benchmark must enforce --fail-on-regression"
    )


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
# 4. Continuous Delivery: Cloud Deploy Delivery, Canary & Verification Tests
# ==============================================================================


def test_create_cloud_deploy_release_step(cloudbuild_config: dict):
    """Verifies Cloud Build invokes Google Cloud Deploy to trigger CD."""
    cd_step = next(
        (s for s in cloudbuild_config["steps"] if s.get("id") == "create-cloud-deploy-release"),
        None,
    )
    assert cd_step is not None, "Pipeline must declare 'create-cloud-deploy-release' step"
    args_str = " ".join(cd_step.get("args", []))
    assert "gcloud deploy releases create" in args_str
    assert "catalog-service-pipeline" in args_str
    assert "deployment/clouddeploy" in args_str


def test_cloud_deploy_pipeline_canary_config(clouddeploy_docs: list[dict]):
    """Verifies Cloud Deploy delivery pipeline defines 0% canary with automatic traffic control and verify."""
    pipeline = next((d for d in clouddeploy_docs if d.get("kind") == "DeliveryPipeline"), None)
    assert pipeline is not None, "clouddeploy.yaml must define a DeliveryPipeline"
    assert pipeline.get("metadata", {}).get("name") == "catalog-service-pipeline"

    stages = pipeline.get("serialPipeline", {}).get("stages", [])
    prod_stage = next((s for s in stages if s.get("targetId") == "cloudrun-prod"), None)
    assert prod_stage is not None, "DeliveryPipeline must include 'cloudrun-prod' stage"

    canary = prod_stage.get("strategy", {}).get("canary", {})
    percentages = canary.get("canaryDeployment", {}).get("percentages", [])
    assert percentages == [0], f"Canary strategy must be 0% initial cutover, found {percentages}"
    assert canary.get("canaryDeployment", {}).get("verify") is True, (
        "Canary stage must enable verification ('verify: true')"
    )
    assert (
        canary.get("runtimeConfig", {}).get("cloudRun", {}).get("automaticTrafficControl") is True
    ), "Cloud Run runtimeConfig must enable automaticTrafficControl"


def test_cloud_deploy_automation_rules(clouddeploy_docs: list[dict]):
    """Verifies Cloud Deploy Automation resource defines auto-advance rules."""
    automation = next((d for d in clouddeploy_docs if d.get("kind") == "Automation"), None)
    assert automation is not None, "clouddeploy.yaml must declare an Automation resource"

    rules = automation.get("rules", [])
    has_advance = any("advanceRolloutRule" in r for r in rules)

    assert has_advance, "Automation must declare an advanceRolloutRule for promotion to 100%"


def test_skaffold_verify_probes(skaffold_config: dict):
    """Verifies skaffold.yaml defines candidate verification probes for health and readiness."""
    assert "deploy" in skaffold_config and "cloudrun" in skaffold_config.get("deploy", {}), (
        "skaffold.yaml must configure deploy.cloudrun"
    )

    verify_entries = skaffold_config.get("verify", [])
    assert len(verify_entries) >= 1, "skaffold.yaml must declare verify probes"
    probe_args = " ".join(verify_entries[0].get("container", {}).get("args", []))

    assert "/health" in probe_args, "Verify probe must test /health endpoint"
    assert "/health/ready" in probe_args, "Verify probe must test /health/ready endpoint"
    assert "/openapi.json" in probe_args, "Verify probe must test /openapi.json endpoint"


def test_cloud_deploy_service_manifest(service_config: dict):
    """Verifies service.yaml targets catalog-comparison-service with health probes."""
    assert service_config.get("metadata", {}).get("name") == "catalog-comparison-service"
    template = service_config.get("spec", {}).get("template", {})
    containers = template.get("spec", {}).get("containers", [])
    assert len(containers) >= 1, "service.yaml must configure container"
    container = containers[0]
    assert "startupProbe" in container, "service.yaml container must declare startupProbe"
    assert "livenessProbe" in container, "service.yaml container must declare livenessProbe"


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
