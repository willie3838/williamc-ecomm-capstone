"""Deterministic and semantic tool trajectory grader for Google ADK agents."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from contextvars import ContextVar
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class MatchType(StrEnum):
    """Supported match strategies for evaluating agent tool trajectories."""

    EXACT = "EXACT"
    IN_ORDER = "IN_ORDER"
    ANY_ORDER = "ANY_ORDER"
    FUZZY_SEMANTIC = "FUZZY_SEMANTIC"


class ToolCallRecord(BaseModel):
    """Record of a tool invocation made or expected during an evaluation turn."""

    model_config = ConfigDict(frozen=True)

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None
    execution_time_seconds: float | None = None

    def normalized_name(self) -> str:
        """Normalized tool name."""
        return self.name.strip().lower()

    def normalized_keywords(self) -> list[str]:
        """Extract and clean keywords from args if present."""
        raw = self.args.get("keywords")
        if isinstance(raw, list):
            return [str(k).strip() for k in raw if str(k).strip()]
        if isinstance(raw, str):
            return [raw.strip()]
        return []

    def category_normalized(self) -> str | None:
        """Extract category string in lowercase."""
        cat = self.args.get("category")
        return str(cat).strip().lower() if cat is not None else None

    @classmethod
    def from_adk_invocation(cls, invocation: Any) -> list[ToolCallRecord]:
        """Extract list of ToolCallRecord from an ADK Invocation object or dictionary."""
        records: list[ToolCallRecord] = []
        if invocation is None:
            return records

        intermediate_data = getattr(invocation, "intermediate_data", None)
        if intermediate_data is None and isinstance(invocation, dict):
            intermediate_data = invocation.get("intermediate_data")

        if intermediate_data is None:
            return records

        tool_uses = getattr(intermediate_data, "tool_uses", None)
        if tool_uses is None and isinstance(intermediate_data, dict):
            tool_uses = intermediate_data.get("tool_uses", [])

        if not tool_uses:
            return records

        for tu in tool_uses:
            if isinstance(tu, dict):
                records.append(
                    cls(
                        name=tu.get("name", ""),
                        args=tu.get("args", {}),
                        call_id=tu.get("id"),
                    )
                )
            else:
                name = getattr(tu, "name", "")
                args = getattr(tu, "args", {})
                call_id = getattr(tu, "id", None)
                records.append(
                    cls(
                        name=name,
                        args=dict(args) if isinstance(args, dict) else {},
                        call_id=call_id,
                    )
                )
        return records


class TrajectoryCriterion(BaseModel):
    """Evaluation criteria and thresholds for trajectory scoring."""

    threshold: float = 1.0
    match_type: MatchType = MatchType.EXACT
    ignore_args: bool = False
    allowed_extra_tools: list[str] = Field(default_factory=list)
    keyword_overlap_threshold: float = 0.5


class TrajectoryDiagnosis(BaseModel):
    """Detailed structural diagnosis explaining trajectory grading results."""

    matched_calls: list[tuple[str, str]] = Field(default_factory=list)
    unmatched_expected: list[str] = Field(default_factory=list)
    unexpected_calls: list[str] = Field(default_factory=list)
    parameter_mismatches: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str = ""


class TrajectoryResult(BaseModel):
    """Outcome of grading a tool trajectory."""

    score: float
    passed: bool
    match_type: MatchType
    actual_tool_count: int
    expected_tool_count: int
    diagnosis: TrajectoryDiagnosis


# Context-local active recorder storage for concurrent-safe recording
_active_recorder: ContextVar[TrajectoryRecorder | None] = ContextVar(
    "active_recorder", default=None
)


class TrajectoryRecorder:
    """Dynamic tracker for recording tool calls during an orchestrator or agent run."""

    def __init__(self) -> None:
        self._records: list[ToolCallRecord] = []
        self._token = None

    def record_call(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        call_id: str | None = None,
        execution_time_seconds: float | None = None,
    ) -> None:
        """Append a tool call record to this recording session."""
        self._records.append(
            ToolCallRecord(
                name=name,
                args=args or {},
                call_id=call_id,
                execution_time_seconds=execution_time_seconds,
            )
        )

    def get_records(self) -> list[ToolCallRecord]:
        """Return a shallow copy of the recorded tool calls."""
        return list(self._records)

    def clear(self) -> None:
        """Clear recorded tool calls."""
        self._records.clear()

    def __enter__(self) -> TrajectoryRecorder:
        self._token = _active_recorder.set(self)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._token:
            _active_recorder.reset(self._token)
            self._token = None

    @classmethod
    def get_current(cls) -> TrajectoryRecorder | None:
        """Get active recorder from context."""
        return _active_recorder.get()


class TrajectoryGrader:
    """Grader engine assessing tool trajectories against golden expectations."""

    def __init__(self, default_match_type: MatchType = MatchType.EXACT) -> None:
        self.default_match_type = default_match_type

    def grade(
        self,
        actual: Sequence[ToolCallRecord],
        expected: Sequence[ToolCallRecord],
        criterion: TrajectoryCriterion | None = None,
        match_type: MatchType | None = None,
    ) -> TrajectoryResult:
        """Grade actual tool call records against expected records."""
        effective_match = match_type or (
            criterion.match_type if criterion else self.default_match_type
        )
        effective_criterion = criterion or TrajectoryCriterion(match_type=effective_match)

        # Edge case: both empty
        if len(actual) == 0 and len(expected) == 0:
            return TrajectoryResult(
                score=1.0,
                passed=True,
                match_type=effective_match,
                actual_tool_count=0,
                expected_tool_count=0,
                diagnosis=TrajectoryDiagnosis(
                    explanation="Zero tool calls expected and zero tool calls executed."
                ),
            )

        # Edge case: expected empty but actual made calls
        if len(expected) == 0 and len(actual) > 0:
            unexpected = [f"{a.name}({a.args})" for a in actual]
            return TrajectoryResult(
                score=0.0,
                passed=False,
                match_type=effective_match,
                actual_tool_count=len(actual),
                expected_tool_count=0,
                diagnosis=TrajectoryDiagnosis(
                    unexpected_calls=unexpected,
                    explanation=f"Expected 0 tool calls, but agent executed {len(actual)} unexpected calls.",
                ),
            )

        # Edge case: expected calls but actual empty
        if len(expected) > 0 and len(actual) == 0:
            unmatched = [f"{e.name}({e.args})" for e in expected]
            return TrajectoryResult(
                score=0.0,
                passed=False,
                match_type=effective_match,
                actual_tool_count=0,
                expected_tool_count=len(expected),
                diagnosis=TrajectoryDiagnosis(
                    unmatched_expected=unmatched,
                    explanation=f"Agent omitted all {len(expected)} expected tool calls.",
                ),
            )

        # Dispatch to specific match logic
        if effective_match == MatchType.EXACT:
            return self._grade_exact(actual, expected, effective_criterion)
        elif effective_match == MatchType.IN_ORDER:
            return self._grade_in_order(actual, expected, effective_criterion)
        elif effective_match == MatchType.ANY_ORDER:
            return self._grade_any_order(actual, expected, effective_criterion)
        elif effective_match == MatchType.FUZZY_SEMANTIC:
            return self._grade_fuzzy_semantic(actual, expected, effective_criterion)
        else:
            raise ValueError(f"Unsupported match type: {effective_match}")

    def _match_arguments_exact(
        self, actual_args: dict[str, Any], expected_args: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Check if arguments match exactly. Returns list of mismatches if any."""
        mismatches: list[dict[str, Any]] = []

        all_keys = set(actual_args.keys()) | set(expected_args.keys())
        for k in all_keys:
            v_act = actual_args.get(k)
            v_exp = expected_args.get(k)

            # Ignore None vs missing
            if v_act is None and v_exp is None:
                continue

            # Case-insensitive comparison for strings
            if isinstance(v_act, str) and isinstance(v_exp, str):
                if v_act.strip().lower() != v_exp.strip().lower():
                    mismatches.append({"field": k, "actual": v_act, "expected": v_exp})
                continue

            # Set comparison for lists of strings
            if isinstance(v_act, list) and isinstance(v_exp, list):
                s_act = {str(item).strip().lower() for item in v_act}
                s_exp = {str(item).strip().lower() for item in v_exp}
                if s_act != s_exp:
                    mismatches.append({"field": k, "actual": v_act, "expected": v_exp})
                continue

            if v_act != v_exp:
                mismatches.append({"field": k, "actual": v_act, "expected": v_exp})

        return mismatches

    def _grade_exact(
        self,
        actual: Sequence[ToolCallRecord],
        expected: Sequence[ToolCallRecord],
        criterion: TrajectoryCriterion,
    ) -> TrajectoryResult:
        """Grade using strict 1:1 sequential exact matching."""
        matched: list[tuple[str, str]] = []
        unmatched_expected: list[str] = []
        unexpected_calls: list[str] = []
        param_mismatches: list[dict[str, Any]] = []

        if len(actual) != len(expected):
            # Length difference means exact match failure
            if len(actual) > len(expected):
                unexpected_calls = [f"{a.name}({a.args})" for a in actual[len(expected) :]]
            else:
                unmatched_expected = [f"{e.name}({e.args})" for e in expected[len(actual) :]]

        min_len = min(len(actual), len(expected))
        matched_count = 0

        for i in range(min_len):
            act = actual[i]
            exp = expected[i]

            if act.normalized_name() != exp.normalized_name():
                unexpected_calls.append(f"{act.name}({act.args})")
                unmatched_expected.append(f"{exp.name}({exp.args})")
                continue

            if not criterion.ignore_args:
                mismatches = self._match_arguments_exact(act.args, exp.args)
                if mismatches:
                    param_mismatches.extend(mismatches)
                    continue

            matched.append((act.name, exp.name))
            matched_count += 1

        total_target = max(len(actual), len(expected))
        score = matched_count / total_target if total_target > 0 else 1.0
        passed = (
            score >= criterion.threshold
            and len(param_mismatches) == 0
            and len(unexpected_calls) == 0
        )

        explanation = (
            f"Exact match score: {score:.2f} ({matched_count}/{total_target} calls matched). "
            f"Mismatches: {len(param_mismatches)}, Unexpected: {len(unexpected_calls)}, Missing: {len(unmatched_expected)}."
        )

        return TrajectoryResult(
            score=score,
            passed=passed,
            match_type=MatchType.EXACT,
            actual_tool_count=len(actual),
            expected_tool_count=len(expected),
            diagnosis=TrajectoryDiagnosis(
                matched_calls=matched,
                unmatched_expected=unmatched_expected,
                unexpected_calls=unexpected_calls,
                parameter_mismatches=param_mismatches,
                explanation=explanation,
            ),
        )

    def _grade_in_order(
        self,
        actual: Sequence[ToolCallRecord],
        expected: Sequence[ToolCallRecord],
        criterion: TrajectoryCriterion,
    ) -> TrajectoryResult:
        """Grade checking if expected calls appear sequentially within actual calls."""
        matched: list[tuple[str, str]] = []
        param_mismatches: list[dict[str, Any]] = []

        act_idx = 0
        exp_idx = 0

        while act_idx < len(actual) and exp_idx < len(expected):
            act = actual[act_idx]
            exp = expected[exp_idx]

            if act.normalized_name() == exp.normalized_name():
                mismatches = (
                    self._match_arguments_exact(act.args, exp.args)
                    if not criterion.ignore_args
                    else []
                )
                if not mismatches:
                    matched.append((act.name, exp.name))
                    exp_idx += 1
                else:
                    param_mismatches.extend(mismatches)
            act_idx += 1

        unmatched_expected = [f"{e.name}({e.args})" for e in expected[exp_idx:]]
        unexpected_calls = [
            f"{a.name}({a.args})" for a in actual if not any(a.name == m[0] for m in matched)
        ]

        score = exp_idx / len(expected) if len(expected) > 0 else 1.0
        passed = score >= criterion.threshold and len(unmatched_expected) == 0

        explanation = f"In-order match score: {score:.2f} ({exp_idx}/{len(expected)} expected calls satisfied sequentially)."

        return TrajectoryResult(
            score=score,
            passed=passed,
            match_type=MatchType.IN_ORDER,
            actual_tool_count=len(actual),
            expected_tool_count=len(expected),
            diagnosis=TrajectoryDiagnosis(
                matched_calls=matched,
                unmatched_expected=unmatched_expected,
                unexpected_calls=unexpected_calls,
                parameter_mismatches=param_mismatches,
                explanation=explanation,
            ),
        )

    def _grade_any_order(
        self,
        actual: Sequence[ToolCallRecord],
        expected: Sequence[ToolCallRecord],
        criterion: TrajectoryCriterion,
    ) -> TrajectoryResult:
        """Grade checking if all expected calls appear in actual calls regardless of order."""
        matched: list[tuple[str, str]] = []
        unmatched_expected: list[str] = []
        param_mismatches: list[dict[str, Any]] = []

        used_act_indices: set[int] = set()

        for exp in expected:
            found_idx = None
            for idx, act in enumerate(actual):
                if idx in used_act_indices:
                    continue
                if act.normalized_name() == exp.normalized_name():
                    mismatches = (
                        self._match_arguments_exact(act.args, exp.args)
                        if not criterion.ignore_args
                        else []
                    )
                    if not mismatches:
                        found_idx = idx
                        break

            if found_idx is not None:
                used_act_indices.add(found_idx)
                matched.append((actual[found_idx].name, exp.name))
            else:
                unmatched_expected.append(f"{exp.name}({exp.args})")

        unexpected_calls = [
            f"{a.name}({a.args})" for idx, a in enumerate(actual) if idx not in used_act_indices
        ]

        score = len(matched) / len(expected) if len(expected) > 0 else 1.0
        passed = score >= criterion.threshold and len(unmatched_expected) == 0

        explanation = (
            f"Any-order match score: {score:.2f} ({len(matched)}/{len(expected)} calls matched)."
        )

        return TrajectoryResult(
            score=score,
            passed=passed,
            match_type=MatchType.ANY_ORDER,
            actual_tool_count=len(actual),
            expected_tool_count=len(expected),
            diagnosis=TrajectoryDiagnosis(
                matched_calls=matched,
                unmatched_expected=unmatched_expected,
                unexpected_calls=unexpected_calls,
                parameter_mismatches=param_mismatches,
                explanation=explanation,
            ),
        )

    def _grade_fuzzy_semantic(
        self,
        actual: Sequence[ToolCallRecord],
        expected: Sequence[ToolCallRecord],
        criterion: TrajectoryCriterion,
    ) -> TrajectoryResult:
        """Grade tool trajectory with domain-aware semantic argument matching."""
        matched: list[tuple[str, str]] = []
        unmatched_expected: list[str] = []
        param_mismatches: list[dict[str, Any]] = []

        used_act_indices: set[int] = set()

        for exp in expected:
            best_idx = None
            best_sim = 0.0

            for idx, act in enumerate(actual):
                if idx in used_act_indices:
                    continue
                if act.normalized_name() != exp.normalized_name():
                    continue

                # Compute semantic argument similarity
                sim = self._compute_semantic_similarity(act, exp)
                if sim >= criterion.keyword_overlap_threshold and sim > best_sim:
                    best_sim = sim
                    best_idx = idx

            if best_idx is not None and best_sim >= criterion.keyword_overlap_threshold:
                used_act_indices.add(best_idx)
                matched.append((actual[best_idx].name, exp.name))
            else:
                unmatched_expected.append(f"{exp.name}({exp.args})")

        unexpected_calls = [
            f"{a.name}({a.args})" for idx, a in enumerate(actual) if idx not in used_act_indices
        ]

        matched_ratio = len(matched) / len(expected) if len(expected) > 0 else 1.0
        # If extra calls exist, mild penalty
        extra_penalty = 0.05 * len(unexpected_calls) if unexpected_calls else 0.0
        score = max(0.0, min(1.0, matched_ratio - extra_penalty))
        passed = score >= (criterion.threshold * 0.95) and len(unmatched_expected) == 0

        explanation = (
            f"Fuzzy semantic match score: {score:.2f} ({len(matched)}/{len(expected)} matched). "
            f"Unmatched: {len(unmatched_expected)}, Unexpected: {len(unexpected_calls)}."
        )

        return TrajectoryResult(
            score=score,
            passed=passed,
            match_type=MatchType.FUZZY_SEMANTIC,
            actual_tool_count=len(actual),
            expected_tool_count=len(expected),
            diagnosis=TrajectoryDiagnosis(
                matched_calls=matched,
                unmatched_expected=unmatched_expected,
                unexpected_calls=unexpected_calls,
                parameter_mismatches=param_mismatches,
                explanation=explanation,
            ),
        )

    def _compute_semantic_similarity(
        self, actual: ToolCallRecord, expected: ToolCallRecord
    ) -> float:
        """Compute semantic argument overlap between actual and expected catalog calls."""
        # 1. Category check
        act_cat = actual.category_normalized()
        exp_cat = expected.category_normalized()
        cat_match = 1.0 if (not exp_cat or exp_cat == act_cat) else 0.0

        # 2. Keywords token overlap
        act_tokens = self._extract_tokens(actual.normalized_keywords())
        exp_tokens = self._extract_tokens(expected.normalized_keywords())

        if not exp_tokens:
            keyword_score = 1.0
        elif not act_tokens:
            keyword_score = 0.0
        else:
            intersection = act_tokens & exp_tokens
            precision = len(intersection) / len(act_tokens) if act_tokens else 0.0
            recall = len(intersection) / len(exp_tokens) if exp_tokens else 0.0
            if (precision + recall) > 0:
                keyword_score = (2 * precision * recall) / (precision + recall)
            else:
                keyword_score = 0.0

        # Brand check: ensure expected brands appear in actual tokens
        known_brands = {
            "apple",
            "dell",
            "lenovo",
            "samsung",
            "sony",
            "bose",
            "google",
            "lg",
            "nest",
            "ecobee",
        }
        exp_brands = exp_tokens & known_brands
        act_brands = act_tokens & known_brands
        if exp_brands:
            if not (exp_brands & act_brands):
                # Missing core brand name severely penalizes similarity
                keyword_score *= 0.5
            elif exp_brands.issubset(act_brands):
                # All expected brands were captured; floor keyword score to 0.45
                keyword_score = max(keyword_score, 0.45)

        return (cat_match * 0.3) + (keyword_score * 0.7)

    @staticmethod
    def _extract_tokens(keywords: list[str]) -> set[str]:
        """Tokenize a list of keyword strings."""
        tokens: set[str] = set()
        stopwords = {
            "vs",
            "and",
            "or",
            "with",
            "for",
            "the",
            "in",
            "inch",
            "laptop",
            "laptops",
            "tablets",
            "tablet",
            "headphones",
            "headphone",
            "smart",
            "home",
            "tvs",
            "tv",
            "what",
            "are",
            "key",
            "differences",
            "between",
            "compare",
            "comparison",
            "versus",
            "performance",
            "specs",
            "chip",
            "memory",
            "ssd",
            "gb",
            "to",
            "is",
            "of",
            "on",
            "a",
            "an",
            "which",
            "better",
        }
        for k in keywords:
            words = re.findall(r"[a-z0-9]+", k.lower())
            for w in words:
                if len(w) > 1 and w not in stopwords:
                    tokens.add(w)
        return tokens

    def extract_expected_from_eval_case(self, case: dict[str, Any]) -> list[ToolCallRecord]:
        """Extract expected ToolCallRecord list from an ADK EvalCase dictionary."""
        records: list[ToolCallRecord] = []

        # 1. From direct conversation intermediate_data
        conv = case.get("conversation", [])
        if conv and isinstance(conv, list):
            inv = conv[0]
            interm = inv.get("intermediate_data", {})
            tool_uses = interm.get("tool_uses", [])
            for tu in tool_uses:
                args = dict(tu.get("args", {}))
                if "keywords" not in args:
                    # Enrich keywords from ground truth specs or expected SKUs
                    gt = case.get("ground_truth_specs", {})
                    extracted_names = [
                        spec.get("name") or spec.get("brand")
                        for spec in gt.values()
                        if isinstance(spec, dict) and (spec.get("name") or spec.get("brand"))
                    ]
                    if extracted_names:
                        args["keywords"] = extracted_names
                    elif "expected_skus" in case:
                        args["keywords"] = case["expected_skus"]
                records.append(
                    ToolCallRecord(
                        name=tu.get("name", "query_catalog"),
                        args=args,
                        call_id=tu.get("id"),
                    )
                )

        # 2. Fallback to expected_tool_use if top-level
        if not records and "expected_tool_use" in case:
            for tu in case["expected_tool_use"]:
                records.append(
                    ToolCallRecord(
                        name=tu.get("name", "query_catalog"),
                        args=tu.get("args", {}),
                        call_id=tu.get("id"),
                    )
                )

        # 3. Fallback synthesis from expected_skus / category
        if not records and "category" in case and "expected_skus" in case:
            # Synthetic default query_catalog call
            records.append(
                ToolCallRecord(
                    name="query_catalog",
                    args={
                        "category": case.get("category"),
                        "keywords": case.get("expected_skus", []),
                    },
                )
            )

        return records


try:
    from google.adk.evaluation.evaluator import (
        ConversationScenario,
        EvalStatus,
        EvaluationResult,
        Evaluator,
        Invocation,
        PerInvocationResult,
        RubricScore,
    )
    from google.genai.types import Content, Part

    _ADK_EVAL_AVAILABLE = True
except ImportError:
    _ADK_EVAL_AVAILABLE = False
    Evaluator = object  # type: ignore[misc, assignment]
    EvaluationResult = Any  # type: ignore[misc, assignment]
    PerInvocationResult = Any  # type: ignore[misc, assignment]
    RubricScore = Any  # type: ignore[misc, assignment]
    EvalStatus = Any  # type: ignore[misc, assignment]
    Invocation = Any  # type: ignore[misc, assignment]
    ConversationScenario = Any  # type: ignore[misc, assignment]


class ADKTrajectoryEvaluator(Evaluator if _ADK_EVAL_AVAILABLE else object):  # type: ignore[misc]
    """ADK native Evaluator plugin for evaluating tool call trajectories.

    Subclasses google.adk.evaluation.evaluator.Evaluator to allow direct programmatic
    execution in AgentEvaluator.evaluate() pipelines.
    """

    def __init__(
        self,
        grader: TrajectoryGrader | None = None,
        match_type: MatchType = MatchType.IN_ORDER,
        criterion: TrajectoryCriterion | None = None,
    ):
        self.grader = grader or TrajectoryGrader(default_match_type=match_type)
        self.match_type = match_type
        self.criterion = criterion or TrajectoryCriterion(match_type=match_type)

    def evaluate_invocations(
        self,
        actual_invocations: list[Any],
        expected_invocations: list[Any] | None = None,
        conversation_scenario: Any | None = None,
    ) -> Any:
        """Evaluate trajectory alignment between actual and expected invocations."""
        if not _ADK_EVAL_AVAILABLE:
            raise RuntimeError("google.adk.evaluation is not installed.")

        per_inv_results: list[PerInvocationResult] = []
        scores: list[float] = []

        num_inv = max(len(actual_invocations), len(expected_invocations or []))
        for i in range(num_inv):
            actual_inv = actual_invocations[i] if i < len(actual_invocations) else None
            expected_inv = (
                expected_invocations[i]
                if expected_invocations and i < len(expected_invocations)
                else None
            )

            actual_records = ToolCallRecord.from_adk_invocation(actual_inv) if actual_inv else []
            expected_records = (
                ToolCallRecord.from_adk_invocation(expected_inv) if expected_inv else []
            )

            result = self.grader.grade(
                actual=actual_records,
                expected=expected_records,
                criterion=self.criterion,
            )

            scores.append(result.score)
            status = EvalStatus.PASSED if result.passed else EvalStatus.FAILED

            rubric = RubricScore(
                rubric_id="tool_trajectory",
                score=result.score,
                rationale=result.diagnosis.explanation,
            )

            fallback_content = Content(parts=[Part.from_text(text="[Missing Invocation]")])
            resolved_actual = (
                actual_inv if actual_inv is not None else Invocation(user_content=fallback_content)
            )

            per_inv_results.append(
                PerInvocationResult(
                    actual_invocation=resolved_actual,
                    expected_invocation=expected_inv,
                    score=result.score,
                    eval_status=status,
                    rubric_scores=[rubric],
                )
            )

        overall_score = sum(scores) / len(scores) if scores else 1.0
        overall_status = (
            EvalStatus.PASSED
            if all(r.eval_status == EvalStatus.PASSED for r in per_inv_results)
            else EvalStatus.FAILED
        )

        return EvaluationResult(
            overall_score=overall_score,
            overall_eval_status=overall_status,
            per_invocation_results=per_inv_results,
            overall_rubric_scores=[
                RubricScore(
                    rubric_id="tool_trajectory_avg_score",
                    score=overall_score,
                    rationale=f"Overall trajectory score across {len(scores)} invocations: {overall_score:.2f}",
                )
            ],
        )
