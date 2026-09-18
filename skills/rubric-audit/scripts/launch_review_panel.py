#!/usr/bin/env python3
"""Multi-Pane Adversarial FDE Capstone Review Panel Spawner for Tmux.

Spawns 4 specialized review panes in tmux (main-vertical layout):
- Left 45% Column: Panel Chair & Principal FDE Moderator (Panel-Chair)
- Right 55% Stacked Panes:
  1. Panelist 1: Staff AI/ML & Data Systems Architect (Panelist-AI-ML)
  2. Panelist 2: Principal Security, IAM & Cloud Infrastructure Lead (Panelist-Sec-Infra)
  3. Panelist 3: Distinguished SRE, Performance & Commercial CTO/CFO (Panelist-SRE-CTO)

The panelists independently inspect the repository, debate project successes and
failures in `logs/panel_deliberation/discussion_board.md`, submit structured
domain evaluations (`logs/panel_deliberation/panelist_*.json`), and synthesize
an adversarial consensus scorecard via `audit_rubric.py --synthesize-panel`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RESOURCES_DIR = SKILL_DIR / "resources"
PANEL_PROMPTS_PATH = RESOURCES_DIR / "panel_prompts.json"
REPO_ROOT = SKILL_DIR.parent.parent
DELIBERATION_DIR = REPO_ROOT / "logs" / "panel_deliberation"
DISCUSSION_BOARD = DELIBERATION_DIR / "discussion_board.md"
PROMPTS_OUT_DIR = DELIBERATION_DIR / "prompts"
STATE_FILE = DELIBERATION_DIR / "panel_state.json"
MARKER_FILE = REPO_ROOT / "logs" / "audit_complete.marker"
JETSKI_BIN = "/google/bin/releases/jetski-devs/tools/cli"


def run_cmd(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run command and capture output."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def initialize_deliberation_room(repo_root: Path) -> None:
    """Create fresh logs/panel_deliberation workspace and discussion_board.md."""
    DELIBERATION_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_OUT_DIR.mkdir(parents=True, exist_ok=True)
    if MARKER_FILE.exists():
        MARKER_FILE.unlink()

    for old_file in DELIBERATION_DIR.glob("panelist_*.done"):
        old_file.unlink()

    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    board_header = f"""# FDE Capstone Review Panel — Live Deliberation & Debate Ledger

- **Session Started**: {now_utc}
- **Repository**: `{repo_root}`
- **Grading Standard**:
  - **Score 0 (Not Demonstrated)**: Missing or broken implementation.
  - **Score 1 (Awareness)**: Documented in `.md` prose or shallow stub without working implementation/tests.
  - **Score 2 (Competent — Pass)**: Solid, working Field-Ready FDE implementation with happy-path & basic error tests. **(DEFAULT FOR WORKING CODE)**
  - **Score 3 (Proficient / Expert — Strong Pass)**: **RARE.** Requires Staff/Principal-level production depth, anticipated complex failure modes verified by failure-injection/edge-case tests, quantified architectural trade-offs, and zero disqualifiers.

---

## Round 1: Independent Findings (Project Successes vs. Project Failures & Shortcuts)
*(Each Panelist must append their verified project SUCCESSES and FAILURES/GAPS below with exact `file:line` citations)*

---

## Round 2: Cross-Panelist Debate, Challenges & Score Downgrades
*(Panelists and Panel Chair challenge any unsubstantiated Score 3 claims and reconcile disagreements)*

---

## Round 3: Panel Chair Final Verdict & Consensus Summary
*(Panel Chair records final consensus summary before running `audit_rubric.py --synthesize-panel`)*
"""
    DISCUSSION_BOARD.write_text(board_header, encoding="utf-8")


def build_role_prompt(role: dict[str, object], repo_root: Path) -> str:
    """Construct detailed adversarial system prompt for a specific panelist role."""
    role_id = str(role["role_id"])
    persona = str(role["persona"])
    focus_areas = ", ".join(role.get("focus_areas", []))  # type: ignore[arg-type]
    output_file = str(role["output_file"])
    instructions = str(role["instructions"])

    return f"""# FDE CAPSTONE REVIEW PANEL — ROLE ASSIGNMENT: {persona}

You are an adversarial, deeply technical panelist in a multi-pane tmux FDE Capstone Review Panel.
- **Your Role ID**: `{role_id}`
- **Your Persona**: **{persona}**
- **Primary Focus Competencies**: `{focus_areas}`
- **Repository Root**: `{repo_root}`
- **Shared Deliberation Board**: `{DISCUSSION_BOARD}`
- **Your Structured Output JSON**: `{repo_root / output_file}`

## MANDATORY GRADING CALIBRATION (HARSH EXPERT STANDARD)
1. **Default Working Code to Score 2 (Competent)**: If a feature works cleanly and meets basic FDE requirements, score it **2**.
2. **Score 3 (Proficient / Expert) is Reserved for True Mastery**: You may ONLY award a **3** if ALL of the following are verified in the codebase:
   - Deep, modular production implementation (not a stub or paper architecture).
   - Explicit handling and automated test coverage for **complex failure modes** (timeouts, 429s, adversarial prompt injection, partial failures, schema drift).
   - Quantified trade-offs (measured latency, cost math, security blast radius).
   - You STILL identify at least one realistic limitation, operational trade-off, or residual risk in the `"failures_and_gaps"` field (writing `"None"` or `"No gaps"` automatically disqualifies Score 3!).
3. **Paper Architecture Disqualifier**: Any Section 2 (`s2_*`) engineering competency backed ONLY by `.md` documentation (`SPEC.md`, `ARCHITECTURE.md`) without executable `.py`/`.ts`/`.tf`/`.yaml` code and tests MUST be scored **<= 1**.

## YOUR STEP-BY-STEP EXECUTION PROTOCOL
1. Read `skills/rubric-audit/SKILL.md` and `skills/rubric-audit/resources/rubric_checklist.json` (paying close attention to `score_3_expert_criteria` and `score_3_disqualifiers`).
2. Inspect the repository source code, Terraform configs, tests, and evaluation scripts.
3. Append your **Round 1 Position Paper** to `{DISCUSSION_BOARD}` detailing:
   - **Concrete Project Successes** (with `file:line` citations)
   - **Concrete Project Failures, Shortcuts & Edge-Case Gaps** (with `file:line` citations)
   - **Proposed Scores & Challenges** to other panelists.
4. Generate your complete 37-competency JSON evaluation using `python3 skills/rubric-audit/scripts/audit_rubric.py --template` as the base structure, populating every item (`s1_01`..`s1_05` and `s2_01`..`s2_32`) with:
   - `"score"` (0, 1, 2, or 3)
   - `"evidence"` (exact `path/to/file.py:start-end` citations)
   - `"successes"` (specific technical strengths verified)
   - `"failures_and_gaps"` (specific weaknesses, missing edge cases, or trade-offs — NEVER empty or "None")
   - `"reasoning"` (explicit contrast between Score 2 and Score 3 criteria)
5. {instructions}
"""


def spawn_tmux_panel(
    repo_root: Path,
    model: str = "argon",
    new_window: bool = True,
    wait_and_close: bool = False,
    timeout: int = 900,
) -> int:
    """Spawn the 4-pane review panel in tmux and optionally wait for completion."""
    initialize_deliberation_room(repo_root)

    with open(PANEL_PROMPTS_PATH, encoding="utf-8") as f:
        panel_cfg = json.load(f)

    roles: list[dict[str, object]] = panel_cfg.get("roles", [])
    if len(roles) < 4:
        print(
            "Error: panel_prompts.json must define 4 roles (Chair + 3 Panelists).", file=sys.stderr
        )
        return 1

    # Write individual prompt files
    prompt_files: dict[str, Path] = {}
    for role in roles:
        rid = str(role["role_id"])
        pfile = PROMPTS_OUT_DIR / f"{rid}_prompt.md"
        pfile.write_text(build_role_prompt(role, repo_root), encoding="utf-8")
        prompt_files[rid] = pfile

    if not os.environ.get("TMUX"):
        print(
            "WARNING: Not inside an active tmux session. Running Panel Chair in foreground...",
            file=sys.stderr,
        )
        chair_prompt = prompt_files["panel_chair"]
        cmd = [
            JETSKI_BIN,
            "--dangerously-skip-permissions",
            "--model",
            model,
            "-i",
            chair_prompt.read_text(encoding="utf-8"),
        ]
        return subprocess.call(cmd, cwd=repo_root)

    # Create or select tmux window
    if new_window:
        res_win = run_cmd(
            [
                "tmux",
                "new-window",
                "-n",
                "rubric-panel",
                "-c",
                str(repo_root),
                "-P",
                "-F",
                "#{session_name}:#{window_index}",
            ]
        )
        if res_win.returncode != 0:
            print(f"Error creating tmux window: {res_win.stderr}", file=sys.stderr)
            return 1
        target_window = res_win.stdout.strip()
    else:
        res_win = run_cmd(["tmux", "display-message", "-p", "#{session_name}:#{window_index}"])
        target_window = res_win.stdout.strip()

    # Pane 0 (Left column): Panel Chair
    res_chair = run_cmd(["tmux", "display-message", "-t", target_window, "-p", "#{pane_id}"])
    chair_pane_id = res_chair.stdout.strip()
    run_cmd(["tmux", "select-pane", "-t", chair_pane_id, "-T", str(roles[0]["pane_title"])])

    panelist_panes: list[dict[str, str]] = []
    prev_pane = chair_pane_id

    for idx, role in enumerate(roles[1:], start=1):
        split_flag = "-h" if idx == 1 else "-v"
        res_split = run_cmd(
            [
                "tmux",
                "split-window",
                split_flag,
                "-t",
                prev_pane,
                "-c",
                str(repo_root),
                "-P",
                "-F",
                "#{pane_id}",
            ]
        )
        pane_id = res_split.stdout.strip()
        prev_pane = pane_id
        title = str(role["pane_title"])
        run_cmd(["tmux", "select-pane", "-t", pane_id, "-T", title])
        panelist_panes.append(
            {
                "role_id": str(role["role_id"]),
                "pane_id": pane_id,
                "pane_title": title,
                "prompt_file": str(prompt_files[str(role["role_id"])]),
            }
        )

    # Configure main-vertical layout (Panel Chair on left 45%, 3 Panelists stacked on right 55%)
    run_cmd(["tmux", "select-layout", "-t", target_window, "main-vertical"])
    run_cmd(["tmux", "set-window-option", "-t", target_window, "main-pane-width", "45%"])

    state_payload = {
        "target_window": target_window,
        "repo_root": str(repo_root),
        "model": model,
        "discussion_board": str(DISCUSSION_BOARD),
        "panel_chair": {
            "role_id": "panel_chair",
            "pane_id": chair_pane_id,
            "pane_title": str(roles[0]["pane_title"]),
            "prompt_file": str(prompt_files["panel_chair"]),
        },
        "panelists": panelist_panes,
    }
    STATE_FILE.write_text(json.dumps(state_payload, indent=2), encoding="utf-8")

    # Launch all 3 Panelists first so they begin inspecting and writing to discussion_board.md
    for p in panelist_panes:
        launch_cmd = (
            f"{JETSKI_BIN} --dangerously-skip-permissions --model {model} "
            f'-i "$(cat {p["prompt_file"]})"'
        )
        run_cmd(["tmux", "send-keys", "-t", p["pane_id"], launch_cmd, "C-m"])

    # Launch Panel Chair in left pane
    chair_launch_cmd = (
        f"{JETSKI_BIN} --dangerously-skip-permissions --model {model} "
        f'-i "$(cat {prompt_files["panel_chair"]})"'
    )
    run_cmd(["tmux", "send-keys", "-t", chair_pane_id, chair_launch_cmd, "C-m"])

    print("\n============================================================")
    print("   FDE CAPSTONE MULTI-PANE REVIEW PANEL SPAWNED IN TMUX")
    print("============================================================")
    print(f" Tmux Window:       {target_window}")
    print(f" Panel Chair Pane:  {chair_pane_id} ({roles[0]['pane_title']})")
    for p in panelist_panes:
        print(f" Panelist Pane:     {p['pane_id']} ({p['pane_title']})")
    print(f" Deliberation Room: {DISCUSSION_BOARD}")
    print("============================================================\n")

    if wait_and_close:
        print(f"Waiting for multi-pane panel deliberation to finish (timeout: {timeout}s)...")
        elapsed = 0
        interval = 5
        all_pane_ids = [chair_pane_id] + [p["pane_id"] for p in panelist_panes]

        while elapsed < timeout:
            if MARKER_FILE.exists():
                print("Panel deliberation completion marker detected!")
                break
            time.sleep(interval)
            elapsed += interval

        # Run synthesis fallback if panelists wrote JSONs before timeout
        if list(DELIBERATION_DIR.glob("panelist_*.json")):
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "audit_rubric.py"),
                    "--synthesize-panel",
                    str(DELIBERATION_DIR),
                    "--record",
                    str(REPO_ROOT / "logs" / "unbiased_rubric_audit.json"),
                ],
                cwd=repo_root,
                check=False,
            )

        # Clean up spawned panes
        for pid in all_pane_ids:
            run_cmd(["tmux", "kill-pane", "-t", pid])

        if MARKER_FILE.exists():
            MARKER_FILE.unlink()

        subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "audit_rubric.py"), "--summary"],
            cwd=repo_root,
            check=False,
        )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch Multi-Pane Adversarial FDE Capstone Review Panel in Tmux"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Path to repository root",
    )
    parser.add_argument(
        "--model",
        default="argon",
        help="Jetski model for panelist agents (default: argon)",
    )
    parser.add_argument(
        "--current-window",
        action="store_true",
        help="Split panes in current tmux window instead of creating 'rubric-panel' window",
    )
    parser.add_argument(
        "--wait-and-close",
        "-w",
        action="store_true",
        help="Wait for panel deliberation to finish, synthesize scores, and close panes",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=900,
        help="Timeout in seconds when --wait-and-close is enabled",
    )
    args = parser.parse_args()
    return spawn_tmux_panel(
        repo_root=args.repo_root.resolve(),
        model=args.model,
        new_window=not args.current_window,
        wait_and_close=args.wait_and_close,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
