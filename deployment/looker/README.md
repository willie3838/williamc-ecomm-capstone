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

## 3. Automated Option B: 1-Click Looker Studio Linking API URLs

Because Looker Studio (`lookerstudio.google.com`) requires an interactive browser session to save visual reports, Terraform outputs pre-bound **Looker Studio Linking API URLs** (`terraform output looker_studio_linking_urls`) that auto-configure the BigQuery connector, project, dataset, and BI view in **1 click**:

1. **[1-Click: Create Category Engagement Report (`vw_most_compared_categories`)](https://lookerstudio.google.com/reporting/create?ds.alias=CategoryEngagement&ds.connector=bigQuery&ds.projectId=fde-bestbuy-sandbox-dev-508321&ds.type=TABLE&ds.datasetId=catalog_agent_telemetry&ds.tableId=vw_most_compared_categories)**
2. **[1-Click: Create Latency & SLA Report (`vw_latency_performance_trends`)](https://lookerstudio.google.com/reporting/create?ds.alias=LatencyTrends&ds.connector=bigQuery&ds.projectId=fde-bestbuy-sandbox-dev-508321&ds.type=TABLE&ds.datasetId=catalog_agent_telemetry&ds.tableId=vw_latency_performance_trends)**
3. **[1-Click: Create Token & Cost Report (`vw_token_and_cost_analytics`)](https://lookerstudio.google.com/reporting/create?ds.alias=TokenCostAnalytics&ds.connector=bigQuery&ds.projectId=fde-bestbuy-sandbox-dev-508321&ds.type=TABLE&ds.datasetId=catalog_agent_telemetry&ds.tableId=vw_token_and_cost_analytics)**

When the link opens in your browser, click **Acknowledge and Save** in the top-right corner to persist the report.

