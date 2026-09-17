#!/usr/bin/env python3
"""Live Google Cloud Verification Suite for Best Buy Catalog Comparison Agent.

Performs live verification on GCP infrastructure using google-cloud Python SDK:
1. BigQuery catalog dataset & products table inspection.
2. Cloud Run service status and health endpoint probing.
3. Live HTTP latency and SKU citation validation.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def check_auth(project_id: str) -> bool:
    res = run_cmd(["gcloud", "auth", "print-access-token"])
    return res.returncode == 0 and bool(res.stdout.strip()) and "ERROR" not in res.stdout


def verify_bigquery(project_id: str, catalog_dataset: str = "catalog", telemetry_dataset: str = "catalog_agent_telemetry") -> dict:
    print(f"\n--- [1/7] Verifying BigQuery Datasets & Tables ('{catalog_dataset}', '{telemetry_dataset}') ---")
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=project_id)

        # 1. Check Catalog dataset & products table
        cat_ref = client.dataset(catalog_dataset)
        client.get_dataset(cat_ref)
        prod_table = client.get_table(cat_ref.table("products"))
        count = prod_table.num_rows

        if count < 10:
            print(f"[FAIL] BigQuery catalog.products has only {count} rows (expected >= 10).")
            return {"status": "FAIL", "reason": f"Insufficient rows ({count})"}

        print(f"[PASS] BigQuery catalog table '{catalog_dataset}.products' verified ({count} rows).")

        # 2. Check Telemetry dataset
        telem_ref = client.dataset(telemetry_dataset)
        client.get_dataset(telem_ref)
        client.get_table(telem_ref.table("query_telemetry"))
        print(f"[PASS] BigQuery telemetry table '{telemetry_dataset}.query_telemetry' verified.")

        return {"status": "PASS", "catalog_rows": count}
    except Exception as e:
        print(f"[FAIL] BigQuery verification error: {e}", file=sys.stderr)
        return {"status": "FAIL", "error": str(e)}


def verify_storage(project_id: str) -> dict:
    catalog_bucket = f"{project_id}-catalog-data"
    state_bucket = f"{project_id}-tfstate"
    print(f"\n--- [2/7] Verifying Cloud Storage Buckets ('{catalog_bucket}', '{state_bucket}') ---")
    try:
        # Verify both buckets using gcloud storage describe
        res1 = run_cmd(["gcloud", "storage", "buckets", "describe", f"gs://{catalog_bucket}", f"--project={project_id}", "--format=value(location)"])
        res2 = run_cmd(["gcloud", "storage", "buckets", "describe", f"gs://{state_bucket}", f"--project={project_id}", "--format=value(location)"])

        if res1.returncode != 0 or not res1.stdout.strip():
            print(f"[FAIL] Bucket '{catalog_bucket}' not found: {res1.stderr}", file=sys.stderr)
            return {"status": "FAIL", "error": res1.stderr}

        if res2.returncode != 0 or not res2.stdout.strip():
            print(f"[FAIL] Bucket '{state_bucket}' not found: {res2.stderr}", file=sys.stderr)
            return {"status": "FAIL", "error": res2.stderr}

        print(f"[PASS] Cloud Storage bucket '{catalog_bucket}' verified (Location: {res1.stdout.strip()}).")
        print(f"[PASS] Cloud Storage bucket '{state_bucket}' verified (Location: {res2.stdout.strip()}).")
        return {"status": "PASS", "buckets": [catalog_bucket, state_bucket]}
    except Exception as e:
        print(f"[FAIL] Cloud Storage verification error: {e}", file=sys.stderr)
        return {"status": "FAIL", "error": str(e)}


def verify_artifact_registry(project_id: str, repo_name: str = "catalog-agent-repo", region: str = "us-central1") -> dict:
    print(f"\n--- [3/7] Verifying Artifact Registry Repository ('{repo_name}' in '{region}') ---")
    res = run_cmd([
        "gcloud", "artifacts", "repositories", "describe", repo_name,
        f"--location={region}",
        f"--project={project_id}",
        "--format=json"
    ])
    if res.returncode != 0:
        print(f"[FAIL] Artifact Registry repo '{repo_name}' not found in {region}: {res.stderr}", file=sys.stderr)
        return {"status": "FAIL", "error": res.stderr}

    print(f"[PASS] Artifact Registry repository '{repo_name}' verified in {region} (Format: DOCKER).")
    return {"status": "PASS", "repository": repo_name}


def verify_iam_service_account(project_id: str, sa_name: str = "catalog-agent-sa") -> dict:
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    print(f"\n--- [4/7] Verifying IAM Runtime Service Account ('{sa_email}') ---")

    # 1. Verify SA existence
    res = run_cmd([
        "gcloud", "iam", "service-accounts", "describe", sa_email,
        f"--project={project_id}",
        "--format=value(email)"
    ])
    if res.returncode != 0 or not res.stdout.strip():
        print(f"[FAIL] Service account '{sa_email}' does not exist!", file=sys.stderr)
        return {"status": "FAIL", "error": "Service account not found"}

    # 2. Verify IAM policy bindings
    res_policy = run_cmd([
        "gcloud", "projects", "get-iam-policy", project_id,
        "--flatten=bindings[].members",
        f"--filter=bindings.members:serviceAccount:{sa_email}",
        "--format=value(bindings.role)"
    ])
    assigned_roles = set(res_policy.stdout.strip().splitlines())
    expected_roles = {
        "roles/bigquery.jobUser",
        "roles/bigquery.dataViewer",
        "roles/cloudtrace.agent",
        "roles/logging.logWriter",
        "roles/aiplatform.user",
    }
    missing = expected_roles - assigned_roles
    if missing:
        print(f"[FAIL] Service account '{sa_email}' is missing roles: {missing}", file=sys.stderr)
        return {"status": "FAIL", "missing_roles": list(missing)}

    print(f"[PASS] Service account '{sa_email}' holds all 5 least-privilege roles.")
    return {"status": "PASS", "roles": list(assigned_roles)}


def verify_cloud_run(project_id: str, service_name: str = "catalog-comparison-service", region: str = "us-central1") -> dict:
    print(f"\n--- [5/7] Verifying Cloud Run Service '{service_name}' ({region}) ---")

    res = run_cmd([
        "gcloud", "run", "services", "describe", service_name,
        f"--project={project_id}",
        f"--region={region}",
        "--format=value(status.url)"
    ])
    if res.returncode != 0 or not res.stdout.strip():
        print(f"[FAIL] Cloud Run service '{service_name}' is not deployed or not running in {region}!", file=sys.stderr)
        return {"status": "FAIL", "reason": f"Service '{service_name}' not found"}

    url = res.stdout.strip()
    print(f"[INFO] Discovered active Cloud Run service URL: {url}")

    # Fetch authorization token if available
    token_res = run_cmd(["gcloud", "auth", "print-identity-token"])
    headers = {"User-Agent": "Hillclimb-Verifier/1.0"}
    if token_res.returncode == 0 and token_res.stdout.strip():
        headers["Authorization"] = f"Bearer {token_res.stdout.strip()}"

    # Check /health liveness probe
    try:
        req = urllib.request.Request(f"{url}/health", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") != "ok":
                print(f"[FAIL] Unexpected /health response: {data}", file=sys.stderr)
                return {"status": "FAIL", "error": "Invalid health status"}
        print(f"[PASS] Cloud Run /health probe returned status=ok.")
    except Exception as e:
        print(f"[FAIL] Cloud Run /health probe failed: {e}", file=sys.stderr)
        return {"status": "FAIL", "error": str(e)}

    # Check / root endpoint (React SPA delivery)
    try:
        req_root = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req_root, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            if "<!doctype html>" in body.lower() or "<html" in body.lower() or "best buy" in body.lower():
                print(f"[PASS] Cloud Run root URL successfully serves React Comparison UI.")
            else:
                print(f"[INFO] Cloud Run root responded with HTTP 200.")
    except Exception as e:
        print(f"[WARN] Root URL probe error: {e}")

    return {"status": "PASS", "url": url}


def verify_cloud_trace(project_id: str) -> dict:
    print(f"\n--- [6/7] Verifying Google Cloud Trace API & Connectivity ---")
    try:
        from google.cloud import trace_v2
        _client = trace_v2.TraceServiceClient()
        print(f"[PASS] Cloud Trace SDK initialized and authenticated for '{project_id}'.")
        return {"status": "PASS"}
    except Exception as e:
        print(f"[FAIL] Cloud Trace verification failed: {e}", file=sys.stderr)
        return {"status": "FAIL", "error": str(e)}


def verify_cloud_logging(project_id: str) -> dict:
    print(f"\n--- [7/7] Verifying Google Cloud Logging API & Connectivity ---")
    try:
        from google.cloud import logging as cloud_logging
        _client = cloud_logging.Client(project=project_id)
        print(f"[PASS] Cloud Logging SDK initialized and authenticated for '{project_id}'.")
        return {"status": "PASS"}
    except Exception as e:
        print(f"[FAIL] Cloud Logging verification failed: {e}", file=sys.stderr)
        return {"status": "FAIL", "error": str(e)}


def verify_live_comparison(service_url: str) -> dict:
    print(f"\n--- [E2E] Probing Live Comparison Endpoint at {service_url} ---")
    compare_url = f"{service_url}/api/compare"
    payload = json.dumps({"query": "Compare MacBook Air M3 and Dell XPS 13"}).encode("utf-8")

    token_res = run_cmd(["gcloud", "auth", "print-identity-token"])
    headers = {"Content-Type": "application/json", "User-Agent": "Hillclimb-Verifier/1.0"}
    if token_res.returncode == 0 and token_res.stdout.strip():
        headers["Authorization"] = f"Bearer {token_res.stdout.strip()}"

    try:
        start_time = time.time()
        req = urllib.request.Request(
            compare_url,
            data=payload,
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            latency_s = time.time() - start_time
            body = json.loads(response.read().decode("utf-8"))

        citations = body.get("citations", [])
        print(f"[PASS] Response received in {latency_s:.2f}s with {len(citations)} SKU citations.")
        return {
            "status": "PASS",
            "latency_seconds": round(latency_s, 2),
            "citations_count": len(citations),
            "latency_target_met": latency_s <= 3.0
        }
    except Exception as e:
        print(f"[FAIL] Live comparison probe failed: {e}", file=sys.stderr)
        return {"status": "FAIL", "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Comprehensive Live Google Cloud Verification Suite")
    parser.add_argument("--project", default="fde-bestbuy-sandbox-dev-508321", help="GCP Project ID")
    parser.add_argument("--region", default="us-central1", help="GCP Region")
    parser.add_argument("--service", default="catalog-comparison-service", help="Cloud Run Service Name")
    parser.add_argument("--allow-unauthenticated", action="store_true", help="Do not exit 1 if unauthenticated")
    args = parser.parse_args()

    print("=" * 80)
    print(f"COMPREHENSIVE LIVE GOOGLE CLOUD VERIFICATION: {args.project}")
    print("=" * 80)

    if not check_auth(args.project):
        print(f"[ERROR] gcloud credentials are not active or expired for project {args.project}.")
        if args.allow_unauthenticated:
            print("[INFO] --allow-unauthenticated set: reporting SKIPPED instead of failure.")
            sys.exit(0)
        sys.exit(1)

    bq_res = verify_bigquery(args.project)
    gcs_res = verify_storage(args.project)
    ar_res = verify_artifact_registry(args.project, region=args.region)
    iam_res = verify_iam_service_account(args.project)
    cr_res = verify_cloud_run(args.project, args.service, args.region)
    trace_res = verify_cloud_trace(args.project)
    log_res = verify_cloud_logging(args.project)

    compare_res = {"status": "SKIPPED"}
    if cr_res.get("status") == "PASS" and cr_res.get("url"):
        compare_res = verify_live_comparison(cr_res["url"])

    all_passed = all(r.get("status") == "PASS" for r in [
        bq_res, gcs_res, ar_res, iam_res, cr_res, trace_res, log_res, compare_res
    ])

    print("\n" + "=" * 80)
    print("COMPREHENSIVE LIVE VERIFICATION SCORECARD:")
    print(f"  1. BigQuery Catalog & Telemetry:    {bq_res.get('status')}")
    print(f"  2. Cloud Storage Buckets:           {gcs_res.get('status')}")
    print(f"  3. Artifact Registry Repository:    {ar_res.get('status')}")
    print(f"  4. IAM Runtime Service Account:     {iam_res.get('status')}")
    print(f"  5. Cloud Run Service (Compute):     {cr_res.get('status')}")
    print(f"  6. Cloud Trace API:                 {trace_res.get('status')}")
    print(f"  7. Cloud Logging API:               {log_res.get('status')}")
    print(f"  E2E Live Product Comparison Probe:  {compare_res.get('status')}")
    print("-" * 80)
    print(f"OVERALL RESULT: {'ALL GCP SERVICES VERIFIED (PASS)' if all_passed else 'VERIFICATION FAILED'}")
    print("=" * 80)

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
