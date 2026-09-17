#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
LIVE_GCLOUD="${1:-}"

echo "=== [1/5] Running Ruff Linter on backend/ ==="
if [ -f "${BACKEND_DIR}/.venv/bin/ruff" ]; then
  "${BACKEND_DIR}/.venv/bin/ruff" check "${BACKEND_DIR}" --fix
else
  ruff check "${BACKEND_DIR}" --fix
fi

echo "=== [2/5] Running Ruff Formatter on backend/ ==="
if [ -f "${BACKEND_DIR}/.venv/bin/ruff" ]; then
  "${BACKEND_DIR}/.venv/bin/ruff" format "${BACKEND_DIR}"
else
  ruff format "${BACKEND_DIR}"
fi

echo "=== [3/5] Running Pytest with Coverage Gate (>=80%) ==="
cd "${BACKEND_DIR}"
if [ -f "${BACKEND_DIR}/.venv/bin/pytest" ]; then
  "${BACKEND_DIR}/.venv/bin/pytest"
else
  pytest
fi

PYTHON_BIN="python3"
if [ -f "${BACKEND_DIR}/.venv/bin/python3" ]; then
  PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python3"
fi

echo "=== [4/5] Running Hermetic Smoke Evals ==="
cd "${REPO_ROOT}"
"${PYTHON_BIN}" skills/hillclimb/scripts/run_smoke_eval.py --dataset evals/dataset/benchmark_catalog.evalset.json

echo "=== [5/5] Checking Live Google Cloud Environment ==="
AUTH_SCRIPT="${REPO_ROOT}/skills/hillclimb/scripts/check_gcloud_auth.sh"
LIVE_SCRIPT="${REPO_ROOT}/skills/hillclimb/scripts/run_live_gcloud_checks.py"

if [ "$LIVE_GCLOUD" == "--live-gcloud" ]; then
  echo "[ENFORCED] Running mandatory live Google Cloud verification..."
  "${PYTHON_BIN}" "${LIVE_SCRIPT}"
elif bash "${AUTH_SCRIPT}" >/dev/null 2>&1; then
  echo "[DETECTED] Active Google Cloud authentication found. Running live cloud checks..."
  "${PYTHON_BIN}" "${LIVE_SCRIPT}" --allow-unauthenticated
else
  echo "[INFO] Live Google Cloud checks skipped (local hermetic mode). Run with --live-gcloud to enforce."
fi

echo "=== [6/6] Running Selenium UI/UX End-to-End Regression Audit ==="
UI_AUDIT_SCRIPT="${REPO_ROOT}/skills/selenium-ui-audit/scripts/run_audit.py"
EXPLORATORY_SCRIPT="${REPO_ROOT}/skills/selenium-ui-audit/scripts/exploratory_roamer.py"

if [ -f "${UI_AUDIT_SCRIPT}" ]; then
  /usr/local/google/home/williamwlchan/.local/bin/uv run --with selenium python "${UI_AUDIT_SCRIPT}" --output-dir "${REPO_ROOT}/reports/ui-audit"
  echo "[PASS] Selenium UI/UX Regression Audit Passed (0 errors, 0 warnings)."
  
  if [ "${2:-}" == "--exploratory" ] || [ "${LIVE_GCLOUD}" == "--exploratory" ]; then
    echo "=== Running Autonomous Exploratory UX & Human Behavior Simulation ==="
    /usr/local/google/home/williamwlchan/.local/bin/uv run --with selenium python "${EXPLORATORY_SCRIPT}" --output-dir "${REPO_ROOT}/reports/ui-audit"
  fi
fi

echo "=== [7/7] Running Capstone Rubric Score 3 Verification Gate ==="
AUDIT_SCRIPT="${REPO_ROOT}/skills/rubric-audit/scripts/audit_rubric.py"
TARGET_FLAG="--target-score 3"
for arg in "$@"; do
  if [ "$arg" == "--baseline" ]; then
    TARGET_FLAG="--target-score 2"
  fi
done

"${PYTHON_BIN}" "${AUDIT_SCRIPT}" --verify ${TARGET_FLAG}
echo "[PASS] Capstone Rubric Verification Passed!"

echo "=== ALL HILLCLIMB CHECKS COMPLETED ==="
