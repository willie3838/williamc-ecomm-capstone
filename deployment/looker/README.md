# Looker Studio Operational & Business Intelligence Dashboards

This directory contains the operational runbook and configuration guide for connecting Google Cloud Looker Studio to the Best Buy Catalog Comparison Agent telemetry pipeline in BigQuery.

## 1. Codified BI Views in BigQuery (Single Source of Truth)

All BigQuery reporting views are defined and deployed exclusively via Terraform in [`deployment/terraform/bigquery.tf`](../terraform/bigquery.tf). Terraform automatically provisions three pre-aggregated views inside the `${var.telemetry_dataset_id}` dataset:

1. **`vw_most_compared_categories`**:
   - Aggregates daily comparison volume and average latency per product category (`Laptops`, `Headphones`, `Tablets`, `TVs`).
   - Used for **Most Compared Product Categories** bar charts and category distribution heatmaps.

2. **`vw_latency_performance_trends`**:
   - Aggregates request count, average total latency, P95 total latency, and average BigQuery bytes billed grouped by execution status.
   - Used for **Database Latency vs. Total Agent Reasoning Latency** dual-axis time series charts.

3. **`vw_token_and_cost_analytics`**:
   - Aggregates total and average input/output tokens, bytes scanned, and calculated USD expenditure.
   - Formula: `(Bytes Scanned / 1TB * $6.25) + (Input Tokens / 1M * $0.075) + (Output Tokens / 1M * $0.30)`.
   - Used for **Executive Cost & Token Burn** KPI scorecards.

---

## 2. Setting Up Looker Studio Dashboards

Follow these steps to link Looker Studio to the sandbox BigQuery project:

1. Navigate to [Looker Studio](https://lookerstudio.google.com/).
2. Click **Create** -> **Data Source**.
3. Select the **BigQuery** connector.
4. Select:
   - **Project**: `fde-bestbuy-sandbox-dev-508321` (or your active `var.project_id`).
   - **Dataset**: `catalog_agent_telemetry`.
   - **Table/View**: Select `vw_most_compared_categories`, `vw_latency_performance_trends`, and `vw_token_and_cost_analytics`.
5. Add Visualizations:
   - **Page 1: Category Engagement**: Horizontal Bar Chart (`category` vs. `comparison_count`).
   - **Page 2: Performance & Latencies**: Time series line chart (`date_bucket` vs. `avg_total_latency_ms` and `p95_total_latency_ms` with a 3000ms reference line).
   - **Page 3: Usage & Costs**: Scorecards displaying `total_comparisons`, `total_input_tokens`, `total_bytes_scanned`, and `estimated_cost_usd`.
