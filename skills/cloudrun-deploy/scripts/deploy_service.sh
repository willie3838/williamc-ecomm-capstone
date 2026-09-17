#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PROJECT_ID="fde-bestbuy-sandbox-dev-508321"
REGION="us-central1"

echo "=== Submitting Build to Google Cloud Build (Project: ${PROJECT_ID}) ==="
gcloud builds submit \
  --config="${REPO_ROOT}/deployment/cloudbuild.yaml" \
  --substitutions=_REGION="${REGION}",_PROJECT_ID="${PROJECT_ID}" \
  "${REPO_ROOT}"

echo "=== Cloud Build Submitted Successfully ==="
