"""Unit tests verifying presence and completeness of evaluation rubrics."""

from pathlib import Path


def test_eval_rubrics_exist_and_populated():
    """Assert all evaluation rubric markdown documents exist and specify criteria."""
    rubrics_dir = Path(__file__).resolve().parent.parent.parent / "evals" / "rubrics"
    assert rubrics_dir.exists(), f"Rubrics directory missing at {rubrics_dir}"

    expected_files = [
        "data_accuracy.md",
        "citation_faithfulness.md",
        "semantic_coherence.md",
        "tool_trajectory.md",
    ]

    for fname in expected_files:
        rubric_file = rubrics_dir / fname
        assert rubric_file.exists(), f"Missing rubric file: {fname}"
        content = rubric_file.read_text(encoding="utf-8")
        assert len(content) > 200, f"Rubric {fname} content too short"

        if fname == "data_accuracy.md":
            assert "0.98" in content or "0.95" in content
            assert "Pricing" in content
            assert "Memory" in content or "Processor" in content

        elif fname == "citation_faithfulness.md":
            assert "0.95" in content or "0.90" in content
            assert "[SKU:" in content

        elif fname == "semantic_coherence.md":
            assert "LLM" in content
            assert "scale" in content.lower() or "score" in content.lower()

        elif fname == "tool_trajectory.md":
            assert "1.00" in content or "0.95" in content
            assert "EXACT" in content
            assert "IN_ORDER" in content
            assert "FUZZY_SEMANTIC" in content
