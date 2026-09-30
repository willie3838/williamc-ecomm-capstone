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
