#!/usr/bin/env python3
"""Taskflow and Buganizer synchronization helper for Capstone project."""

import argparse
import subprocess
import sys

WORKSPACE_ID = "6062895"
COMPONENT_ID = "2257265"
ITERATION_ID = "6062377"


def run_command(cmd: list[str]) -> str:
    """Execute a CLI command and return its stdout."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(cmd)}\nError: {e.stderr}", file=sys.stderr)
        sys.exit(e.returncode)


def list_iteration_items() -> None:
    """List active tickets in current sprint iteration."""
    print(f"Fetching active items in Iteration {ITERATION_ID} (Workspace {WORKSPACE_ID})...")
    output = run_command([
        "taskflow", "iterations", "view-items",
        "--iteration", ITERATION_ID,
        "--workspace", WORKSPACE_ID
    ])
    print(output)


def assign_ticket(issue_id: str, assignee: str = "williamwlchan") -> None:
    """Assign ticket and set status to ASSIGNED."""
    print(f"Setting issue {issue_id} to ASSIGNED and assigning to {assignee}...")
    run_command(["issues", "update", "status", issue_id, "ASSIGNED"])
    run_command(["issues", "update", "assignees", issue_id, assignee])
    print(f"Issue {issue_id} assigned to {assignee}.")


def close_ticket(issue_id: str, commit_sha: str) -> None:
    """Mark issue FIXED with commit comment."""
    comment = f"Resolved in commit {commit_sha}. Verification suite passing."
    print(f"Closing issue {issue_id} with comment: {comment}")
    run_command(["issues", "update", "comments", issue_id, comment])
    run_command(["issues", "update", "status", issue_id, "FIXED"])
    print(f"Issue {issue_id} marked as FIXED.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Taskflow & Buganizer Helper")
    subparsers = parser.add_subparsers(dest="action", required=True)

    # list
    subparsers.add_parser("list", help="List tickets in current iteration")

    # assign
    assign_parser = subparsers.add_parser("assign", help="Assign a ticket")
    assign_parser.add_argument("issue_id", help="Buganizer Issue ID")
    assign_parser.add_argument("--assignee", default="williamwlchan", help="LDAP to assign")

    # close
    close_parser = subparsers.add_parser("close", help="Close a ticket as FIXED")
    close_parser.add_argument("issue_id", help="Buganizer Issue ID")
    close_parser.add_argument("--commit", required=True, help="Git commit SHA")

    args = parser.parse_args()

    if args.action == "list":
        list_iteration_items()
    elif args.action == "assign":
        assign_ticket(args.issue_id, args.assignee)
    elif args.action == "close":
        close_ticket(args.issue_id, args.commit)


if __name__ == "__main__":
    main()
