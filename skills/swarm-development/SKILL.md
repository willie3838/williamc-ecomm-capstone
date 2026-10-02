---
name: swarm-development
description: >-
  Multi-agent swarm engineering for tmux. Spawns an aggressive Tech Lead reviewer and multiple Senior Engineer implementers across isolated panes with --dangerously-skip-permissions. Enforces architecture reviews, hillclimbing, Buganizer/Taskflow closing, PR merges, and automated pane termination.
---

# Swarm Development Skill (`swarm-development`)

The `swarm-development` skill orchestrates a multi-agent engineering team across tmux panes to design, build, review, and merge features in parallel with zero manual prompt interruptions.

---

## Swarm Architecture & Roles

```mermaid
flowchart LR
    subgraph Tmux Window [Tmux Window: main-vertical Layout]
        direction TB
        subgraph Left [Left 50% Column]
            TL["Tech Lead Agent\n(Aggressive Reviewer & Gatekeeper)\njetski --dangerously-skip-permissions"]
        end
        subgraph Right [Right 50% Column (Stacked)]
            SE1["Senior Engineer 1\n[Feature A / feat/task-1]\njetski --dangerously-skip-permissions"]
            SE2["Senior Engineer 2\n[Feature B / feat/task-2]\njetski --dangerously-skip-permissions"]
            SEN["Senior Engineer N\n[Feature N / feat/task-N]\njetski --dangerously-skip-permissions"]
        end
    end

    SE1 -->|1. Submit Architecture & Tests| Desk[".swarm/reviews/<task>.md"]
    SE2 -->|1. Submit Architecture & Tests| Desk
    SEN -->|1. Submit Architecture & Tests| Desk

    Desk -->|2. Inspect Diffs & Run Evals/Tests| TL
    TL -->|3a. Critique & Request Revisions| Desk
    TL -->|3b. GREEN LIGHT Approval| Action["complete_task.py"]
    Action --> Merge["Merge feat branch into main"]
    Action --> Buganizer["Update Buganizer/Taskflow -> FIXED"]
    Action --> KillPane["tmux kill-pane (Close Senior Eng)"]
```

### 1. The Tech Lead (Reviewer & Gatekeeper)
- **Spawned in**: Primary pane (Left 50% of tmux window).
- **System Prompt**: Loaded from [`resources/tech_lead_prompt.md`](resources/tech_lead_prompt.md).
- **Mandate**: Aggressively review architecture proposals and code implementations. Enforces zero hallucination, strict typing, coverage floors ($\ge 80\%$), and clean linting.
- **Authority**:
  - Issues line-item critique in `.swarm/reviews/<task_id>.md`.
  - Grants the final `GREEN LIGHT: APPROVED`.
  - Atomically merges the feature branch into `main`, updates Buganizer/Taskflow to `FIXED`, and closes the Senior Engineer's tmux pane.

### 2. Senior Engineers (Feature Implementers)
- **Spawned in**: Right column panes (one per feature).
- **System Prompt**: Loaded from [`resources/senior_engineer_prompt.md`](resources/senior_engineer_prompt.md).
- **Mandate**: Implement assigned features to superior technical standards.
- **Workflow**:
  1. Work on isolated branch: `feat/<task_id>`.
  2. Document architecture and test plan in `.swarm/reviews/<task_id>.md`.
  3. Apply test-driven hillclimbing: unit tests first, verify $\ge 80\%$ coverage.
  4. Submit to Tech Lead for review and rapidly iterate on feedback until approved.

---

## How to Spawn a Swarm

### 1. From Terminal / Shell
```bash
python3 skills/swarm-development/scripts/spawn_swarm.py \
  --features "Product Filter Tool" "Cart Recommendation Engine" \
  --issues 225726501 225726502 \
  --repo-dir /usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone
```

### 2. Spawning in a Dedicated Tmux Window with Worktrees
To create the swarm in a fresh new window named `swarm` with isolated git worktrees:
```bash
python3 skills/swarm-development/scripts/spawn_swarm.py \
  --features "Feature A" "Feature B" \
  --model argon \
  --new-window
```
Each Senior Engineer is allocated an isolated directory in `.swarm/worktrees/<task_id>` to eliminate branch-switching collisions and allow fully parallel development.

---

## Model Selection & Quota Fallback Protocol

> [!IMPORTANT]
> **Model Selection Hierarchy**:
> 1. **Primary (Prioritized)**: **Argon** (`--model argon` or `/model Argon`) should always be prioritized across all swarm panes (Tech Lead reviewer and Senior Engineer implementers) when quota is available for deep reasoning, architectural review, and rigorous TDD.
> 2. **Fallback**: **Gemini 3.8 Flash** (`--model gemini-3.8-flash-high` or `/model Gemini 3.8 Flash (High)`) is the designated fallback model whenever Argon individual quota is exhausted or rate-limited (`⚠ Individual quota reached`).
>
> **Handling Quota Exhaustion in Running Panes**:
> If an active tmux pane encounters an Argon quota exhaustion error:
> 1. If the pane is waiting/interrupted (`esc to cancel`), send `Escape` to cancel the blocked call.
> 2. Switch the model to Gemini 3.8 Flash:
>    ```bash
>    tmux send-keys -t <pane_id> "/model Gemini 3.8 Flash (High)" Enter
>    ```
> 3. Verify the status bar shows `Gemini 3.8 Flash · high`.
> 4. Prompt the agent to resume execution if needed (`tmux send-keys -t <pane_id> "continue" Enter`).
>
> When spawning new swarms, if Argon quota is depleted, supply `--model gemini-3.8-flash-high`:
> ```bash
> python3 skills/swarm-development/scripts/spawn_swarm.py \
>   --features "Feature A" "Feature B" \
>   --model gemini-3.8-flash-high \
>   --new-window
> ```

---

## Review & Completion Protocol

### For Tech Lead: Approving & Closing a Feature (GitHub PR + Buganizer)
When a Senior Engineer's branch meets all quality, architecture, and test criteria:
```bash
python3 skills/swarm-development/scripts/complete_task.py \
  --task "<task_id>" \
  --issue "<buganizer_issue_id>" \
  --what "Implemented <concrete changes across files/components>" \
  --why "Resolved <root cause / architectural rationale>" \
  --pane "<senior_eng_pane_id>" \
  --branch "feat/<task_id>" \
  --base "main"
```

This command automatically:
1. Pushes `feat/<task_id>` to `origin`, creates a **GitHub Pull Request** (`gh pr create`) with structured `## What Was Implemented`, `## Why`, and `Fixes b/<issue_id>`, and merges the PR (`gh pr merge --merge --delete-branch`) into `main`.
2. Updates **Buganizer / Taskflow** (`b/<issue_id>`) to status `FIXED` with a comment linking the **GitHub PR URL**, **merge commit hash**, and **What + Why summary**.
3. Updates `.swarm/state.json` with `merge_commit` and `pr_url`.
4. Closes the Senior Engineer's tmux pane via `tmux kill-pane`.
5. **Mandatory Post-Merge CI/CD Monitoring & Auto-Fix**: Immediately after merging to `main`, the Tech Lead MUST monitor the triggered CI/CD run on `main` (`RUN_ID=$(gh run list --branch main --limit 1 --json databaseId -q '.[0].databaseId') && gh run watch "$RUN_ID" --exit-status`). If the CI/CD run fails, the Tech Lead MUST inspect `gh run view "$RUN_ID" --log-failed` and automatically fix, commit, push, and re-verify on `main` until the pipeline turns green.

---

## Key Files & Resources
- [`scripts/spawn_swarm.py`](scripts/spawn_swarm.py): Multi-pane spawner with layout adjustment and prompt injection.
- [`scripts/complete_task.py`](scripts/complete_task.py): Gatekeeper merger, Taskflow updater, and pane closer.
- [`resources/tech_lead_prompt.md`](resources/tech_lead_prompt.md): Injected Tech Lead system prompt.
- [`resources/senior_engineer_prompt.md`](resources/senior_engineer_prompt.md): Injected Senior Engineer system prompt.
- `.swarm/state.json`: Active swarm registry, task statuses, and pane mappings.
- `.swarm/reviews/`: Markdown review files for architecture plans, critique, and approval logs.
