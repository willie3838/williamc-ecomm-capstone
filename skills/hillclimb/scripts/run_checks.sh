#!/usr/bin/env bash
# ==============================================================================
# Unified Hillclimbing Verification & Monotonic Ratchet Runner
#
# Executes the Multi-Tier Hillclimbing Pipeline:
#   [1/8] Ruff Linter & Formatter (backend/)
#   [2/8] Pytest Unit & Contract Tests (>=80% coverage gate)
#   [3/8] Frontend TypeScript & Vite Production Build Check
#   [4/8] Production 80-Pair Evaluation Suite (evals.runner + evals.analyze)
#   [5/8] Disaster Recovery & Chaos Resilience Verification
#   [6/8] Live Google Cloud Infrastructure & E2E Verification
#   [7/8] Selenium Headless Chrome UI/UX Regression Audit
#   [8/8] Capstone Rubric Audit & Monotonic High-Water Mark Ratchet
#
# If any stage fails or regresses, records diagnostics to logs/hillclimb_latest_report.json
# and dispatches (or prints) the Swarm Reviewer + Developer pair command (--model argon).
# ==============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
FRONTEND_DIR="${REPO_ROOT}/frontend"

PYTHON_BIN="python3"
if [ -f "${BACKEND_DIR}/.venv/bin/python3" ]; then
  PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python3"
fi

LIVE_GCLOUD=false
EXPLORATORY=false
TARGET_FLAG="--target-score 3"
FRESH_AUDIT=false
SKIP_UI=false
AUTO_SWARM=false

for arg in "$@"; do
  case "$arg" in
    --live-gcloud)
      LIVE_GCLOUD=true
      ;;
    --exploratory)
      EXPLORATORY=true
      ;;
    --baseline)
      TARGET_FLAG="--target-score 2"
      ;;
    --fresh-audit)
      FRESH_AUDIT=true
      ;;
    --skip-ui)
      SKIP_UI=true
      ;;
    --auto-swarm)
      AUTO_SWARM=true
      ;;
    *)
      ;;
  esac
done

CURRENT_STAGE="Initialization"
RATCHET_SCRIPT="${REPO_ROOT}/skills/hillclimb/scripts/hillclimb_ratchet.py"
SWARM_DISPATCH_SCRIPT="${REPO_ROOT}/skills/hillclimb/scripts/dispatch_hillclimb_swarm.py"

on_failure() {
  local exit_code=$?
  echo ""
  echo "================================================================================"
  echo "❌ HILLCLIMB CHECK FAILED AT STAGE: ${CURRENT_STAGE} (exit code ${exit_code})"
  echo "================================================================================"
  "${PYTHON_BIN}" "${RATCHET_SCRIPT}" --record-failure "${CURRENT_STAGE}" "Stage exited with code ${exit_code}" || true
  echo ""
  echo "🐝 SWARM REMEDIATION PROTOCOL (Tech Lead Reviewer + Senior Engineer Developer):"
  echo "   To fix this failure with an Argon Reviewer + Developer pair in isolated worktrees, run:"
  echo "   python3 skills/hillclimb/scripts/dispatch_hillclimb_swarm.py --from-report logs/hillclimb_latest_report.json"
  echo "================================================================================"
  if [ "$AUTO_SWARM" = true ]; then
    echo "[AUTO-SWARM] Automatically dispatching Tech Lead Reviewer + Senior Engineer pair..."
    "${PYTHON_BIN}" "${SWARM_DISPATCH_SCRIPT}" --from-report "${REPO_ROOT}/logs/hillclimb_latest_report.json"
  fi
  exit "${exit_code}"
}
trap on_failure ERR

echo "=== [1/8] Running Ruff Linter & Formatter on backend/ ==="
CURRENT_STAGE="Tier 1: Ruff Lint & Format"
if [ -f "${BACKEND_DIR}/.venv/bin/ruff" ]; then
  "${BACKEND_DIR}/.venv/bin/ruff" check "${BACKEND_DIR}" --fix
  "${BACKEND_DIR}/.venv/bin/ruff" format "${BACKEND_DIR}"
else
  ruff check "${BACKEND_DIR}" --fix
  ruff format "${BACKEND_DIR}"
fi

echo "=== [2/8] Running Pytest with Coverage Gate (>=80%) ==="
CURRENT_STAGE="Tier 1: Pytest Unit & Coverage Gate"
cd "${BACKEND_DIR}"
if [ -f "${BACKEND_DIR}/.venv/bin/pytest" ]; then
  "${BACKEND_DIR}/.venv/bin/pytest"
else
  pytest
fi

echo "=== [3/8] Verifying Frontend TypeScript & Vite Production Build ==="
CURRENT_STAGE="Tier 1: Frontend Build Verification"
cd "${REPO_ROOT}"
if [ -f "${FRONTEND_DIR}/package.json" ] && command -v npm >/dev/null 2>&1; then
  npm --prefix "${FRONTEND_DIR}" run build
else
  echo "[INFO] Frontend build skipped (npm or frontend/package.json not found)."
fi

echo "=== [4/8] Running Production 80-Pair Evaluation & Regression Suite (evals.runner + evals.analyze) ==="
CURRENT_STAGE="Tier 1: Evals Suite & Regression Analysis"
cd "${REPO_ROOT}"
"${PYTHON_BIN}" -m evals.runner \
  --dataset evals/dataset/benchmark_catalog.evalset.json \
  --output evals/reports/latest_eval_report.json
"${PYTHON_BIN}" -m evals.analyze --current evals/reports/latest_eval_report.json

echo "=== [5/8] Running Disaster Recovery & Chaos Resilience Verification ==="
CURRENT_STAGE="Tier 1: Disaster Recovery & Resilience"
bash "${REPO_ROOT}/skills/hillclimb/scripts/verify_disaster_recovery.sh"

echo "=== [6/8] Checking Live Google Cloud Environment ==="
CURRENT_STAGE="Tier 2: Live Google Cloud Verification"
AUTH_SCRIPT="${REPO_ROOT}/skills/hillclimb/scripts/check_gcloud_auth.sh"
LIVE_SCRIPT="${REPO_ROOT}/skills/hillclimb/scripts/run_live_gcloud_checks.py"

if [ "$LIVE_GCLOUD" = true ]; then
  echo "[ENFORCED] Running mandatory live Google Cloud verification..."
  "${PYTHON_BIN}" "${LIVE_SCRIPT}"
elif bash "${AUTH_SCRIPT}" >/dev/null 2>&1; then
  echo "[DETECTED] Active Google Cloud authentication found. Running live cloud checks..."
  "${PYTHON_BIN}" "${LIVE_SCRIPT}" --allow-unauthenticated
else
  echo "[INFO] Live Google Cloud checks skipped (local hermetic mode). Run with --live-gcloud to enforce."
fi

echo "=== [7/8] Running Selenium UI/UX End-to-End Regression Audit ==="
CURRENT_STAGE="Tier 1: Selenium UI/UX Audit"
UI_AUDIT_SCRIPT="${REPO_ROOT}/skills/selenium-ui-audit/scripts/run_audit.py"
EXPLORATORY_SCRIPT="${REPO_ROOT}/skills/selenium-ui-audit/scripts/exploratory_roamer.py"

if [ "$SKIP_UI" = true ]; then
  echo "[INFO] Selenium UI/UX audit skipped via --skip-ui."
elif [ -f "${UI_AUDIT_SCRIPT}" ]; then
  /usr/local/google/home/williamwlchan/.local/bin/uv run --with selenium python "${UI_AUDIT_SCRIPT}" --output-dir "${REPO_ROOT}/reports/ui-audit"
  echo "[PASS] Selenium UI/UX Regression Audit Passed (0 errors, 0 warnings)."

  if [ "$EXPLORATORY" = true ]; then
    echo "=== Running Autonomous Exploratory UX & Human Behavior Simulation ==="
    /usr/local/google/home/williamwlchan/.local/bin/uv run --with selenium python "${EXPLORATORY_SCRIPT}" --output-dir "${REPO_ROOT}/reports/ui-audit"
  fi
fi

echo "=== [8/8] Running Capstone Rubric Gate & Monotonic High-Water Mark Ratchet ==="
CURRENT_STAGE="Tier 3: Capstone Rubric & Monotonic Ratchet"
AUDIT_SCRIPT="${REPO_ROOT}/skills/rubric-audit/scripts/audit_rubric.py"
if [ "$FRESH_AUDIT" = true ]; then
  echo "[FRESH-AUDIT] Spawning independent Argon reviewer pane in tmux..."
  bash "${REPO_ROOT}/skills/rubric-audit/scripts/launch_unbiased_reviewer.sh" --wait-and-close
fi

"${PYTHON_BIN}" "${AUDIT_SCRIPT}" --verify ${TARGET_FLAG}
echo "[PASS] Capstone Rubric Verification Passed!"

"${PYTHON_BIN}" "${RATCHET_SCRIPT}" --check-and-update

echo "=== ALL HILLCLIMB CHECKS & MONOTONIC RATCHET COMPLETED ==="
