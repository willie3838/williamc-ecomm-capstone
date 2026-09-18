# Counterfactual Anti-Overfitting & Generalization Evaluation Rubric

## 1. Metric Definition & Motivation

In production agentic AI systems, model prompts, heuristic parsers, and retrieval filters are frequently tuned and hillclimbed against a fixed benchmark evaluation dataset (e.g. the 80-pair canonical benchmark in `evals/dataset/benchmark_catalog.evalset.json`). Without strict safeguards, this iterative optimization leads to:
1. **Benchmark Overfitting**: Memorizing specific query phrasings, brand orders, and attribute layouts, causing accuracy to degrade on unseen test distributions.
2. **Parametric Memory Leakage**: Large foundation models fall back to parametric training memories rather than adhering strictly to newly retrieved tool outputs (e.g. asserting pre-trained launch specs or MSRP rather than updated or promotional catalog values).
3. **Adversarial & Chatter Fragility**: Agents trained solely on clean comparative queries hallucinate phantom product comparisons and false citations when given out-of-scope customer rants, single-product inquiries, or cross-category mismatches.

The **Counterfactual Anti-Overfitting Gate** enforces generalization rigor by comparing agent performance across a held-out dataset, auditing counterfactual spec adherence, and verifying negative query suppression.

---

## 2. Quantitative Criteria & Mathematical Bounds

### A. Generalization Gap ($\Delta$)
The generalization gap quantifies the performance difference between the primary benchmark and the held-out dataset:

$$\Delta_{\text{accuracy}} = \max(0.0, \text{Accuracy}_{\text{benchmark}} - \text{Accuracy}_{\text{holdout}})$$
$$\Delta_{\text{citation}} = \max(0.0, \text{Citation}_{\text{benchmark}} - \text{Citation}_{\text{holdout}})$$

- **Target Score**: $\Delta \le 0.02$ (2% drop)
- **Maximum Permissible Gap**: $\Delta \le 0.05$ (5% drop)
- **Overfitting Trigger**: $\Delta > 0.05$ triggers an automatic `OVERFITTING_DETECTED` gate failure and blocks deployment.

### B. Holdout Performance Floors
To prevent artificial benchmark inflation from masking absolute performance drops:
- **Holdout Data Accuracy**: $\ge 0.95$
- **Holdout Citation Faithfulness**: $\ge 0.90$
- **Holdout End-to-End P95 Latency**: $\le 3.0\text{s}$

### C. Counterfactual Specification Grounding Score
Measures whether the agent strictly honors perturbed or counterfactual catalog attributes (promotional prices, custom RAM configurations, updated battery endurance) returned by the catalog retrieval tool, rather than reverting to parametric memory:

$$\text{Counterfactual Fidelity} = \frac{\sum \text{Correct Perturbed Specs}}{\sum \text{Total Perturbed Specs Checked}}$$

- **Target Score**: $1.00$
- **Minimum Floor**: $\ge 0.95$

### D. Negative Query & Chatter Suppression Rate
For out-of-scope customer service inquiries, general greetings, and non-comparative rants (0-SKU cases):

$$\text{Suppression Rate} = \frac{\sum (\text{Queries with 0 Hallucinated SKUs and 0 Phantom Tables})}{\text{Total Negative Queries Tested}}$$

- **Required Target**: $100.0\%$ ($1.00$)
- Any hallucinated SKU or phantom comparison table on a 0-SKU test query constitutes a zero-tolerance failure ($0.0$).

---

## 3. Evaluation Protocol & Automated Execution

The Anti-Overfitting Gate is run programmatically via:

```bash
# Automated evaluation across both benchmark and holdout datasets:
python3 -m evals.anti_overfitting_gate \
  --benchmark-dataset evals/dataset/benchmark_catalog.evalset.json \
  --holdout-dataset evals/dataset/holdout_catalog.evalset.json \
  --max-gap 0.05 \
  --output evals/reports/anti_overfitting_report.json \
  --strict
```

Or using pre-computed evaluation reports:
```bash
python3 -m evals.anti_overfitting_gate \
  --benchmark-report evals/reports/benchmark_report.json \
  --holdout-report evals/reports/holdout_report.json \
  --strict
```
