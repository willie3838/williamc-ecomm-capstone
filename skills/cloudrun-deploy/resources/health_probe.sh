#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="fde-bestbuy-sandbox-dev-508321"
REGION="us-central1"
SERVICE_NAME="catalog-comparison-service"

echo "=== Fetching Cloud Run Service URL ==="
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format='value(status.url)' 2>/dev/null || true)

if [[ -z "${SERVICE_URL}" ]]; then
  echo "Cloud Run service '${SERVICE_NAME}' not yet deployed or unreachable in ${PROJECT_ID}."
  exit 0
fi

echo "Pinging ${SERVICE_URL}/health..."
START_TIME=$(date +%s%N)
HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" "${SERVICE_URL}/health")
END_TIME=$(date +%s%N)

STATUS_CODE=$(echo "${HTTP_RESPONSE}" | tail -n1)
BODY=$(echo "${HTTP_RESPONSE}" | sed '$d')
ELAPSED_MS=$(( (END_TIME - START_TIME) / 1000000 ))

echo "Status Code: ${STATUS_CODE}"
echo "Response Body: ${BODY}"
echo "Roundtrip Latency: ${ELAPSED_MS} ms"

if [[ "${STATUS_CODE}" == "200" && "${ELAPSED_MS}" -le 3000 ]]; then
  echo "PASS: Health check succeeded within 3.0s latency SLA."
else
  echo "FAIL: Health check failed SLA or returned non-200 code."
fi
