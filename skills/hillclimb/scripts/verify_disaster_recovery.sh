#!/usr/bin/env bash
# Automated Disaster Recovery & Failure Mode Verification Script
# Verifies system resilience, circuit breakers, data quarantine, and health restoration.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
PYTHON_BIN="python3"
if [ -f "${BACKEND_DIR}/.venv/bin/python3" ]; then
  PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python3"
fi

echo "============================================================"
echo "    DISASTER RECOVERY & FAILURE RESILIENCE VERIFICATION"
echo "============================================================"

# Step 1: Run comprehensive failure injection unit tests
echo "[DR Check 1/3] Executing Chaos & Failure Injection Test Suite..."
cd "${BACKEND_DIR}"
"${PYTHON_BIN}" -m pytest tests/test_failure_injection.py --no-cov -v

# Step 2: Test health probes and configuration resilience
echo "[DR Check 2/3] Verifying Health Probe Restoration & Liveness..."
"${PYTHON_BIN}" -m pytest tests/test_health.py --no-cov -v

# Step 3: Verify hermetic recovery under catastrophic failure simulation
echo "[DR Check 3/3] Simulating Catastrophic Dependency Outage & Recovery Cycle..."
"${PYTHON_BIN}" "${REPO_ROOT}/skills/hillclimb/scripts/run_dr_simulation.py"

echo "============================================================"
echo " [PASS] ALL DISASTER RECOVERY & RESILIENCE VERIFICATIONS PASSED"
echo "============================================================"
