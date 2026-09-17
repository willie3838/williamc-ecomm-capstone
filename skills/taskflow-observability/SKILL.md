---
name: taskflow-observability
description: Manage Buganizer issues and Taskflow sprint iterations for the Best Buy comparison project (Workspace 6062895, Component 2257265, Iteration 6062377).
---

# Taskflow & Buganizer Project Observability Skill

This skill governs issue tracking, iteration management, and task status synchronization for the **Best Buy Catalog Comparison Agent** project.

## Context Identifiers
- **Taskflow Workspace ID**: `6062895` ("Capstone")
- **Buganizer Component ID**: `2257265` (`Personal issues > williamwlchan`)
- **Active Sprint Iteration**: `6062377` (`Test (Current)`, Hotlist: `8948653`)

---

## Operating Protocol for Agents

Whenever an agent picks up a task, implements code, or resolves a defect:
1. **Pre-Task Check**:
   - Query the active sprint iteration items using the helper:
     ```bash
     python3 skills/taskflow-observability/scripts/task_helper.py list
     ```
   - If starting an unassigned task, claim it:
     ```bash
     python3 skills/taskflow-observability/scripts/task_helper.py assign <ISSUE_ID>
     ```
2. **Creating New Issues**:
   - For bugs, use `resources/bug_template.json`:
     ```bash
     issues create \
       --title "[Ecomm Bug]: <Short description>" \
       --component 2257265 \
       --type BUG \
       --priority P2 \
       --severity S2 \
       --description "<Detailed reproduction and acceptance criteria>"
     taskflow iterations add-items --iteration 6062377 --workspace 6062895 --issues <ISSUE_ID>
     ```
   - For features, use `resources/feature_template.json`.
3. **Closing Completed Work**:
   - Once all unit tests and benchmarks pass, close the issue and link the commit:
     ```bash
     python3 skills/taskflow-observability/scripts/task_helper.py close <ISSUE_ID> --commit $(git rev-parse --short HEAD)
     ```

---

## Direct CLI Commands
```bash
# View active sprint iteration items directly
taskflow iterations view-items --iteration 6062377 --workspace 6062895

# Update issue status
issues update status <ISSUE_ID> ASSIGNED
issues update status <ISSUE_ID> FIXED
```
