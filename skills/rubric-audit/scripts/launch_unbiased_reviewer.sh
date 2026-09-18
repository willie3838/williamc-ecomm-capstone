#!/usr/bin/env bash
# ==============================================================================
# launch_unbiased_reviewer.sh
#
# Automatically spawns the Multi-Pane Adversarial FDE Review Panel in tmux
# (Panel Chair + Staff AI/ML Architect + Principal Security/Infra Lead +
# Distinguished SRE/CTO/CFO) running Jetski with argon (--model argon).
#
# The panel deliberates in `logs/panel_deliberation/discussion_board.md`
# on the project's concrete successes and failures, then computes and records
# the strict consensus scorecard via `audit_rubric.py --synthesize-panel`.
#
# Options:
#   --wait-and-close    Wait for panel deliberation to finish, close panes, and print summary
#   --timeout <sec>     Maximum wait time in seconds (default: 900)
#   --current-window    Split panes in the current tmux window instead of new window
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/launch_review_panel.py" "$@"
