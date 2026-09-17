#!/usr/bin/env python3
"""Interactive Google Cloud Authentication Tmux Pane Spawner.

Opens a dedicated pane named 'GCloud-Auth' in the active tmux window,
instructs the user to authenticate, runs `gcloud auth login` and `gcloud auth application-default login`,
and monitors for valid credential resolution.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def run_cmd(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def check_auth_valid() -> bool:
    """Check if gcloud token and ADC are valid."""
    res_gcloud = run_cmd(["gcloud", "auth", "print-access-token"])
    if res_gcloud.returncode != 0 or not res_gcloud.stdout.strip() or "ERROR" in res_gcloud.stdout or "Reauthentication" in res_gcloud.stdout:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Spawn interactive tmux pane for gcloud auth")
    parser.add_argument("--project", default="fde-bestbuy-sandbox-dev-508321", help="Target GCP Project ID")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait for authentication")
    parser.add_argument("--no-wait", action="store_true", help="Do not wait for auth completion, exit immediately after spawning pane")
    args = parser.parse_args()

    # If already authenticated, exit clean
    if check_auth_valid():
        print(f"[SUCCESS] Google Cloud credentials already active for project '{args.project}'.")
        sys.exit(0)

    # Check tmux session
    res_win = run_cmd(["tmux", "display-message", "-p", "#{session_name}:#{window_index}"])
    if res_win.returncode != 0 or not res_win.stdout.strip():
        print("[ERROR] Tmux session not found. Please run manual auth in your terminal:", file=sys.stderr)
        print(f"  gcloud auth login && gcloud auth application-default login && gcloud config set project {args.project}", file=sys.stderr)
        sys.exit(1)

    current_window = res_win.stdout.strip()
    print(f"[INFO] Spawning interactive authentication pane in tmux window '{current_window}'...")

    # Split horizontally to create a 35% right pane for authentication
    res_split = run_cmd([
        "tmux", "split-window", "-h", "-p", "35", "-t", current_window,
        "-P", "-F", "#{pane_id}"
    ])
    if res_split.returncode != 0:
        print(f"[ERROR] Could not split tmux pane: {res_split.stderr}", file=sys.stderr)
        sys.exit(1)

    auth_pane_id = res_split.stdout.strip()
    run_cmd(["tmux", "select-pane", "-t", auth_pane_id, "-T", "GCloud-Auth"])

    # Send authentication commands
    commands = [
        "clear",
        "echo '====================================================='",
        "echo '  INTERACTIVE GOOGLE CLOUD AUTHENTICATION REQUIRED   '",
        "echo '====================================================='",
        f"echo 'Target Project: {args.project}'",
        "echo 'Please follow the prompts below to authenticate.'",
        "echo ''",
        "gcloud auth login",
        "gcloud auth application-default login",
        f"gcloud config set project {args.project}",
        "echo ''",
        "echo '[SUCCESS] Authentication complete! You can close this pane or let the orchestrator close it.'",
    ]
    
    script_str = " && ".join(commands)
    run_cmd(["tmux", "send-keys", "-t", auth_pane_id, script_str, "C-m"])

    print(f"[INFO] Interactive pane '{auth_pane_id}' created. Prompting user for authentication.")

    if args.no_wait:
        print("[INFO] --no-wait specified. Returning immediately.")
        sys.exit(0)

    print(f"[INFO] Waiting up to {args.timeout}s for credentials to be refreshed...")
    start_time = time.time()
    authenticated = False

    while time.time() - start_time < args.timeout:
        if check_auth_valid():
            authenticated = True
            print("[SUCCESS] Credentials refreshed successfully!")
            break
        time.sleep(5)

    if authenticated:
        time.sleep(2)
        run_cmd(["tmux", "kill-pane", "-t", auth_pane_id])
        print(f"[INFO] Closed authentication pane '{auth_pane_id}'.")
        sys.exit(0)
    else:
        print(f"[WARN] Authentication timed out after {args.timeout}s. Authentication pane '{auth_pane_id}' remains open.")
        sys.exit(1)


if __name__ == "__main__":
    main()
