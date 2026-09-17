#!/usr/bin/env bash
# ==============================================================================
# launch_unbiased_reviewer.sh
#
# Automatically spawns an independent, clean-context review pane in tmux
# running Jetski with gemini-3.8-flash and high reasoning effort (--effort high)
# to audit the repository against RUBRIC.md without conversation bias.
# ==============================================================================

set -euo pipefail

PROMPT="Review the codebase against RUBRIC.md using the rubric-audit skill with an unbiased perspective"
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

# Verify tmux environment
if [[ -z "${TMUX:-}" ]]; then
  echo "WARNING: Not running inside tmux session. Executing command in current terminal..."
  exec "$JETSKI_BIN" --model gemini-3.8-flash --effort high -i "$PROMPT"
else
  echo "Spawning independent review pane in tmux with gemini-3.8-flash (--effort high)..."
  PANE_ID=$(tmux split-window -h -P -F "#{pane_id}" "$JETSKI_BIN --model gemini-3.8-flash --effort high")
  echo "Spawned review pane: $PANE_ID"
  sleep 2
  tmux send-keys -t "$PANE_ID" "$PROMPT" C-m
  echo "Prompt sent to reviewer pane $PANE_ID successfully."
fi
