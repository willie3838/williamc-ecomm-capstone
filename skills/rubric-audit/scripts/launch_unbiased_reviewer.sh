#!/usr/bin/env bash
# ==============================================================================
# launch_unbiased_reviewer.sh
#
# Automatically spawns an independent, clean-context review pane in tmux
# running Jetski with gemini-3.8-flash and high reasoning effort (--effort high)
# to audit the repository against RUBRIC.md without conversation bias.
#
# Options:
#   --wait-and-close    Wait for audit completion, close the pane, and print summary
#   --timeout <sec>     Maximum wait time in seconds (default: 900)
# ==============================================================================

set -euo pipefail

WAIT_AND_CLOSE=false
TIMEOUT=900

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wait-and-close|-w)
      WAIT_AND_CLOSE=true
      shift
      ;;
    --timeout|-t)
      TIMEOUT="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

MARKER_FILE="logs/audit_complete.marker"
PROMPT="Review the codebase against RUBRIC.md using the rubric-audit skill with an unbiased perspective. Record findings to logs/unbiased_rubric_audit.json, run 'python3 skills/rubric-audit/scripts/audit_rubric.py --record logs/unbiased_rubric_audit.json', and when completely finished, run 'touch logs/audit_complete.marker'."
JETSKI_BIN="/google/bin/releases/jetski-devs/tools/cli"

# Check if Jetski binary exists
if [[ ! -x "$JETSKI_BIN" ]]; then
  if command -v jetski >/dev/null 2>&1; then
    JETSKI_BIN="jetski"
  else
    echo "ERROR: Jetski binary not found at $JETSKI_BIN or in PATH." >&2
    exit 1
  fi
fi

# Clean previous marker
mkdir -p logs
rm -f "$MARKER_FILE"

# Verify tmux environment
if [[ -z "${TMUX:-}" ]]; then
  echo "WARNING: Not running inside tmux session. Executing command in current terminal..."
  exec "$JETSKI_BIN" --model gemini-3.8-flash --effort high -i "$PROMPT"
fi

echo "Spawning independent review pane in tmux with gemini-3.8-flash (--effort high)..."
PANE_ID=$(tmux split-window -h -P -F "#{pane_id}" "$JETSKI_BIN --model gemini-3.8-flash --effort high -i \"$PROMPT\"")
echo "Spawned review pane: $PANE_ID with initial prompt."

if [[ "$WAIT_AND_CLOSE" == "true" ]]; then
  echo "Waiting for reviewer pane $PANE_ID to complete audit (marker: $MARKER_FILE, timeout: ${TIMEOUT}s)..."
  ELAPSED=0
  SLEEP_INTERVAL=5

  while [[ $ELAPSED -lt $TIMEOUT ]]; do
    if [[ -f "$MARKER_FILE" ]]; then
      echo "Audit completion marker detected!"
      break
    fi

    # Check if pane was manually killed or exited
    if ! tmux list-panes -a -F "#{pane_id}" | grep -q "^${PANE_ID}$"; then
      echo "Reviewer pane $PANE_ID has already exited."
      break
    fi

    sleep "$SLEEP_INTERVAL"
    ELAPSED=$((ELAPSED + SLEEP_INTERVAL))
  done

  if [[ ! -f "$MARKER_FILE" ]] && tmux list-panes -a -F "#{pane_id}" | grep -q "^${PANE_ID}$"; then
    echo "WARNING: Reviewer pane timed out after ${TIMEOUT}s before creating $MARKER_FILE."
  fi

  # Clean up review pane
  if tmux list-panes -a -F "#{pane_id}" | grep -q "^${PANE_ID}$"; then
    echo "Closing reviewer pane $PANE_ID..."
    tmux kill-pane -t "$PANE_ID" || true
  fi

  rm -f "$MARKER_FILE"

  echo ""
  echo "============================================================"
  echo "       INDEPENDENT REVIEW COMPLETE - SUMMARY REPORT"
  echo "============================================================"
  python3 skills/rubric-audit/scripts/audit_rubric.py --summary
fi
