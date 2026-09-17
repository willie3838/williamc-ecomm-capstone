#!/usr/bin/env bash
# Git pre-commit hook / verification script for documentation synchronization.
# Rule: Any change without a doc change fails. Pass NO_DOC=1 or use [no-doc] to bypass.

set -euo pipefail

if [[ "${NO_DOC:-0}" == "1" ]]; then
    echo "[check_docs_sync] Documentation check bypassed via NO_DOC=1."
    exit 0
fi

# Get list of staged files (or HEAD diff if not staged)
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    AGAINST="HEAD"
else
    # Initial commit
    AGAINST="$(git hash-object -t tree /dev/null)"
fi

STAGED_FILES=$(git diff --cached --name-only "$AGAINST")

if [[ -z "$STAGED_FILES" ]]; then
    exit 0
fi

# Check for code changes
CODE_CHANGED=$(echo "$STAGED_FILES" | grep -E '^(backend/src/|frontend/src/|deployment/terraform/|deployment/clouddeploy/|evals/runner\.py|evals/analyze\.py|evals/run_pipeline\.py)' || true)

# Check for doc changes
DOCS_CHANGED=$(echo "$STAGED_FILES" | grep -E '(ARCHITECTURE\.md|SPEC\.md|RUBRIC\.md|AGENTS\.md|backend/AGENTS\.md|frontend/AGENTS\.md|deployment/AGENTS\.md|evals/AGENTS\.md)$' || true)

if [[ -n "$CODE_CHANGED" && -z "$DOCS_CHANGED" ]]; then
    echo "================================================================================"
    echo "ERROR: Documentation synchronization failure!"
    echo "The following code files were modified without any documentation updates:"
    echo "$CODE_CHANGED"
    echo ""
    echo "Strict Policy: Any code change without a doc change fails."
    echo "To resolve, either:"
    echo "  1. Stage updates to ARCHITECTURE.md, SPEC.md, or the relevant AGENTS.md file."
    echo "  2. Explicitly bypass by setting NO_DOC=1:"
    echo "     NO_DOC=1 git commit"
    echo "================================================================================"
    exit 1
fi

exit 0
