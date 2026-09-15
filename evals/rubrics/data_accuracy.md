# Data Accuracy Evaluation Rubric

## 1. Metric Definition

**Data Accuracy** measures the degree to which technical specifications and product claims produced by the Catalog Comparison Agent correspond strictly and precisely to the ground truth data stored in Google Cloud BigQuery (`fde-bestbuy-sandbox-dev-508321.catalog.products`).

- **Target Score**: $\ge 0.98$ (98% of evaluated specifications match catalog ground truth)
- **Critical Rollback Threshold**: $< 0.95$ (triggers immediate alert and blocks deployment)

$$\text{Data Accuracy} = \frac{\sum_{i=1}^{N} \text{Correctly Grounded Specs}_i}{\sum_{i=1}^{N} \text{Total Evaluated Specs}_i}$$

---

## 2. Evaluation Criteria & Scoring

Each product specification evaluated in the comparison matrix and synthesis narrative is scored on a binary scale ($1.0$ for exact match, $0.0$ for discrepancy or hallucination).

| Spec Dimension | Exact Match Requirement ($1.0$) | Tolerances / Normalization | Hallucination Penalty ($0.0$) |
| :--- | :--- | :--- | :--- |
| **Pricing** | Matches `price` numeric float to 2 decimal places. | Formats like `$1,099.00` and `$1099` normalized to `1099.0`. | Any price deviation exceeding $\$0.00$. |
| **Memory (RAM)** | Integer memory size matching `ram_gb`. | `16 GB`, `16GB`, and `16` are normalized to `16`. | Any mismatched memory size (e.g., claiming 32GB instead of 16GB). |
| **Storage (SSD)** | Capacity in GB matching `storage_gb`. | `512 GB`, `512GB`, `1TB` vs `1000GB` normalized. | Fabricated capacity or missing storage. |
| **Battery Life** | Endurance in hours matching `battery_life_hours`. | `Up to 18 hours`, `18 hrs`, and `18.0` normalized. | Claiming higher battery life than catalog specification. |
| **Processor / CPU** | Exact model family matching `processor`. | Minor whitespace or capitalization differences permitted. | Claiming different chip family (e.g., M3 Pro vs M3, Ultra 5 vs Ultra 7). |
| **Display Resolution**| Resolution text matching `display_resolution`. | Case-insensitive substring matching allowed. | Inverted resolutions or fabricated pixel counts. |
| **Weight** | Weight in lbs/oz matching `weight_lbs` or `weight_oz`. | Unit conversion allowed (e.g., $1\text{ lb} = 16\text{ oz}$). | Erroneous weight claims. |

---

## 3. Automated Verification Protocol

1. **Extraction**: The evaluation harness parses the `CompareResponse`:
   - Inspects `products` list.
   - Inspects `comparison_matrix` rows for evaluated feature keys.
   - Extracts numeric and text values corresponding to each cited SKU.
2. **Comparison**: Compares each extracted spec against `ground_truth_specs[sku][feature]`.
3. **Scoring**:
   - If all ground truth features for all expected SKUs match: $1.0$.
   - If any feature has an ungrounded or mismatched value: partial score $\frac{\text{matching}}{\text{total}}$.
   - If an unexpected product was retrieved or product was omitted: penalty applied.
