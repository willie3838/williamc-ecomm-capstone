#!/usr/bin/env python3
"""Autonomous Swarm Spawner for Tmux & Jetski.

Spawns:
- 1 Tech Lead pane (review & gatekeeper)
- N Senior Engineer panes (one per feature)
Configured with:
- Main-vertical layout (Tech Lead left 50%, Senior Engineers stacked right)
- System prompts tailored with task context
- Jetski running with --dangerously-skip-permissions
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def run_cmd(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run command and return CompletedProcess."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[CMD ERROR] {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
    return result


def slugify(text: str) -> str:
    """Converts a text description into a clean task slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text)[:25].strip("-")


def get_current_tmux_window() -> str:
    """Gets the active tmux window identifier."""
    res = run_cmd(["tmux", "display-message", "-p", "#{session_name}:#{window_index}"])
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError("Not inside a tmux session or tmux is not running.")
    return res.stdout.strip()


def load_template(template_path: Path) -> str:
    """Loads a prompt template from resources."""
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    with open(template_path, "r") as f:
        return f.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Spawn Swarm Development Team in Tmux")
    parser.add_argument(
        "--features",
        nargs="+",
        required=True,
        help="List of feature descriptions (e.g. 'Catalog Filters' 'SKU Citation Fix')",
    )
    parser.add_argument(
        "--issues",
        nargs="*",
        default=[],
        help="Optional corresponding Buganizer issue IDs for each feature",
    )
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=Path(".").resolve(),
        help="Path to the repository root directory",
    )
    parser.add_argument(
        "--new-window",
        action="store_true",
        help="Create a new tmux window named 'swarm' instead of using current window",
    )
    parser.add_argument(
        "--model",
        default="argon",
        help="Jetski LLM model to run across all panes (default: argon; fallback: gemini-3.8-flash-high when quota exhausted)",
    )
    parser.add_argument(
        "--window-target",
        default=None,
        help="Explicit tmux target window (e.g. 'session:window') for automated or background execution",
    )

    args = parser.parse_args()
    repo_dir = args.repo_dir.resolve()
    skill_dir = Path(__file__).resolve().parent.parent
    resources_dir = skill_dir / "resources"

    tl_template = load_template(resources_dir / "tech_lead_prompt.md")
    se_template = load_template(resources_dir / "senior_engineer_prompt.md")

    # Setup .swarm directory in the target repository
    swarm_dir = repo_dir / ".swarm"
    reviews_dir = swarm_dir / "reviews"
    prompts_dir = swarm_dir / "prompts"
    worktrees_dir = swarm_dir / "worktrees"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    # 1. Determine or create Tmux window
    if args.window_target:
        target_window = args.window_target
    elif args.new_window:
        res_win = run_cmd(["tmux", "new-window", "-n", "swarm", "-c", str(repo_dir), "-P", "-F", "#{session_name}:#{window_index}"])
        if res_win.returncode != 0:
            sys.exit(1)
        target_window = res_win.stdout.strip()
    else:
        target_window = get_current_tmux_window()

    print(f"[INFO] Using tmux window: {target_window}")

    # Pane 1: Tech Lead pane (the primary/initial pane of the window)
    res_tl = run_cmd(["tmux", "display-message", "-t", target_window, "-p", "#{pane_id}"])
    tl_pane_id = res_tl.stdout.strip()
    run_cmd(["tmux", "select-pane", "-t", tl_pane_id, "-T", "Tech-Lead"])

    # Build tasks metadata
    tasks_meta = []
    se_panes = []
    previous_pane = tl_pane_id

    # Setup isolated git worktree directory & prune stale references
    run_cmd(["git", "worktree", "prune"], cwd=repo_dir)

    for idx, feature_desc in enumerate(args.features, start=1):
        task_slug = f"task-{idx}-{slugify(feature_desc)}"
        issue_id = args.issues[idx - 1] if idx - 1 < len(args.issues) else None
        branch_name = f"feat/{task_slug}"
        task_worktree_dir = worktrees_dir / task_slug

        # If live Buganizer issue attached, advance stage from ASSIGNED to ACCEPTED
        if issue_id and issue_id not in ("None", "DRY_RUN"):
            issues_cli = "/google/bin/releases/issues-cli/issues"
            run_cmd([issues_cli, "update", "status", "--issue_id", str(issue_id), "--status", "ACCEPTED"])
            run_cmd([issues_cli, "comment", "--issue_id", str(issue_id), "--comment", f"Senior Engineer began implementation for '{feature_desc}'."])

        # Setup isolated git worktree for each Senior Engineer
        if task_worktree_dir.exists():
            run_cmd(["git", "worktree", "remove", "--force", str(task_worktree_dir)], cwd=repo_dir)
        run_cmd(["git", "branch", "-D", branch_name], cwd=repo_dir)
        res_wt = run_cmd(["git", "worktree", "add", "-b", branch_name, str(task_worktree_dir), "main"], cwd=repo_dir)
        if res_wt.returncode != 0:
            print(f"[WARN] Worktree creation warning for {branch_name}: {res_wt.stderr}")

        # Split pane: first SE splits horizontally from TL (creating right column);
        # subsequent SEs split vertically within the right column.
        if idx == 1:
            split_flag = "-h"
            split_target = tl_pane_id
        else:
            split_flag = "-v"
            split_target = previous_pane

        res_split = run_cmd([
            "tmux", "split-window", split_flag, "-t", split_target,
            "-c", str(task_worktree_dir), "-P", "-F", "#{pane_id}"
        ])
        se_pane_id = res_split.stdout.strip()
        previous_pane = se_pane_id
        se_panes.append(se_pane_id)

        # Set clean pane title
        run_cmd(["tmux", "select-pane", "-t", se_pane_id, "-T", f"SeniorEng-{task_slug}"])

        task_entry = {
            "task_id": task_slug,
            "feature": feature_desc,
            "issue_id": issue_id,
            "branch": branch_name,
            "worktree_dir": str(task_worktree_dir),
            "pane_id": se_pane_id,
            "status": "IN_PROGRESS",
            "review_file": str(reviews_dir / f"{task_slug}.md"),
        }
        tasks_meta.append(task_entry)

        # Initialize review file
        review_file = reviews_dir / f"{task_slug}.md"
        with open(review_file, "w") as f:
            f.write(f"""# Code Review: {task_slug} - {feature_desc}

- **Task ID**: `{task_slug}`
- **Feature**: {feature_desc}
- **Buganizer Issue**: `{issue_id or 'None'}`
- **Branch**: `{branch_name}`
- **Senior Engineer Pane**: `{se_pane_id}`
- **Status**: `PROPOSAL_PENDING`

---

## 1. Senior Engineer Architecture Proposal
*(Senior Engineer will document the design, module interfaces, and planned unit tests here)*

---

## 2. Implementation & Test Evidence
*(Senior Engineer will record diff summary, test/linter results, and commit hash here)*

---

## 3. Tech Lead Critique & Decision
*(Tech Lead will record critique or GREEN LIGHT: APPROVED here)*
""")

    # 2. Adjust tmux layout to main-vertical (Tech Lead gets left 50%)
    run_cmd(["tmux", "select-layout", "-t", target_window, "main-vertical"])
    run_cmd(["tmux", "set-window-option", "-t", target_window, "main-pane-width", "50%"])

    # 3. Save swarm state
    state = {
        "target_window": target_window,
        "repo_dir": str(repo_dir),
        "tech_lead": {
            "pane_id": tl_pane_id,
            "prompt_file": str(prompts_dir / "tech_lead_prompt.md"),
        },
        "tasks": tasks_meta,
    }
    with open(swarm_dir / "state.json", "w") as f:
        json.dump(state, f, indent=2)

    # 4. Generate prompts and launch agents
    # Generate Tech Lead prompt
    tl_custom_prompt = tl_template + f"""

---

## 4. CURRENT ACTIVE SWARM ASSIGNMENTS

- **Repository**: `{repo_dir}`
- **Tech Lead Pane**: `{tl_pane_id}`
- **Active Tasks**:
"""
    for t in tasks_meta:
        tl_custom_prompt += (
            f"  * **Task**: `{t['task_id']}` | Feature: {t['feature']} | "
            f"Issue: `{t['issue_id'] or 'None'}` | Branch: `{t['branch']}` | Pane: `{t['pane_id']}`\n"
        )

    tl_prompt_file = prompts_dir / "tech_lead_prompt.md"
    with open(tl_prompt_file, "w") as f:
        f.write(tl_custom_prompt)

    # Launch Tech Lead agent in tl_pane_id
    jetski_bin = "/google/bin/releases/jetski-devs/tools/cli"
    tl_launch_cmd = f'{jetski_bin} --dangerously-skip-permissions --model {args.model} -i "$(cat {tl_prompt_file})"'
    run_cmd(["tmux", "send-keys", "-t", tl_pane_id, tl_launch_cmd, "C-m"])

    # Generate Senior Engineer prompts and launch
    for t in tasks_meta:
        se_custom_prompt = se_template + f"""

---

## 2. YOUR ASSIGNED FEATURE CONTEXT

- **Repository**: `{repo_dir}`
- **Your Isolated Worktree Directory**: `{t['worktree_dir']}`
- **Your Task ID**: `{t['task_id']}`
- **Feature Name**: {t['feature']}
- **Buganizer / Taskflow Issue**: `{t['issue_id'] or 'None'}`
- **Your Target Branch**: `{t['branch']}`
- **Your Pane ID**: `{t['pane_id']}`
- **Tech Lead Pane ID**: `{tl_pane_id}`
- **Shared Review File**: `{t['review_file']}`

### Immediate First Steps:
1. You are ALREADY in your isolated git worktree directory on branch `{t['branch']}`. Do NOT run git checkout on other branches.
2. Open `{t['review_file']}` and write your architecture proposal.
3. Commit and begin your test-driven implementation in your worktree directory.
"""
        se_prompt_file = prompts_dir / f"{t['task_id']}_prompt.md"
        with open(se_prompt_file, "w") as f:
            f.write(se_custom_prompt)

        se_launch_cmd = f'{jetski_bin} --dangerously-skip-permissions --model {args.model} -i "$(cat {se_prompt_file})"'
        run_cmd(["tmux", "send-keys", "-t", t["pane_id"], se_launch_cmd, "C-m"])

    print("\n=== [SWARM DEVELOPMENT SUCCESSFULLY SPAWNED] ===")
    print(f"Tech Lead Pane: {tl_pane_id}")
    for t in tasks_meta:
        print(f"Senior Engineer Pane: {t['pane_id']} -> {t['task_id']} ({t['feature']})")
    print(f"Layout: main-vertical (50% left for Tech Lead)")
    print(f"State saved to: {swarm_dir / 'state.json'}")


if __name__ == "__main__":
    main()
