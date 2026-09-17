#!/usr/bin/env python3
"""Standalone CI/CD Pipeline & Deployment Validator.

Validates the Cloud Build pipeline configuration, Cloud Deploy delivery manifests,
Dockerfile container hardening, and rollback mechanisms against Capstone Rubric 6.1, 6.2
and SPEC.md requirements.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml


def validate_cloudbuild(cb_path: Path) -> list[str]:
    """Validates deployment/cloudbuild.yaml quality gates, deployment strategy, and schemas."""
    errors = []
    if not cb_path.exists():
        return [f"File not found: {cb_path}"]

    try:
        with open(cb_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"Failed to parse YAML from {cb_path}: {e}"]

    if not isinstance(config, dict):
        return ["cloudbuild.yaml must be a YAML dictionary"]

    # Top-level required keys
    for key in ["steps", "substitutions", "images", "options"]:
        if key not in config:
            errors.append(f"Missing required top-level key: '{key}'")

    # Substitutions
    subs = config.get("substitutions", {})
    if subs.get("_REGION") != "us-central1":
        errors.append(f"Expected _REGION='us-central1', got '{subs.get('_REGION')}'")
    if subs.get("_PROJECT_ID") != "fde-bestbuy-sandbox-dev-508321":
        errors.append(
            f"Expected _PROJECT_ID='fde-bestbuy-sandbox-dev-508321', got '{subs.get('_PROJECT_ID')}'"
        )

    # Step sequence and configuration
    steps = config.get("steps", [])
    step_ids = [s.get("id") for s in steps if isinstance(s, dict)]

    expected_steps = [
        "lint",
        "unit-tests",
        "adk-eval",
        "build-image",
        "push-image",
        "create-cloud-deploy-release",
    ]
    for exp in expected_steps:
        if exp not in step_ids:
            errors.append(f"Missing required build step: '{exp}'")

    # Lint step checks
    lint_step = next((s for s in steps if s.get("id") == "lint"), None)
    if lint_step:
        args_str = " ".join(lint_step.get("args", []))
        if "ruff check" not in args_str:
            errors.append("Lint step must execute 'ruff check'")
        if "ruff format --check" not in args_str:
            errors.append("Lint step must execute 'ruff format --check'")

    # Unit-tests coverage gate
    test_step = next((s for s in steps if s.get("id") == "unit-tests"), None)
    if test_step:
        args_str = " ".join(test_step.get("args", []))
        match = re.search(r"--cov-fail-under=(\d+)", args_str)
        if not match:
            errors.append("Unit tests step missing --cov-fail-under flag")
        elif int(match.group(1)) < 80:
            errors.append(f"Coverage gate threshold {match.group(1)}% is below mandatory 80%")

    # ADK eval step checks
    adk_step = next((s for s in steps if s.get("id") == "adk-eval"), None)
    if adk_step:
        args_str = " ".join(adk_step.get("args", []))
        if "test_eval_adk.py" not in args_str:
            errors.append("adk-eval step must execute pytest on evals/test_eval_adk.py")

    # Cloud Deploy release creation checks
    cd_step = next((s for s in steps if s.get("id") == "create-cloud-deploy-release"), None)
    if cd_step:
        args_str = " ".join(cd_step.get("args", []))
        if "deploy releases create" not in args_str:
            errors.append(
                "create-cloud-deploy-release step must execute 'gcloud deploy releases create'"
            )
        if "catalog-service-pipeline" not in args_str:
            errors.append(
                "create-cloud-deploy-release step must target delivery pipeline 'catalog-service-pipeline'"
            )

    return errors


def validate_clouddeploy(clouddeploy_dir: Path) -> list[str]:
    """Validates Cloud Deploy delivery pipeline, targets, automation, and skaffold manifests."""
    errors = []
    cd_yaml = clouddeploy_dir / "clouddeploy.yaml"
    skaffold_yaml = clouddeploy_dir / "skaffold.yaml"
    service_yaml = clouddeploy_dir / "service.yaml"

    if not cd_yaml.exists():
        return [f"Missing {cd_yaml}"]
    if not skaffold_yaml.exists():
        return [f"Missing {skaffold_yaml}"]
    if not service_yaml.exists():
        return [f"Missing {service_yaml}"]

    # 1. Parse clouddeploy.yaml documents
    try:
        with open(cd_yaml, encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))
    except yaml.YAMLError as e:
        return [f"Failed to parse YAML from {cd_yaml}: {e}"]

    pipeline_doc = next(
        (d for d in docs if isinstance(d, dict) and d.get("kind") == "DeliveryPipeline"),
        None,
    )
    if not pipeline_doc:
        errors.append("clouddeploy.yaml missing DeliveryPipeline resource")
    else:
        stages = pipeline_doc.get("serialPipeline", {}).get("stages", [])
        prod_stage = next((s for s in stages if s.get("targetId") == "cloudrun-prod"), None)
        if not prod_stage:
            errors.append("DeliveryPipeline missing stage targeting 'cloudrun-prod'")
        else:
            strategy = prod_stage.get("strategy", {}).get("canary", {})
            canary_cfg = strategy.get("canaryDeployment", {})
            percentages = canary_cfg.get("percentages", [])
            if percentages != [0]:
                errors.append(f"Expected canary percentages [0], got {percentages}")
            if not canary_cfg.get("verify", False):
                errors.append("Cloud Deploy canaryDeployment must have 'verify: true'")
            run_cfg = strategy.get("runtimeConfig", {}).get("cloudRun", {})
            if not run_cfg.get("automaticTrafficControl", False):
                errors.append(
                    "Cloud Deploy runtimeConfig must enable 'automaticTrafficControl: true'"
                )

    target_doc = next(
        (d for d in docs if isinstance(d, dict) and d.get("kind") == "Target"),
        None,
    )
    if not target_doc:
        errors.append("clouddeploy.yaml missing Target resource")

    automation_doc = next(
        (d for d in docs if isinstance(d, dict) and d.get("kind") == "Automation"),
        None,
    )
    if not automation_doc:
        errors.append("clouddeploy.yaml missing Automation resource for auto-advance/rollback")
    else:
        rules = automation_doc.get("rules", [])
        has_advance = any("advanceRolloutRule" in r for r in rules)
        if not has_advance:
            errors.append("Automation resource missing 'advanceRolloutRule'")

    # 2. Parse skaffold.yaml
    try:
        with open(skaffold_yaml, encoding="utf-8") as f:
            sk_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"Failed to parse YAML from {skaffold_yaml}: {e}"]

    if not isinstance(sk_config, dict):
        errors.append("skaffold.yaml must be a YAML dictionary")
    else:
        if "deploy" not in sk_config or "cloudrun" not in sk_config.get("deploy", {}):
            errors.append("skaffold.yaml missing 'deploy.cloudrun' configuration")
        verify_entries = sk_config.get("verify", [])
        if not verify_entries:
            errors.append(
                "skaffold.yaml missing 'verify' configuration for candidate health checks"
            )
        else:
            probe = verify_entries[0]
            args_str = " ".join(probe.get("container", {}).get("args", []))
            if "/health" not in args_str:
                errors.append("Skaffold verify must probe /health endpoint")

    # 3. Parse service.yaml
    try:
        with open(service_yaml, encoding="utf-8") as f:
            srv_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"Failed to parse YAML from {service_yaml}: {e}"]

    if (
        not isinstance(srv_config, dict)
        or srv_config.get("metadata", {}).get("name") != "catalog-comparison-service"
    ):
        errors.append("service.yaml must define service 'catalog-comparison-service'")

    return errors


def validate_cloudbuild_pr(cb_path: Path) -> list[str]:
    """Validates deployment/cloudbuild-pr.yaml quality gates."""
    errors = []
    if not cb_path.exists():
        return [f"File not found: {cb_path}"]

    try:
        with open(cb_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"Failed to parse YAML from {cb_path}: {e}"]

    if not isinstance(config, dict):
        return ["cloudbuild-pr.yaml must be a YAML dictionary"]

    steps = config.get("steps", [])
    step_ids = [s.get("id") for s in steps if isinstance(s, dict)]

    expected_steps = ["lint", "unit-tests", "eval-benchmark", "adk-eval"]
    for exp in expected_steps:
        if exp not in step_ids:
            errors.append(f"Missing required PR build step: '{exp}'")

    # Lint checks
    lint_step = next((s for s in steps if s.get("id") == "lint"), None)
    if lint_step:
        args_str = " ".join(lint_step.get("args", []))
        if "ruff check" not in args_str or "ruff format --check" not in args_str:
            errors.append("PR lint step must execute ruff check and ruff format --check")

    # Unit tests coverage gate
    test_step = next((s for s in steps if s.get("id") == "unit-tests"), None)
    if test_step:
        args_str = " ".join(test_step.get("args", []))
        match = re.search(r"--cov-fail-under=(\d+)", args_str)
        if not match or int(match.group(1)) < 80:
            errors.append("PR unit tests step must enforce --cov-fail-under >= 80")

    # Benchmark step
    eval_step = next((s for s in steps if s.get("id") == "eval-benchmark"), None)
    if eval_step:
        args_str = " ".join(eval_step.get("args", []))
        if "runner.py" not in args_str:
            errors.append("PR eval-benchmark step must execute runner.py")

    # ADK eval step
    adk_step = next((s for s in steps if s.get("id") == "adk-eval"), None)
    if adk_step:
        args_str = " ".join(adk_step.get("args", []))
        if "test_eval_adk.py" not in args_str:
            errors.append("PR adk-eval step must execute pytest on evals/test_eval_adk.py")

    return errors


def validate_dockerfile(dockerfile_path: Path) -> list[str]:
    """Validates Dockerfile multi-stage build, non-root security, and port configuration."""
    errors = []
    if not dockerfile_path.exists():
        return [f"File not found: {dockerfile_path}"]

    content = dockerfile_path.read_text(encoding="utf-8")

    if not re.search(r"FROM\s+python:[\w\.-]+\s+as\s+builder", content, re.IGNORECASE):
        errors.append("Dockerfile missing multi-stage 'builder' stage")
    if not re.search(r"FROM\s+python:[\w\.-]+\s+as\s+runner", content, re.IGNORECASE):
        errors.append("Dockerfile missing multi-stage 'runner' stage")
    if "useradd" not in content and "adduser" not in content:
        errors.append("Dockerfile does not create a non-root system user")
    if not re.search(r"USER\s+(?!root\b)\w+", content):
        errors.append("Dockerfile does not switch to a non-root USER")
    if "EXPOSE 8080" not in content:
        errors.append("Dockerfile must declare 'EXPOSE 8080'")
    if "HEALTHCHECK" not in content:
        errors.append("Dockerfile missing 'HEALTHCHECK' directive")
    if "uvicorn" not in content:
        errors.append("Dockerfile CMD must execute uvicorn server")

    return errors


def validate_rollback_assets(rollback_script: Path, rollback_yaml: Path) -> list[str]:
    """Validates existence and commands of rollback script and rollback pipeline."""
    errors = []
    if not rollback_script.exists():
        errors.append(f"Missing rollback script: {rollback_script}")
    else:
        content = rollback_script.read_text(encoding="utf-8")
        if "update-traffic" not in content:
            errors.append("rollback.sh missing 'update-traffic' command")
        if "catalog-comparison-service" not in content:
            errors.append("rollback.sh missing target service 'catalog-comparison-service'")

    if not rollback_yaml.exists():
        errors.append(f"Missing rollback pipeline: {rollback_yaml}")
    else:
        try:
            with open(rollback_yaml, encoding="utf-8") as f:
                rb_config = yaml.safe_load(f)
            if not isinstance(rb_config, dict) or "steps" not in rb_config:
                errors.append("cloudbuild-rollback.yaml must declare 'steps'")
        except yaml.YAMLError as e:
            errors.append(f"Failed to parse {rollback_yaml}: {e}")

    return errors


def main() -> int:
    """CLI entrypoint for pipeline validation."""
    parser = argparse.ArgumentParser(description="Validate CI/CD pipeline and deployment assets")
    parser.add_argument(
        "--repo-root", type=Path, default=Path.cwd(), help="Path to repository root"
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    deployment_dir = repo_root / "deployment"

    print(f"=== Validating CI/CD & Deployment Assets in: {deployment_dir} ===")

    all_errors = []

    # 1. Cloud Build CI Pipeline
    cb_errors = validate_cloudbuild(deployment_dir / "cloudbuild.yaml")
    if cb_errors:
        print("[FAIL] deployment/cloudbuild.yaml errors:")
        for err in cb_errors:
            print(f"  - {err}")
        all_errors.extend(cb_errors)
    else:
        print(
            "[PASS] deployment/cloudbuild.yaml satisfies all quality gates and Cloud Deploy release trigger."
        )

    # 1b. Cloud Build PR Pipeline
    cb_pr_errors = validate_cloudbuild_pr(deployment_dir / "cloudbuild-pr.yaml")
    if cb_pr_errors:
        print("[FAIL] deployment/cloudbuild-pr.yaml errors:")
        for err in cb_pr_errors:
            print(f"  - {err}")
        all_errors.extend(cb_pr_errors)
    else:
        print(
            "[PASS] deployment/cloudbuild-pr.yaml satisfies all quality gates and evaluation checks."
        )

    # 2. Cloud Deploy Delivery Manifests
    cd_errors = validate_clouddeploy(deployment_dir / "clouddeploy")
    if cd_errors:
        print("[FAIL] deployment/clouddeploy errors:")
        for err in cd_errors:
            print(f"  - {err}")
        all_errors.extend(cd_errors)
    else:
        print(
            "[PASS] deployment/clouddeploy manifests satisfy 0% -> 100% canary and verification rules."
        )

    # 3. Dockerfile Hardening
    df_errors = validate_dockerfile(deployment_dir / "Dockerfile")
    if df_errors:
        print("[FAIL] deployment/Dockerfile errors:")
        for err in df_errors:
            print(f"  - {err}")
        all_errors.extend(df_errors)
    else:
        print("[PASS] deployment/Dockerfile satisfies multi-stage and least-privilege security.")

    # 4. Rollback Assets
    rb_errors = validate_rollback_assets(
        deployment_dir / "rollback.sh",
        deployment_dir / "cloudbuild-rollback.yaml",
    )
    if rb_errors:
        print("[FAIL] Rollback assets errors:")
        for err in rb_errors:
            print(f"  - {err}")
        all_errors.extend(rb_errors)
    else:
        print("[PASS] Rollback script and Cloud Build rollback pipeline verified.")

    if all_errors:
        print(f"\nTotal Validation Failures: {len(all_errors)}")
        return 1

    print("\nAll CI/CD pipeline validation checks passed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
