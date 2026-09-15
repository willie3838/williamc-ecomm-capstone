# Citation Faithfulness Evaluation Rubric

## 1. Metric Definition

**Citation Faithfulness** quantifies the fidelity and traceability of product assertions made by the agent. Every technical spec, comparison claim, and product mention must be grounded in an explicit, verifiable SKU citation (`[SKU: <id>]`).

- **Target Score**: $\ge 0.95$ (95% of asserted claims carry valid, verified SKU citations)
- **Critical Pipeline Threshold**: $< 0.90$ (fails CI pipeline and quality gate)

$$\text{Citation Faithfulness} = \frac{\sum_{i=1}^{M} \text{Verifiable Inline Citations}_i}{\sum_{i=1}^{M} \text{Total Product Claims}_i}$$

---

## 2. Citation Requirements & Syntax

1. **Standard Citation Syntax**:
   - Every product reference in the summary narrative and recommendations must include an inline bracket citation:
     ```text
     Apple MacBook Air 13.6" [SKU: 6534606]
     ```
2. **Citation Object Validation**:
   - The `citations` array in `CompareResponse` must include an object for every retrieved SKU:
     ```json
     {
       "sku": "6534606",
       "url": "https://www.bestbuy.com/site/sku/6534606.p"
     }
     ```
3. **Traceability Rule**:
   - Citations must map to real items returned by the BigQuery catalog.
   - Fabricated, non-existent, or mismatched SKU citations incur a score of $0.0$.

---

## 3. Automated Scoring Rules

| Scenario | Score Impact | Rationale |
| :--- | :--- | :--- |
| **All products cited with valid `[SKU: ...]`** | $1.0$ | Perfect citation fidelity across narrative and structured payload. |
| **Missing citation for one product in summary** | $0.5$ | Partial faithfulness; claims cannot be verified against catalog. |
| **Invalid SKU syntax (e.g., missing bracket or prefix)** | $0.25$ | Parser failure; frontend citation links will not render. |
| **Hallucinated SKU not present in catalog** | $0.0$ | Critical failure; zero tolerance for phantom citations. |
| **Empty citations list in response payload** | $0.0$ | Complete absence of grounding references. |
