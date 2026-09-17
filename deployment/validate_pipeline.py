#!/usr/bin/env python3
"""Standalone CI/CD Pipeline & Deployment Validator.

Validates the Cloud Build pipeline configuration, Dockerfile container hardening,
and rollback mechanisms against Capstone Rubric 6.1, 6.2 and SPEC.md requirements.
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
        "deploy-candidate",
        "smoke-test",
        "promote-traffic",
    ]
    for exp in expected_steps:
        if exp not in step_ids:
            errors.append(f"Missing required build step: '{exp}'")

    # ADK eval step checks
    adk_step = next((s for s in steps if s.get("id") == "adk-eval"), None)
    if adk_step:
        args_str = " ".join(adk_step.get("args", []))
        if "test_eval_adk.py" not in args_str:
            errors.append("adk-eval step must execute pytest on evals/test_eval_adk.py")

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
            errors.append(
                f"Coverage gate threshold {match.group(1)}% is below mandatory 80%"
            )

    # Deploy candidate flags
    deploy_step = next((s for s in steps if s.get("id") == "deploy-candidate"), None)
    if deploy_step:
        args = deploy_step.get("args", [])
        if "--no-traffic" not in args:
            errors.append(
                "deploy-candidate step must specify --no-traffic for canary safety"
            )
        if "--tag" not in args:
            errors.append("deploy-candidate step must assign a revision tag")
        if "catalog-comparison-service" not in args:
            errors.append(
                "deploy-candidate step must target 'catalog-comparison-service'"
            )

    # Smoke test checks
    smoke_step = next((s for s in steps if s.get("id") == "smoke-test"), None)
    if smoke_step:
        args_str = " ".join(smoke_step.get("args", []))
        if "/health" not in args_str or "/health/ready" not in args_str:
            errors.append(
                "smoke-test step must probe both /health and /health/ready endpoints"
            )

    # Promote traffic
    promote_step = next((s for s in steps if s.get("id") == "promote-traffic"), None)
    if promote_step:
        args = promote_step.get("args", [])
        if "--to-latest" not in args and not any("--to-revisions" in a for a in args):
            errors.append(
                "promote-traffic step must update traffic to latest verified revision"
            )

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
            errors.append(
                "PR lint step must execute ruff check and ruff format --check"
            )

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
            errors.append(
                "PR adk-eval step must execute pytest on evals/test_eval_adk.py"
            )

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
            errors.append(
                "rollback.sh missing target service 'catalog-comparison-service'"
            )

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
    parser = argparse.ArgumentParser(
        description="Validate CI/CD pipeline and deployment assets"
    )
    parser.add_argument(
        "--repo-root", type=Path, default=Path.cwd(), help="Path to repository root"
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    deployment_dir = repo_root / "deployment"

    print(f"=== Validating CI/CD & Deployment Assets in: {deployment_dir} ===")

    all_errors = []

    # 1. Cloud Build Pipeline
    cb_errors = validate_cloudbuild(deployment_dir / "cloudbuild.yaml")
    if cb_errors:
        print("[FAIL] deployment/cloudbuild.yaml errors:")
        for err in cb_errors:
            print(f"  - {err}")
        all_errors.extend(cb_errors)
    else:
        print(
            "[PASS] deployment/cloudbuild.yaml satisfies all quality gates and deployment rules."
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

    # 2. Dockerfile Hardening
    df_errors = validate_dockerfile(deployment_dir / "Dockerfile")
    if df_errors:
        print("[FAIL] deployment/Dockerfile errors:")
        for err in df_errors:
            print(f"  - {err}")
        all_errors.extend(df_errors)
    else:
        print(
            "[PASS] deployment/Dockerfile satisfies multi-stage and least-privilege security."
        )

    # 3. Rollback Assets
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
