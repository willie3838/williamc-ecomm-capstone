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

## 2. Automated Option A: 100% Terraform Cloud Monitoring Dashboard (`monitoring.tf`)

A production operational dashboard (`google_monitoring_dashboard.catalog_agent_dashboard`) is **100% codified in Terraform** at [`deployment/terraform/monitoring.tf`](../terraform/monitoring.tf) and automatically provisioned with zero manual clicks:
- **P50 & P95 Request Latency vs. 3,000ms SLA Threshold** (`run.googleapis.com/request_latencies`)
- **Request Volume by HTTP Status Class** (`run.googleapis.com/request_count`)
- **Cloud Run Container CPU & Memory Utilization** (`run.googleapis.com/container/cpu/utilizations`)
- **BigQuery Query Execution Rate** (`bigquery.googleapis.com/query/count`)

View it directly in GCP Console:
`https://console.cloud.google.com/monitoring/dashboards?project=fde-bestbuy-sandbox-dev-508321`

---

## 3. Automated Option B: 1-Click Looker Studio Linking API URLs & BigQuery Native Export

Because Looker Studio (`lookerstudio.google.com`) requires an interactive browser session to save visual reports, Terraform provisions a single **Unified Executive BI View (`vw_unified_executive_dashboard`)** with human-readable units (`Latency_Seconds`, `SLA_Compliance`, `Total_Tokens`, `BigQuery_MB_Scanned`, `Estimated_Cost_USD`) and embeds the 1-click link directly in the Cloud Monitoring Dashboard (`monitoring.tf`):

- **Unified All-in-One Executive Dashboard (`vw_unified_executive_dashboard`)**:
  `https://lookerstudio.google.com/reporting/create?c.mode=edit&r.reportName=TechBuy_Unified_Executive_Dashboard&ds.datasourceName=UnifiedExecutiveTelemetry&ds.connector=bigQuery&ds.type=TABLE&ds.projectId=fde-bestbuy-sandbox-dev-508321&ds.datasetId=catalog_agent_telemetry&ds.tableId=vw_unified_executive_dashboard`

### Alternative: Open Directly from BigQuery Console in 2 Clicks
1. Open the BigQuery dataset in GCP Console:
   `https://console.cloud.google.com/bigquery?project=fde-bestbuy-sandbox-dev-508321&ws=!1m4!1m3!3m2!1sfde-bestbuy-sandbox-dev-508321!2scatalog_agent_telemetry`
2. Click `vw_unified_executive_dashboard` $\rightarrow$ click **Export** (top toolbar) $\rightarrow$ **Explore with Looker Studio** $\rightarrow$ click **Save and Share**.



