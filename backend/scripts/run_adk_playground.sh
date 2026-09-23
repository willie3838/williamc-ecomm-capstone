#!/usr/bin/env bash
# ==============================================================================
# run_adk_playground.sh
#
# Launches Google ADK Web Playground for local debugging, interactive agent turns,
# and live visual inspection of agent execution steps and tool invocations.
#
# Usage:
#   ./scripts/run_adk_playground.sh [--port 8000] [--host 127.0.0.1]
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${BACKEND_DIR}"

# Activate virtualenv if present
if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
fi

export PYTHONPATH="${BACKEND_DIR}/src:${PYTHONPATH:-}"

echo "======================================================================"
echo " Starting Google ADK Web Playground"
echo " Target Agent: ${BACKEND_DIR}/src/app/agent"
echo " Root Agent:   catalog_comparison_agent (CatalogAdkRunner)"
echo " Open browser at: http://localhost:8000"
echo " Press Ctrl+C to terminate."
echo "======================================================================"

exec adk web src/app/agent "$@"
