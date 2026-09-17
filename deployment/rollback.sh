#!/usr/bin/env bash
# ==============================================================================
# Automated Rollback Script for Best Buy Catalog Comparison Agent
# Reverts Cloud Run traffic to the previous known stable revision or rollback release.
# Supports both Google Cloud Deploy rollback and direct Cloud Run traffic recovery.
# ==============================================================================
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-catalog-comparison-service}"
PIPELINE_NAME="${PIPELINE_NAME:-catalog-service-pipeline}"
REGION="${REGION:-us-central1}"
PROJECT_ID="${PROJECT_ID:-fde-bestbuy-sandbox-dev-508321}"
TARGET_REVISION="${1:-}"

echo "================================================================="
echo " Initiating Automated Rollback for Catalog Comparison Service"
echo " Service:   ${SERVICE_NAME}"
echo " Pipeline:  ${PIPELINE_NAME}"
echo " Region:    ${REGION}"
echo " Project:   ${PROJECT_ID}"
echo "================================================================="

# Attempt Cloud Deploy rollback first if no specific revision is requested
if [ -z "${TARGET_REVISION}" ]; then
  echo "Checking for active Cloud Deploy rollouts on ${PIPELINE_NAME}..."
  LATEST_ROLLOUT=$(gcloud deploy rollouts list \
    --delivery-pipeline="${PIPELINE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --format="value(name)" 2>/dev/null | head -n 1 || true)

  if [ -n "${LATEST_ROLLOUT}" ]; then
    echo "Found active/recent Cloud Deploy rollout: ${LATEST_ROLLOUT}"
    echo "Executing Cloud Deploy automated rollback..."
    if gcloud deploy rollouts rollback "${LATEST_ROLLOUT}" \
      --delivery-pipeline="${PIPELINE_NAME}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}" \
      --quiet 2>/dev/null; then
      echo "Cloud Deploy rollback initiated successfully."
    else
      echo "Notice: Falling back to direct Cloud Run traffic reversion."
    fi
  fi
fi

# Direct Cloud Run traffic update (ensures 100% stable traffic recovery)
if [ -z "${TARGET_REVISION}" ]; then
  echo "Querying previous stable revision from Cloud Run..."
  REVISIONS=$(gcloud run revisions list \
    --service="${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --sort-by="~metadata.creationTimestamp" \
    --format="value(metadata.name)")

  # Second line represents the previous revision
  TARGET_REVISION=$(echo "${REVISIONS}" | sed -n '2p')

  if [ -z "${TARGET_REVISION}" ]; then
    echo "ERROR: Could not detect a prior revision to rollback to."
    exit 1
  fi
fi

echo "Selected target revision for rollback: ${TARGET_REVISION}"
echo "Routing 100% traffic to target revision: ${TARGET_REVISION}..."
gcloud run services update-traffic "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --to-revisions="${TARGET_REVISION}=100"

echo "Verifying service health post-rollback..."
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")

if [ -z "${SERVICE_URL}" ]; then
  echo "WARNING: Could not determine service URL, skipping HTTP probe."
else
  echo "Probing ${SERVICE_URL}/health..."
  curl -sf --retry 3 "${SERVICE_URL}/health"
  echo ""
fi

echo "Rollback successfully completed. Active revision: ${TARGET_REVISION} (100% traffic)."
