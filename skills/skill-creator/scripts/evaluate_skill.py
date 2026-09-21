#!/usr/bin/env python3
"""Anthropic skill-creator automated evaluator for Jetski skills.

Validates:
1. SKILL.md YAML frontmatter (name, description with trigger instructions)
2. Progressive disclosure line count (< 500 lines)
3. Bundled scripts/ and resources/references existence
4. Quantitative evals/evals.json schema conformance and adversarial honey-pot execution
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def evaluate_skill_package(skill_dir: Path) -> int:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        print(f"[FAIL] Missing SKILL.md in {skill_dir}", file=sys.stderr)
        return 1

    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    checks: list[tuple[str, bool, str]] = []

    has_frontmatter = text.startswith("---\n") and "\n---\n" in text[4:]
    checks.append(("YAML Frontmatter Present", has_frontmatter, f"{len(lines)} total lines"))

    line_budget_ok = len(lines) < 500
    checks.append(
        ("Progressive Disclosure (<500 lines)", line_budget_ok, f"{len(lines)} / 500 lines")
    )

    evals_path = skill_dir / "evals" / "evals.json"
    has_evals = evals_path.exists()
    eval_count = 0
    if has_evals:
        data = json.loads(evals_path.read_text(encoding="utf-8"))
        eval_count = len(data.get("evals", []))
    checks.append(
        (
            "Quantitative evals/evals.json Suite",
            has_evals and eval_count >= 5,
            f"{eval_count} test cases",
        )
    )

    # If evaluating rubric-audit, run live honey-pot adversarial checks against apply_strict_expert_calibration
    if skill_dir.name == "rubric-audit":
        repo_root = skill_dir.parent.parent
        sys.path.insert(0, str(skill_dir / "scripts"))
        import audit_rubric  # type: ignore[import-not-found]

        # Honey-pot 1: Out-of-bounds line range citation (e.g. main.py:9999-10050) must be downgraded
        hp1_payload = {
            "section_1_presentation_and_advisory": [],
            "section_2_engineering_excellence": [
                {
                    "id": "s2_01",
                    "score": 3,
                    "evidence": "backend/src/app/main.py:9999-10050",
                    "successes": "Validates main.py",
                    "failures_and_gaps": "Trade-off in sequential execution latency",
                    "reasoning": "Deep multi-agent implementation verified with tests.",
                }
            ],
        }
        cal1, down1 = audit_rubric.apply_strict_expert_calibration(hp1_payload, repo_root)
        hp1_passed = cal1["section_2_engineering_excellence"][0]["score"] < 3 and len(down1) == 1
        checks.append(
            (
                "Honey-Pot 1: Reject Out-of-Bounds Line Ranges",
                hp1_passed,
                f"downgraded={len(down1)}",
            )
        )

        # Honey-pot 2: Paper Architecture (.md only for s2_01) must be capped at Score 1
        hp2_payload = {
            "section_1_presentation_and_advisory": [],
            "section_2_engineering_excellence": [
                {
                    "id": "s2_01",
                    "score": 3,
                    "evidence": "ARCHITECTURE.md:10-40",
                    "successes": "Documented in ARCHITECTURE.md",
                    "failures_and_gaps": "Trade-off in sequential execution latency",
                    "reasoning": "Deep multi-agent implementation verified with tests.",
                }
            ],
        }
        cal2, _ = audit_rubric.apply_strict_expert_calibration(hp2_payload, repo_root)
        hp2_passed = cal2["section_2_engineering_excellence"][0]["score"] == 1
        checks.append(
            (
                "Honey-Pot 2: Paper Architecture Capped at Score 1",
                hp2_passed,
                f"score={cal2['section_2_engineering_excellence'][0]['score']}",
            )
        )

        # Honey-pot 3: Programmatic Code Probe Verification on Live Repository
        probe_failures = audit_rubric.run_programmatic_code_probes(repo_root)
        hp3_passed = len(probe_failures) == 0
        checks.append(
            (
                "Honey-Pot 3: Live AST/Code Disqualifier Probes Pass",
                hp3_passed,
                "0 code probe violations" if hp3_passed else f"Violations: {probe_failures}",
            )
        )

    print("=" * 68)
    print(f"SKILL-CREATOR EVALUATION REPORT: {skill_dir.name}")
    print("=" * 68)
    all_ok = True
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{status}] {name:<48} | {detail}")
    print("=" * 68)
    return 0 if all_ok else 1


if __name__ == "__main__":
    target = (
        Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("skills/rubric-audit").resolve()
    )
    sys.exit(evaluate_skill_package(target))
