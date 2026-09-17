#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TF_DIR="${REPO_ROOT}/deployment/terraform"
PROJECT_ID="fde-bestbuy-sandbox-dev-508321"
REGION="us-central1"

ACTION="${1:-plan}"

cd "${TF_DIR}"

echo "=== Initializing Terraform in ${TF_DIR} ==="
terraform init -upgrade

echo "=== Validating Terraform Configuration ==="
terraform fmt -check
terraform validate

if [[ "${ACTION}" == "plan" ]]; then
  echo "=== Running Terraform Plan for ${PROJECT_ID} ==="
  terraform plan -var="project_id=${PROJECT_ID}" -var="region=${REGION}" -out=tfplan
elif [[ "${ACTION}" == "apply" ]]; then
  echo "=== Applying Terraform Changes to ${PROJECT_ID} ==="
  terraform apply -auto-approve tfplan
else
  echo "Usage: $0 [plan|apply]"
  exit 1
fi
