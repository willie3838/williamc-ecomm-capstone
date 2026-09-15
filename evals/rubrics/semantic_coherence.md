# Semantic Coherence & Faithfulness Rubric (LLM Judge)

## 1. Metric Definition

**Semantic Coherence & Faithfulness** evaluates whether the narrative comparison summary and recommendations accurately reflect the technical matrix without contradictions, unsupported inferences, or tone distortions.

- **Target Score**: $\ge 0.95$ (or $\ge 4.5 / 5.0$ normalized)
- **Judge Model**: Gemini 1.5 Flash / Gemini 2.5 Flash / Hermetic Fallback Judge

---

## 2. LLM-as-a-Judge Prompt Template

```text
You are an expert impartial evaluation judge assessing a product comparison assistant.
You will evaluate whether the generated comparison summary is faithful to the verified catalog data.

[INPUT QUERY]
{query}

[GROUND TRUTH / MATRIX DATA]
{matrix_json}

[GENERATED SUMMARY & RECOMMENDATIONS]
{generated_text}

Rate the generated comparison on a scale of 1 to 5 based on:
1. Factual Consistency: Does every claim in the narrative match the matrix specs?
2. Contradiction Absence: Does the narrative never invert comparison winners (e.g. claiming a more expensive item is cheaper)?
3. Grounded Recommendations: Are buying recommendations backed by catalog attributes?

Return your response in strict JSON:
{
  "score": <1-5 integer>,
  "normalized_score": <0.0-1.0 float>,
  "has_contradiction": <bool>,
  "reasoning": "<concise explanation>"
}
```

---

## 3. Scoring Scale

| Rating | Normalized | Description |
| :--- | :--- | :--- |
| **5 (Flawless)** | $1.0$ | Perfectly faithful to matrix data; clear, balanced narrative; zero hallucinations or inversions. |
| **4 (Good)** | $0.8$ | Minor stylistic phrasing variance, but all facts and comparisons are 100% accurate. |
| **3 (Borderline)** | $0.6$ | General gist is correct, but omits a key comparison winner or makes ambiguous claims. |
| **2 (Poor)** | $0.4$ | Minor factual discrepancy or misstated specification. |
| **1 (Unacceptable)**| $0.0$ | Direct contradiction with matrix (e.g., claiming wrong winner) or hallucinated specs. |
