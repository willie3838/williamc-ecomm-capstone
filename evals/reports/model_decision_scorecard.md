# Empirical Foundation Model Decision Scorecard (ADR-004)

- **Generated At**: `2026-09-21T21:06:53.351477+00:00`
- **Benchmark Corpus**: `80` Golden Comparison Queries (Laptops, Tablets, Headphones, Smart Home, TVs)
- **Selected Production Architecture**: **`tiered-hybrid`** (`AgentVersionSpec 1.0.0`)
- **Registered High-QPS Canary**: **`gemini-2.5-flash`** (`AgentVersionSpec 1.1.0-flash`)

---

## 1. Multi-Objective Empirical Model Comparison Matrix

| Candidate Architecture | Turn 1 / Turn 2 Routing | Data Accuracy ($\ge 0.98$) | Citation Faithfulness ($\ge 0.95$) | Schema Validity ($1.00$) | P50 / P95 Latency ($\le 3.00$s) | Unit Cost ($/1k Queries) | Synthesis Quality (1-5) | SLA Gate | Composite Score | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`tiered-hybrid`** | `gemini-3.5-flash` $\rightarrow$ `gemini-2.5-pro` | `0.995` | `0.988` | `1.00` | `1.18s` / `2.18s` | `$0.85` | `4.84 / 5.0` | **PASS** | **`89.78`** | `PRODUCTION_SELECTED` |
| **`gemini-2.5-flash`** | `gemini-2.5-flash` $\rightarrow$ `gemini-2.5-flash` | `0.985` | `0.962` | `1.00` | `0.84s` / `1.42s` | `$0.22` | `4.35 / 5.0` | **PASS** | **`86.80`** | `VIABLE_FALLBACK` |
| **`gemini-2.5-pro`** | `gemini-2.5-pro` $\rightarrow$ `gemini-2.5-pro` | `0.996` | `0.991` | `1.00` | `1.95s` / `3.48s` | `$2.45` | `4.88 / 5.0` | **FAIL** | **`55.96`** | `SLA_VIOLATION_LATENCY` |
| **`gemini-1.5-flash`** | `gemini-1.5-flash` $\rightarrow$ `gemini-1.5-flash` | `0.938` | `0.912` | `0.96` | `0.91s` / `1.55s` | `$0.19` | `3.60 / 5.0` | **FAIL** | **`0.00`** | `SLA_VIOLATION_QUALITY` |

---

## 2. Head-to-Head Pairwise Judge Tournament (`evals/pairwise_judge.py`)

| Matchup (`Model A` vs `Model B`) | Win Rate A | Win Rate B | Tie Rate | Mean Score A vs B | Tournament Winner | Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`tiered-hybrid`** vs **`gemini-2.5-flash`** | `100.0%` | `0.0%` | `0.0%` | `4.91` vs `4.45` | **`tiered-hybrid`** | tiered-hybrid achieved 100.0% win rate (2W-0L-0T, mean score 4.91 vs 4.45) against gemini-2.5-flash. Tournament winner: tiered-hybrid. |
| **`tiered-hybrid`** vs **`gemini-2.5-pro`** | `0.0%` | `0.0%` | `100.0%` | `5.00` vs `5.00` | **`TIE (Quality Parity)`** | tiered-hybrid achieved 0.0% win rate (0W-0L-1T, mean score 5.00 vs 5.00) against gemini-2.5-pro. Tournament winner: TIE. |
| **`tiered-hybrid`** vs **`gemini-1.5-flash`** | `100.0%` | `0.0%` | `0.0%` | `4.64` vs `1.94` | **`tiered-hybrid`** | tiered-hybrid achieved 100.0% win rate (1W-0L-0T, mean score 4.64 vs 1.94) against gemini-1.5-flash. Tournament winner: tiered-hybrid. |

---

## 3. Architectural Trade-Off & Disqualification Analysis (ADR-004)

1. **Why Pure `gemini-2.5-pro` Was Rejected (`SLA_VIOLATION_LATENCY`)**:
   - Running `gemini-2.5-pro` across both Turn 1 (intent/entity extraction) and Turn 2 (comparative synthesis) yields a P95 latency of **`3.48s`**, violating the non-negotiable **`<= 3.0s`** retail conversion SLA (`RUBRIC.md` North Star #3). Furthermore, its token cost (`$2.45 / 1,000 queries`) is **2.88x more expensive** than `tiered-hybrid` (`$0.85 / 1,000 queries`) for a statistically negligible `+0.001` accuracy delta.
2. **Why `gemini-1.5-flash` Was Rejected (`SLA_VIOLATION_QUALITY`)**:
   - Legacy `gemini-1.5-flash` drops to **`0.938` Data Accuracy** (`< 0.98` gate) and **`0.912` Citation Faithfulness** (`< 0.95` gate), occasionally omitting inline `[SKU: ...]` brackets on multi-brand comparisons and exhibiting a `4.0%` Pydantic schema validation failure rate.
3. **Why `tiered-hybrid` Is Optimal (`PRODUCTION_SELECTED`)**:
   - Routing Turn 1 Intent Classification & Reranking (`QueryIntentAnalysis`, `temperature=0.0`) to **`gemini-3.5-flash`** (with automatic fallback to `gemini-2.5-flash`) completes entity extraction in `~350ms` (`P95 <= 650ms`).
   - Routing Turn 2 Grounded Matrix & Narrative Synthesis (`temperature=0.1`, `max_output_tokens=2048`) to **`gemini-2.5-pro`** preserves `0.995` Data Accuracy and `4.84 / 5.0` executive trade-off depth while keeping end-to-end P95 latency at **`2.18s`** (`820ms` safety buffer below the `3.0s` ceiling) and unit cost at **`$0.85 / 1,000 queries`**.
4. **Role of `gemini-2.5-flash` Canary (`VIABLE_FALLBACK`)**:
   - Registered in Google Cloud Agent Registry as `1.1.0-flash`. Satisfies all hard SLA gates (`0.985` accuracy, `1.42s` P95 latency, `$0.22 / 1k` cost) and serves as the automated fallback/canary tier during regional `gemini-2.5-pro` quota pressure or 10x Black Friday traffic bursts.
