"""Automated verification test ensuring code changes and documentation remain in lockstep.

Enforces the simple, strict policy:
- ANY change in code without a corresponding documentation change fails.
- To bypass, explicitly pass the '--no-doc' flag to pytest, or set NO_DOC=1 in the environment.
- Statically verifies that key architectural components are documented in ARCHITECTURE.md and backend/AGENTS.md.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_agent_components_documented_in_architecture():
    """Verify all specialist agent classes in multi_agent.py are documented in ARCHITECTURE.md."""
    arch_file = REPO_ROOT / "ARCHITECTURE.md"
    assert arch_file.exists(), f"ARCHITECTURE.md not found at {arch_file}"
    arch_content = arch_file.read_text(encoding="utf-8")

    required_agent_nodes = [
        "QueryIntentAgent",
        "CatalogRetrievalAgent",
        "RelevanceDetectorAgent",
        "SpecComparisonAgent",
        "MultiAgentCoordinator",
    ]

    for node in required_agent_nodes:
        assert node in arch_content, (
            f"Agent node '{node}' is not documented in ARCHITECTURE.md! "
            "Update ARCHITECTURE.md per AGENTS.md Section 5.2."
        )


def test_agent_components_documented_in_backend_agents_guide():
    """Verify all specialist agent classes are documented in backend/AGENTS.md."""
    backend_agents_file = REPO_ROOT / "backend" / "AGENTS.md"
    assert backend_agents_file.exists(), f"backend/AGENTS.md not found at {backend_agents_file}"
    content = backend_agents_file.read_text(encoding="utf-8")

    required_terms = [
        "MultiAgentCoordinator",
        "RelevanceDetectorAgent",
        "multi_agent.py",
    ]

    for term in required_terms:
        assert term in content, (
            f"Term '{term}' is missing from backend/AGENTS.md! "
            "Update backend/AGENTS.md per AGENTS.md Section 4 & 5."
        )


def check_docs_sync(modified_files: list[str], bypass: bool = False) -> tuple[bool, str]:
    """Evaluate whether modified files satisfy the strict documentation synchronization rule.

    Rule: Any code change without a corresponding doc change fails, unless bypass is True.
    """
    if bypass:
        return True, "Bypassed via --no-doc flag or NO_DOC=1"

    code_prefixes = (
        "backend/src/",
        "frontend/src/",
        "deployment/terraform/",
        "deployment/clouddeploy/",
        "evals/runner.py",
        "evals/analyze.py",
        "evals/run_pipeline.py",
    )

    doc_file_patterns = (
        "ARCHITECTURE.md",
        "SPEC.md",
        "RUBRIC.md",
        "AGENTS.md",
        "backend/AGENTS.md",
        "frontend/AGENTS.md",
        "deployment/AGENTS.md",
        "evals/AGENTS.md",
    )

    code_changed = [f for f in modified_files if any(f.startswith(p) for p in code_prefixes)]
    docs_changed = [
        f for f in modified_files if any(f.endswith(d) or f == d for d in doc_file_patterns)
    ]

    if code_changed and not docs_changed:
        err = (
            "Documentation synchronization failure!\n"
            "Code files were modified without any documentation updates:\n"
            + "\n".join(f"  - {c}" for c in code_changed)
            + "\n\nRule: Any change without a doc change fails.\n"
            "To resolve, either:\n"
            "  1. Update the corresponding directory AGENTS.md or ARCHITECTURE.md.\n"
            "  2. Explicitly bypass by passing '--no-doc' to pytest or setting NO_DOC=1."
        )
        return False, err

    return True, "Documentation synchronized or no code files changed"


def test_check_docs_sync_fails_when_code_modified_without_docs():
    """Verify that modifying code without touching docs fails the check."""
    files = ["backend/src/app/main.py"]
    passed, msg = check_docs_sync(files, bypass=False)
    assert not passed
    assert "Documentation synchronization failure!" in msg
    assert "backend/src/app/main.py" in msg


def test_check_docs_sync_passes_when_bypass_flag_set():
    """Verify that passing bypass=True (--no-doc or NO_DOC=1) allows code changes without docs."""
    files = ["backend/src/app/main.py"]
    passed, msg = check_docs_sync(files, bypass=True)
    assert passed
    assert "Bypassed via --no-doc" in msg


def test_check_docs_sync_passes_when_docs_are_updated():
    """Verify that updating both code and docs passes."""
    files = ["backend/src/app/main.py", "backend/AGENTS.md"]
    passed, _ = check_docs_sync(files, bypass=False)
    assert passed


def test_check_docs_sync_passes_when_only_tests_or_non_code_changed():
    """Verify that test or config changes outside core code prefixes do not mandate doc updates."""
    files = ["backend/tests/test_dummy.py", "backend/pyproject.toml"]
    passed, _ = check_docs_sync(files, bypass=False)
    assert passed


def test_any_code_change_requires_doc_change_or_no_doc_flag(pytestconfig):
    """Enforce on actual git working tree: Any code change without a doc change fails, unless --no-doc or NO_DOC=1 is passed."""
    # Check bypass flag via pytest CLI or environment variable
    bypass_flag = False
    try:
        bypass_flag = bool(pytestconfig.getoption("--no-doc"))
    except Exception:
        pass

    env_bypass = os.environ.get("NO_DOC", "").lower() in {"1", "true", "yes"}
    bypass = bypass_flag or env_bypass

    # Inspect git working tree diff
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).splitlines()
    except Exception:
        # If git is unavailable in this environment, skip dynamic diff check
        return

    # Check untracked files
    try:
        untracked = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).splitlines()
        for line in untracked:
            if line.startswith("?? "):
                diff_output.append(line[3:].strip())
    except Exception:
        pass

    if not diff_output:
        return  # Clean working tree

    passed, message = check_docs_sync(diff_output, bypass=bypass)
    if not passed:
        pytest.fail(message)
