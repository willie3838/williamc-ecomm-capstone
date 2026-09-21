---
name: skill-creator
description: Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
---

# Skill Creator (Anthropic Reference Skill for Jetski)

A skill for creating new skills and iteratively improving them with quantitative assertions (`evals/evals.json`) and blind evaluation loops.

At a high level, the process of creating or evaluating a skill goes like this:

1. **Capture Intent & Progressive Disclosure Structure**:
   - `SKILL.md` frontmatter (`name` and `description` with explicit "when to trigger" contexts).
   - Keep `SKILL.md` concise (<500 lines) and delegate detailed schemas/checklists to `references/` and deterministic enforcement to `scripts/`.
2. **Draft Quantitative & Adversarial Test Cases (`evals/evals.json`)**:
   - Skills with objectively verifiable outputs (such as `rubric-audit` or code verification skills) MUST define `evals/evals.json` with realistic and adversarial test cases.
   - Avoid the **"Assertions check presence but not correctness"** anti-pattern (`references/schemas.md`): assertions must verify functional correctness, AST/code semantics, line-range validity, and seeded failure-mode detection rather than mere string/file existence.
3. **Run `scripts/evaluate_skill.py <skill-dir>`**:
   - Validates `SKILL.md` frontmatter, line budget (<500 lines), progressive disclosure references (`scripts/`, `references/`), and `evals/evals.json` assertion pass rate (`100%` required).

## Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions (<500 lines)
├── evals/
│   └── evals.json - Quantitative & adversarial test cases verifying the skill
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── resources/  - Checklists, templates, or schemas
```

## Evaluating a Skill with `evaluate_skill.py`

```bash
python3 skills/skill-creator/scripts/evaluate_skill.py skills/rubric-audit
```
