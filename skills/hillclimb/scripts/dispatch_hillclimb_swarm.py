#!/usr/bin/env python3
"""Swarm-Driven Remediation Dispatcher for Autonomous Hillclimbing.

Ensures that every solution or bugfix implemented during a hillclimbing loop
is executed via the `swarm-development` skill (`spawn_swarm.py --model argon`),
pairing an adversarial **Tech Lead Reviewer** with a **Senior Engineer Developer**
in an isolated git worktree (`.swarm/worktrees/<task_id>`).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent
SWARM_SPAWN_SCRIPT = REPO_ROOT / "skills" / "swarm-development" / "scripts" / "spawn_swarm.py"
DEFAULT_REPORT = REPO_ROOT / "logs" / "hillclimb_latest_report.json"


def extract_features_from_report(report_path: Path) -> list[str]:
    """Derive actionable swarm feature tasks from a failed hillclimb report."""
    if not report_path.exists():
        return []
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    regressions = data.get("regressions", [])
    features: list[str] = []
    for idx, reg in enumerate(regressions[:4], start=1):
        clean_desc = str(reg).replace('"', "'").strip()
        features.append(f"Hillclimb Fix {idx}: {clean_desc}")

    if not features and data.get("failed_stage"):
        features.append(f"Hillclimb Fix: Remediate {data['failed_stage']}")

    return features


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dispatch a Tech Lead Reviewer + Senior Engineer Developer swarm pair (Argon) for hillclimb remediation"
    )
    parser.add_argument(
        "--features",
        nargs="+",
        default=[],
        help="Explicit list of hillclimb remediation tasks/features to implement",
    )
    parser.add_argument(
        "--issues",
        nargs="*",
        default=[],
        help="Corresponding Buganizer/Taskflow issue IDs",
    )
    parser.add_argument(
        "--from-report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to hillclimb_latest_report.json to auto-extract failed checks",
    )
    parser.add_argument(
        "--model",
        default="argon",
        help="Jetski CLI model for the Tech Lead Reviewer and Senior Engineer panes (default: argon)",
    )
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=REPO_ROOT,
        help="Path to repository root",
    )
    parser.add_argument(
        "--new-window",
        action="store_true",
        help="Spawn the Reviewer + Developer swarm in a dedicated tmux window named 'swarm'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the swarm-development invocation without spawning live tmux panes",
    )
    args = parser.parse_args()

    features = list(args.features)
    if not features:
        features = extract_features_from_report(args.from_report)

    if not features:
        print(
            "[INFO] No regressions or explicit --features found to dispatch. "
            "Pass --features '<Task Description>' to launch a Reviewer + Developer pair."
        )
        return 0

    if not SWARM_SPAWN_SCRIPT.exists():
        print(f"[ERROR] Swarm spawn script not found at {SWARM_SPAWN_SCRIPT}", file=sys.stderr)
        return 1

    issues = list(args.issues)
    while len(issues) < len(features):
        issues.append(f"2257265{len(issues) + 1:02d}")

    cmd = [
        sys.executable,
        str(SWARM_SPAWN_SCRIPT),
        "--repo-dir",
        str(args.repo_dir.resolve()),
        "--model",
        args.model,
        "--features",
        *features,
        "--issues",
        *issues,
    ]
    if args.new_window:
        cmd.append("--new-window")

    print("=" * 76)
    print("🐝 DISPATCHING HILLCLIMB SWARM (TECH LEAD REVIEWER + SENIOR ENGINEER PAIR)")
    print("=" * 76)
    print(f"  Model               : {args.model}")
    print(f"  Repository Root     : {args.repo_dir.resolve()}")
    print("  Roles Spawned       : 1x Tech Lead Reviewer + Senior Engineer Implementer(s)")
    print("  Tasks to Remediate  :")
    for f, iss in zip(features, issues):
        print(f"    - [{iss}] {f}")
    print("-" * 76)
    print("  Command             : " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    print("=" * 76)

    if args.dry_run:
        print("[DRY-RUN] Verified swarm dispatch command without spawning tmux panes.")
        return 0

    proc = subprocess.run(cmd, check=False)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
