---
name: rubric-audit
description: Universal, project-agnostic audit engine that dynamically explores any repository to verify compliance against all 37 FDE Capstone competencies in RUBRIC.md, evaluating every sub-criteria with detailed reasoning and historical progression logging.
---

# Universal Capstone Rubric Audit Skill

This skill provides an automated, structured, and project-agnostic audit engine to verify codebase and architecture compliance against all 37 competencies defined in [RUBRIC.md](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/RUBRIC.md).

It features:
1. **Dynamic Project Exploration (Zero Hardcoded Paths)**: Automatically discovers project structure, programming languages (Python, TypeScript, Go), infrastructure as code (Terraform, Docker), CI/CD pipelines (Cloud Build, GitHub Actions), test suites, and documentation across any repository.
2. **Exhaustive Sub-Criteria Verification**: Every single competency (5 in Section 1, 32 across 7 categories in Section 2) is evaluated against concrete code patterns, AST declarations, configuration files, and documentation.
3. **Score 3 (Proficient) Enforcement**: Verifies whether implementations meet the production-grade standard required for a Score of 3, outputting actionable remediation steps for any competency below 3.
4. **Historical Progression Tracking**: Automatically maintains a timeline of audit runs and score evolution in [`logs/rubric_audit_history.md`](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/logs/rubric_audit_history.md).

---

## Scoring Scale
- **`0`**: Not Demonstrated (Growth Opportunity)
- **`1`**: Awareness (Needs Additional Coaching)
- **`2`**: Competent (Pass & Field-Ready)
- **`3`**: Proficient (Strong Pass & Production-Grade)

**Passing Threshold**: Minimum average score $\ge 2.00$ in both Section 1 (Presentation & Advisory Rigor) and Section 2 (Engineering Excellence), with zero `0` scores.

---

## Operating Protocol

### 1. View Summary Scorecard & Update History Log
Runs the audit, prints the high-level summary, and automatically logs the progression entry to `logs/rubric_audit_history.md`:
```bash
python3 skills/rubric-audit/scripts/audit_rubric.py --summary
```

### 2. Verify Score 3 (Proficient) Standard with Itemized Proof Trace
Audits every single sub-criteria and verifies that all 37 competencies achieve Score 3:
```bash
python3 skills/rubric-audit/scripts/audit_rubric.py --detailed --target-score 3
```

### 3. Audit Any Project or Target Repository
Point the auditor to an external project root via `--repo-path`:
```bash
python3 skills/rubric-audit/scripts/audit_rubric.py --repo-path /path/to/other-project --summary
```

### 4. Generate Standalone Markdown Report
Exports a point-in-time evaluation report to an output file:
```bash
python3 skills/rubric-audit/scripts/audit_rubric.py --output rubric_evaluation.md
```

### 5. Custom Log Destination / Dry Run
```bash
# Log to a custom historical file
python3 skills/rubric-audit/scripts/audit_rubric.py --log-file custom_logs/history.md

# Run without appending to the history log
python3 skills/rubric-audit/scripts/audit_rubric.py --no-log
```

---

## Historical Progression Log
The audit runner writes to [`logs/rubric_audit_history.md`](file:///usr/local/google/home/williamwlchan/Playground/williamc-ecomm-capstone/logs/rubric_audit_history.md). This file contains:
- An updated **Historical Progression Timeline Table** tracking timestamp, git commit SHA, branch, section averages, and milestones.
- Chronological **Audit Snapshots** preserving the itemized scores, evidence, and detailed reasoning for each audit execution over time.
