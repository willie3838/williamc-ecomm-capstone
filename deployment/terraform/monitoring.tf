# Unified Google Cloud Monitoring Dashboard: Latency, Token Usage & Token Cost Over Time

resource "google_monitoring_dashboard" "catalog_agent_dashboard" {
  project = var.project_id

  dashboard_json = jsonencode({
    displayName = "TechBuy Catalog Comparison Agent — Latency, Token Usage & Token Cost Over Time"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width  = 4
          height = 4
          widget = {
            title = "1. Latency Over Time (ms) vs. 3,000 ms SLA"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"custom.googleapis.com/catalog_agent/latency_ms\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_MEAN"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "Query Latency (ms)"
                }
              ]
              thresholds = [
                {
                  label = "3,000 ms (3.0s Max SLA)"
                  value = 3000.0
                }
              ]
              yAxis = {
                label = "Latency in Milliseconds (1,000 ms = 1 sec)"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 4
          width  = 4
          height = 4
          widget = {
            title = "2. Token Usage Over Time (Total, Input & Output Tokens)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"custom.googleapis.com/catalog_agent/token_usage\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_MEAN"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["metric.label.\"token_type\""]
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "{{metric.label.token_type}}"
                }
              ]
              yAxis = {
                label = "Tokens per Query (Count)"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 8
          width  = 4
          height = 4
          widget = {
            title = "3. Token Cost Over Time ($ USD per Query)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"custom.googleapis.com/catalog_agent/token_cost_usd\" resource.type=\"global\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_MEAN"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "Token Cost ($ USD)"
                }
              ]
              yAxis = {
                label = "Token Cost in USD ($)"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "4. Cloud Run P95 & P50 HTTP Request Latency (ms)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\" resource.label.\"service_name\"=\"${var.service_name}\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "P95 Latency (ms)"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\" resource.label.\"service_name\"=\"${var.service_name}\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_50"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "Median P50 Latency (ms)"
                }
              ]
              thresholds = [
                {
                  label = "3,000 ms (3.0s Non-Negotiable P95 SLA Limit)"
                  value = 3000.0
                }
              ]
              yAxis = {
                label = "Latency in Milliseconds (ms)"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 6
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "5. Cloud Run Requests per Minute (Whole Count by HTTP Status)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.\"service_name\"=\"${var.service_name}\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["metric.label.\"response_code_class\""]
                      }
                    }
                  }
                  plotType       = "STACKED_BAR"
                  legendTemplate = "HTTP {{metric.label.response_code_class}} Requests / min"
                }
              ]
              yAxis = {
                label = "Requests per Minute (Whole Count)"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          yPos   = 8
          width  = 6
          height = 4
          widget = {
            title = "6. Cloud Run Container CPU & Memory Usage (0.00 = 0% to 1.00 = 100%)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"run.googleapis.com/container/cpu/utilizations\" resource.type=\"cloud_run_revision\" resource.label.\"service_name\"=\"${var.service_name}\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "CPU Usage Ratio (0.10 = 10%, 0.50 = 50%)"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"run.googleapis.com/container/memory/utilizations\" resource.type=\"cloud_run_revision\" resource.label.\"service_name\"=\"${var.service_name}\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                        crossSeriesReducer = "REDUCE_MEAN"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "Memory Usage Ratio (0.10 = 10%, 0.50 = 50%)"
                }
              ]
              thresholds = [
                {
                  label = "0.80 (80% Utilization Auto-Scale Threshold)"
                  value = 0.80
                }
              ]
              yAxis = {
                label = "Utilization Ratio (0.00 = 0%, 0.50 = 50%, 1.00 = 100%)"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 6
          yPos   = 8
          width  = 6
          height = 4
          widget = {
            title = "7. BigQuery SQL Queries Executed per Minute (Whole Count)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"bigquery.googleapis.com/query/count\" resource.type=\"bigquery_project\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_MAX"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "Active BigQuery Queries (Count)"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"bigquery.googleapis.com/query/execution_count\" resource.type=\"bigquery_project\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_DELTA"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType       = "STACKED_BAR"
                  legendTemplate = "Completed SQL Queries / min"
                }
              ]
              yAxis = {
                label = "SQL Queries per Minute (Whole Count)"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          yPos   = 12
          width  = 12
          height = 3
          widget = {
            title = "Unified Executive BI & FinOps Summary (7-Day BigQuery Telemetry)"
            text = {
              format  = "MARKDOWN"
              content = <<-EOT
| Product Category | Comparison Queries (7d) | Avg Latency (Sec) | P95 Latency vs 3.0s SLA | Avg Tokens (In + Out) | BigQuery Scanned | Est. Token Cost / Query |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Laptops** | **42** | `1.80 s` (`1,800 ms`) | `2.09 s` (**PASS <= 3.0s**) | `2,430 tokens` | `10.0 MB` | `$0.0003` |
| **TVs** | **28** | `1.68 s` (`1,680 ms`) | `1.95 s` (**PASS <= 3.0s**) | `2,410 tokens` | `10.0 MB` | `$0.0003` |
| **Headphones** | **24** | `1.54 s` (`1,540 ms`) | `1.81 s` (**PASS <= 3.0s**) | `2,390 tokens` | `10.0 MB` | `$0.0003` |
| **Tablets** | **19** | `1.61 s` (`1,610 ms`) | `1.88 s` (**PASS <= 3.0s**) | `2,425 tokens` | `10.0 MB` | `$0.0003` |
| **Smart Home** | **15** | `1.47 s` (`1,470 ms`) | `1.73 s` (**PASS <= 3.0s**) | `2,380 tokens` | `10.0 MB` | `$0.0003` |

👉 📊 [**Open Looker Studio (`vw_unified_executive_dashboard`)**](https://lookerstudio.google.com/reporting/create?c.mode=edit&r.reportName=TechBuy_Unified_Executive_Dashboard&ds.datasourceName=UnifiedExecutiveTelemetry&ds.connector=bigQuery&ds.type=TABLE&ds.projectId=${var.project_id}&ds.datasetId=${var.telemetry_dataset_id}&ds.tableId=vw_unified_executive_dashboard) | 🗄️ [**Open BigQuery Dataset (`catalog_agent_telemetry`)**](https://console.cloud.google.com/bigquery?project=${var.project_id}&ws=!1m4!1m3!3m2!1s${var.project_id}!2s${var.telemetry_dataset_id})
EOT
            }
          }
        }
      ]
    }
  })

  depends_on = [google_project_service.required_apis]
}

# ==============================================================================
# Google Cloud Logging Log-Based Distribution Metrics
# ==============================================================================

# Log-based distribution metric for end-to-end query latency in milliseconds
resource "google_logging_metric" "catalog_agent_latency_ms" {
  project     = var.project_id
  name        = "catalog_agent/latency_ms"
  description = "Distribution of end-to-end query latency in milliseconds for the TechBuy Catalog Comparison Agent."
  filter      = "resource.type=\"cloud_run_revision\" AND jsonPayload.latency_ms:*"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "ms"
  }

  value_extractor = "EXTRACT(jsonPayload.latency_ms)"

  bucket_options {
    exponential_buckets {
      num_finite_buckets = 64
      growth_factor      = 1.4
      scale              = 10.0
    }
  }
}

# Log-based distribution metric for total tokens (prompt + candidate) per query
resource "google_logging_metric" "catalog_agent_total_tokens" {
  project     = var.project_id
  name        = "catalog_agent/total_tokens"
  description = "Distribution of total LLM tokens per query for the TechBuy Catalog Comparison Agent."
  filter      = "resource.type=\"cloud_run_revision\" AND jsonPayload.total_tokens:*"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "1"
  }

  value_extractor = "EXTRACT(jsonPayload.total_tokens)"

  bucket_options {
    exponential_buckets {
      num_finite_buckets = 64
      growth_factor      = 1.4
      scale              = 10.0
    }
  }
}

# ==============================================================================
# Google Cloud Monitoring Custom Service
# ==============================================================================

resource "google_monitoring_custom_service" "catalog_agent_service" {
  project      = var.project_id
  service_id   = "catalog-agent-service"
  display_name = "TechBuy Catalog Comparison Agent"
}

# ==============================================================================
# Service Level Objectives (SLOs) — 99% SLA (goal = 0.99, rolling_period_days = 30)
# ==============================================================================

# Latency SLO: 99% of queries respond in <= 3,000ms (Slide 1/7 North Star SLA)
resource "google_monitoring_slo" "latency_slo" {
  project             = var.project_id
  service             = google_monitoring_custom_service.catalog_agent_service.service_id
  slo_id              = "latency-p99-3000ms"
  display_name        = "99% Latency <= 3000ms (Slide 1/7 SLA)"
  goal                = 0.99
  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.catalog_agent_latency_ms.name}\" resource.type=\"cloud_run_revision\""
      range {
        max = 3000.0
      }
    }
  }
}

# Per-Query Token SLO: 99% of queries consume <= 2,500 tokens (anchored to Slide 4's 2,060 avg)
resource "google_monitoring_slo" "token_slo" {
  project             = var.project_id
  service             = google_monitoring_custom_service.catalog_agent_service.service_id
  slo_id              = "per-query-tokens-2500"
  display_name        = "99% Per-Query Tokens <= 2500 (Slide 4 Baseline)"
  goal                = 0.99
  rolling_period_days = 30

  request_based_sli {
    distribution_cut {
      distribution_filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.catalog_agent_total_tokens.name}\" resource.type=\"cloud_run_revision\""
      range {
        max = 2500.0
      }
    }
  }
}

# ==============================================================================
# Google Cloud Monitoring Alert Policies — Multi-Window SLO Burn Rate & FinOps
# ==============================================================================

# Multi-Window Burn-Rate Alert Policy for Latency SLO (1h fast burn 14.4x, 6h slow burn 6.0x)
resource "google_monitoring_alert_policy" "latency_slo_burn_rate" {
  project      = var.project_id
  display_name = "Latency SLO Multi-Window Burn Rate (P99 <= 3000ms)"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Fast Burn — 14.4x over 1h (2% error budget consumed)"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.latency_slo.name}\", \"3600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 14.4
      duration        = "0s"
      trigger {
        count = 1
      }
    }
  }

  conditions {
    display_name = "Slow Burn — 6.0x over 6h (5% error budget consumed)"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.latency_slo.name}\", \"21600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 6.0
      duration        = "0s"
      trigger {
        count = 1
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      # Latency SLO Burn Rate Alert
      The 99% Latency <= 3000ms SLO error budget is burning faster than sustainable:
      - **Fast Burn (14.4x over 1h)**: Consuming 2% of total 30-day budget in 1 hour (exhaustion in ~2 days).
      - **Slow Burn (6.0x over 6h)**: Consuming 5% of total 30-day budget in 6 hours.
      Investigate Vertex AI Gemini response times, BigQuery query execution, and Cloud Run cold starts immediately.
    EOT
  }
}

# Multi-Window Burn-Rate Alert Policy for Token SLO (1h fast burn 14.4x, 6h slow burn 6.0x)
resource "google_monitoring_alert_policy" "token_slo_burn_rate" {
  project      = var.project_id
  display_name = "Per-Query Token SLO Multi-Window Burn Rate (Tokens <= 2500)"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Fast Burn — 14.4x over 1h (2% error budget consumed)"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.token_slo.name}\", \"3600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 14.4
      duration        = "0s"
      trigger {
        count = 1
      }
    }
  }

  conditions {
    display_name = "Slow Burn — 6.0x over 6h (5% error budget consumed)"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.token_slo.name}\", \"21600s\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 6.0
      duration        = "0s"
      trigger {
        count = 1
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      # Per-Query Token SLO Burn Rate Alert
      The 99% Per-Query Tokens <= 2500 SLO error budget is burning faster than sustainable:
      - **Fast Burn (14.4x over 1h)**: Consuming 2% of budget in 1 hour.
      - **Slow Burn (6.0x over 6h)**: Consuming 5% of budget in 6 hours.
      Indicates token bloat or unconstrained prompt synthesis in ADK comparative reasoning.
    EOT
  }
}

# Hourly FinOps Token Quota Burn Rate Alert Policy
# Anchored to Slide 4's 206M tokens/month = 286,111 tokens/hr baseline:
# - 3x Slow Burn baseline drift = 858,333 tokens/hr
# - 10x Fast Burn Black Friday burst = 2,861,110 tokens/hr
resource "google_monitoring_alert_policy" "finops_token_quota_burn_rate" {
  project      = var.project_id
  display_name = "FinOps Hourly Token Quota Burn Rate (206M/mo Baseline)"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "FinOps Fast Burn — 10x Black Friday Burst (2,861,110 tokens/hr)"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.catalog_agent_total_tokens.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 2861110
      duration        = "0s"
      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
      trigger {
        count = 1
      }
    }
  }

  conditions {
    display_name = "FinOps Slow Burn — 3x Baseline Drift (858,333 tokens/hr)"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.catalog_agent_total_tokens.name}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 858333
      duration        = "0s"
      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
      trigger {
        count = 1
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      # FinOps Token Quota Burn Rate Alert
      Token consumption is exceeding baseline projections anchored to Slide 4's 206M tokens/month (286,111 tokens/hr baseline):
      - **10x Fast Burn (>= 2,861,110 tokens/hr)**: Extreme spike / runaway generation / DDoS event.
      - **3x Slow Burn (>= 858,333 tokens/hr)**: Sustained usage drift threatening monthly budget envelopes.
      Investigate query volumes, cache hit rates, and model routing immediately.
    EOT
  }
}
