# Tool Trajectory Evaluation Rubric

## 1. Metric Definition

**Tool Trajectory Quality** measures the precision, sequencing, and argument fidelity of tool calls executed by the Best Buy Catalog Comparison Agent against canonical golden trajectories defined in Google ADK evaluation sets (`evals/dataset/benchmark_catalog.evalset.json`).

- **Target Score**: $\ge 1.00$ (100% compliance with canonical tool invocation expectations)
- **Warning Threshold**: $< 0.95$ (triggers investigation of query expansion or routing drift)
- **Critical Pipeline Threshold**: $< 0.90$ (fails CI/CD evaluation gate and triggers deployment rollback)

$$\text{Tool Trajectory Score} = \frac{\sum_{i=1}^{K} \text{Matched Tool Invocations}_i}{\max(\text{Total Actual Calls}, \text{Total Expected Calls})}$$

---

## 2. Evaluation Match Strategies

The trajectory grader supports four configurable match strategies (`MatchType`):

| Match Type | Matching Semantic | Use Case | Tolerance & Flexibility |
| :--- | :--- | :--- | :--- |
| **`EXACT`** | Strict 1:1 sequential alignment and identical argument values. | Deterministic single-step lookups with predefined parameters. | Zero tolerance for extraneous calls, reordering, or parameter variations. |
| **`IN_ORDER`** | Golden tool calls must appear in order, allowing intermediate exploratory calls. | Multi-step reasoning where the agent performs exploratory catalog filtering. | Allows intermediate exploratory calls from `allowed_extra_tools`. |
| **`ANY_ORDER`** | Golden tool calls must all be executed, but invocation order is unrestricted. | Parallel or asynchronous retrieval operations across multiple product categories. | Reordering permitted; all expected calls must succeed. |
| **`FUZZY_SEMANTIC`** | Subsequence match with token overlap and brand extraction for string parameters. | Natural language search queries where customer phrasing varies. | Jaccard token overlap $\ge 0.50$ or brand name containment accepted. |

---

## 3. Automated Scoring & Diagnostic Rules

| Scenario | Score Impact | Diagnosis Classification |
| :--- | :--- | :--- |
| **Perfect Trajectory Match** | $1.00$ | All expected tools called in compliance with match strategy; zero argument errors. |
| **Intermediate Exploratory Calls (`IN_ORDER`)** | $1.00$ | Intermediate queries executed within `allowed_extra_tools` without dropping required calls. |
| **Argument Mismatch (Exact Mode)** | Proportional penalty ($0.0 - 0.5$) | Classified as `parameter_mismatches` with `field`, `actual`, and `expected` values. |
| **Partial Keyword Overlap (`FUZZY_SEMANTIC`)** | Proportional score ($\ge 0.50$) | Evaluated via token Jaccard similarity and brand extraction. |
| **Missing Expected Tool Call** | Heavy penalty ($\frac{\text{matched}}{\text{expected}}$) | Classified as `unmatched_expected` (e.g. omitted SKU lookup). |
| **Unexpected Spurious Tool Call** | Penalty ($\frac{\text{matched}}{\text{actual}}$) | Classified as `unexpected_calls` (e.g. redundant query or ungrounded external tool). |
| **Zero Tool Calls When Expected** | $0.00$ | Total failure; agent failed to invoke catalog retrieval tool. |
| **Zero Tool Calls When None Expected** | $1.00$ | Correctly avoided unnecessary tool calls for conversational/clarification queries. |

---

## 4. Integration with Google ADK

Tool trajectory evaluation is fully integrated into the Google ADK evaluation harness:
1. **`ADKTrajectoryEvaluator`**: Subclasses `google.adk.evaluation.evaluator.Evaluator` to grade `Invocation.intermediate_data.tool_uses` natively during `AgentEvaluator.evaluate()`.
2. **`TrajectoryRecorder`**: Thread-safe, async-safe context manager using Python `contextvars` to dynamically trace tool invocations during live benchmark runs.
3. **BigQuery Telemetry Export**: Emits `adk_tool_trajectory_score` alongside `avg_spec_accuracy` and `avg_citation_faithfulness` to `catalog_analytics.evaluation_runs`.
