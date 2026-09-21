# JSON Schemas (`skill-creator`)

This document defines the official Anthropic `skill-creator` JSON schemas (`evals/evals.json`, `history.json`, and `grading.json`).

## `evals/evals.json`

Defines the quantitative and adversarial evaluation test cases for a skill. Located at `evals/evals.json` within the skill directory.

```json
{
  "skill_name": "rubric-audit",
  "evals": [
    {
      "id": 1,
      "name": "reject-out-of-bounds-line-ranges",
      "prompt": "Audit a payload citing non-existent line numbers in an existing file",
      "expected_output": "Downgrades score to 1 due to invalid line range citation",
      "expectations": [
        "Verify line range bounds against actual file line count",
        "Downgrade score when cited lines do not exist"
      ]
    }
  ]
}
```

## Anti-Pattern Warning (`eval_feedback`)

```json
  "eval_feedback": {
    "suggestions": [
      {
        "assertion": "The output includes the file path",
        "reason": "A hallucinated citation or un-enforced dead-code class in the file would also pass"
      }
    ],
    "overall": "Assertions check presence but not correctness."
  }
```
