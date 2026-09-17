#!/usr/bin/env bash
# Script to verify active Google Cloud authentication and Application Default Credentials (ADC).
set -uo pipefail

TARGET_PROJECT="${TARGET_PROJECT:-fde-bestbuy-sandbox-dev-508321}"
AUTO_PROMPT="${1:-}"

echo "=== [GCLOUD AUTH CHECK] Checking Google Cloud authentication status ==="

# 1. Check gcloud CLI token validity
GCLOUD_AUTH_OK=false
TOKEN_OUTPUT=$(gcloud auth print-access-token 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ] && [ -n "$TOKEN_OUTPUT" ] && [[ "$TOKEN_OUTPUT" != *"ERROR"* ]] && [[ "$TOKEN_OUTPUT" != *"Reauthentication"* ]]; then
    GCLOUD_AUTH_OK=true
fi

# 2. Check Application Default Credentials (ADC)
ADC_AUTH_OK=false
ADC_TOKEN_OUTPUT=$(gcloud auth application-default print-access-token 2>&1 || true)
if [[ -n "$ADC_TOKEN_OUTPUT" ]] && [[ "$ADC_TOKEN_OUTPUT" != *"ERROR"* ]] && [[ "$ADC_TOKEN_OUTPUT" != *"Reauthentication"* ]]; then
    ADC_AUTH_OK=true
fi

# Check active project
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "none")

echo "  gcloud Access Token: $( [ "$GCLOUD_AUTH_OK" = true ] && echo "VALID" || echo "EXPIRED / REAUTH NEEDED" )"
echo "  ADC Credentials:    $( [ "$ADC_AUTH_OK" = true ] && echo "PRESENT" || echo "MISSING" )"
echo "  Current Project:    ${CURRENT_PROJECT} (Target: ${TARGET_PROJECT})"

if [ "$GCLOUD_AUTH_OK" = true ] && [ "$ADC_AUTH_OK" = true ]; then
    echo "[SUCCESS] Google Cloud credentials are fully active and valid."
    exit 0
fi

echo ""
echo "[WARNING] Active Google Cloud authentication is required for live cloud testing."
echo "Background agent sessions cannot interactively prompt for passwords or SSO."

if [ "$AUTO_PROMPT" == "--open-auth-pane" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PYTHON_HELPER="${SCRIPT_DIR}/open_gcloud_auth_pane.py"
    if [ -f "$PYTHON_HELPER" ]; then
        python3 "$PYTHON_HELPER" --project "$TARGET_PROJECT"
        exit $?
    fi
fi

echo "To authenticate manually, run in your interactive terminal:"
echo "  gcloud auth login"
echo "  gcloud auth application-default login"
echo "  gcloud config set project ${TARGET_PROJECT}"
echo ""
exit 1
