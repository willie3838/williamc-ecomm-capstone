#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PROJECT_ID="fde-bestbuy-sandbox-dev-508321"
REGION="us-central1"

PYTHON_BIN="python3"
if [[ -x "${REPO_ROOT}/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_ROOT}/backend/.venv/bin/python"
fi

echo "=== [PRE-DEPLOY GATE] Verifying Live Vertex AI + BigQuery Latency (< 3.0s) ==="
env -u PYTEST_CURRENT_TEST -u HERMETIC_EVAL "${PYTHON_BIN}" "${REPO_ROOT}/backend/scripts/verify_live_latency.py" --threshold-ms 3000

echo "=== Submitting Build to Google Cloud Build (Project: ${PROJECT_ID}) ==="
SHORT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD)"
gcloud builds submit \
  --config="${REPO_ROOT}/deployment/cloudbuild.yaml" \
  --substitutions=_REGION="${REGION}",_PROJECT_ID="${PROJECT_ID}",SHORT_SHA="${SHORT_SHA}" \
  "${REPO_ROOT}"

echo "=== [POST-DEPLOY GATE] Verifying Live Deployed Environment Latency (< 3.0s) ==="
env -u PYTEST_CURRENT_TEST -u HERMETIC_EVAL "${PYTHON_BIN}" "${REPO_ROOT}/skills/hillclimb/scripts/run_live_gcloud_checks.py" --project "${PROJECT_ID}" --region "${REGION}"

echo "=== Cloud Build Deployed & Verified (< 3.0s Live SLA) Successfully ==="
