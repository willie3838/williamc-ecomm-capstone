# Operational Skills Catalog: Best Buy Catalog Comparison Agent

This directory contains the modular **Agent Skills** for developing, testing, evaluating, deploying, and observing the **Best Buy Catalog Comparison Agent** on Google Cloud Platform (`fde-bestbuy-sandbox-dev-508321`).

Each skill is a self-contained operational unit adhering to the Agent Skill standard:
- **`SKILL.md`**: Instruction runbook with YAML frontmatter (`name`, `description`), execution recipes, and troubleshooting tips.
- **`scripts/`**: Executable automation scripts and helper CLIs.
- **`resources/`**: Templates, JSON payloads, schemas, reference code, and evaluation checklists.

---

## Skills Directory Map

| Skill Name | Path | Description | Included Resources & Scripts |
| :--- | :--- | :--- | :--- |
| **`taskflow-observability`** | [taskflow-observability/](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/skills/taskflow-observability/SKILL.md) | Manage Buganizer issues and Taskflow sprint iterations (Workspace `6062895`, Component `2257265`, Iteration `6062377`). | `scripts/task_helper.py`<br/>`resources/bug_template.json`<br/>`resources/feature_template.json` |
| **`hillclimb`** | [hillclimb/](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/skills/hillclimb/SKILL.md) | Autonomous iterative optimization with Monotonic High-Water Mark Ratchet and Swarm-Driven Remediation (Tech Lead Reviewer + Senior Engineer pair on Argon). | `scripts/run_checks.sh`<br/>`scripts/hillclimb_ratchet.py`<br/>`scripts/dispatch_hillclimb_swarm.py`<br/>`scripts/verify_disaster_recovery.sh`<br/>`resources/eval_criteria.json` |
| **`terraform-deploy`** | [terraform-deploy/](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/skills/terraform-deploy/SKILL.md) | Terraform Infrastructure as Code for BigQuery datasets, tables, IAM roles, and Cloud Run in `fde-bestbuy-sandbox-dev-508321`. | `scripts/tf_run.sh`<br/>`resources/terraform.tfvars.example` |
| **`cloudrun-deploy`** | [cloudrun-deploy/](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/skills/cloudrun-deploy/SKILL.md) | Container builds via Google Cloud Build and zero-downtime Cloud Run service deployment. | `scripts/deploy_service.sh`<br/>`resources/health_probe.sh` |
| **`rubric-audit`** | [rubric-audit/](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/skills/rubric-audit/SKILL.md) | Self-assessment against the 31 FDE Capstone competencies defined in [RUBRIC.md](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/RUBRIC.md). | `scripts/audit_rubric.py`<br/>`resources/rubric_checklist.json` |
| **`swarm-development`** | [swarm-development/](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/skills/swarm-development/SKILL.md) | Multi-agent engineering swarm across tmux panes: Tech Lead reviewer & Senior Engineer implementers with automated Buganizer updates and PR merges. | `scripts/spawn_swarm.py`<br/>`scripts/complete_task.py`<br/>`resources/tech_lead_prompt.md`<br/>`resources/senior_engineer_prompt.md` |
| **`project-creation`** | [project-creation/](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/skills/project-creation/SKILL.md) | End-to-end project creation orchestration in automated vs. manual modes: Spec/Rubric architecture drafting, tmux architect reviewer, Taskflow tickets, swarm execution, and continuous rubric hillclimbing. | `scripts/orchestrate_project.py`<br/>`resources/architecture_reviewer_prompt.md`<br/>`resources/rubric_architecture_rules.json`<br/>`resources/project_tickets_template.json` |

---

## How Agents Use Skills
When an agent or developer needs to perform a specific workflow:
1. Navigate to the relevant skill folder (`cd skills/<skill-name>`).
2. Read `SKILL.md` to load the instructions into context.
3. Execute the provided utility scripts in `scripts/` or reference the configurations in `resources/`.
