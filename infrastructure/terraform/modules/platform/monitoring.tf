resource "google_logging_metric" "control_plane_api_errors" {
  project = var.project_id
  name    = "${local.name}-control-plane-api-errors"
  filter  = "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${local.control_plane_api_name}\" severity>=ERROR"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

  }
}

resource "google_monitoring_alert_policy" "control_plane_api_errors" {
  project      = var.project_id
  display_name = "${local.name}: Control Plane API errors"
  combiner     = "OR"
  conditions {
    display_name = "Error log rate"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.control_plane_api_errors.name}\" resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "60s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"

      }

    }

  }
  notification_channels = var.notification_channel_ids
  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "control_plane_api_5xx" {
  project      = var.project_id
  display_name = "${local.name}: Control Plane API 5xx responses"
  combiner     = "OR"
  conditions {
    display_name = "5xx request rate"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${local.control_plane_api_name}\" metric.labels.response_code_class=\"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"

      }

    }

  }
  notification_channels = var.notification_channel_ids
}

resource "google_monitoring_dashboard" "platform" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "${local.name} GEAP Platform"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          xPos = 0, yPos = 0, width = 6, height = 4
          widget = {
            title = "Control Plane API request rate"
            xyChart = {
              dataSets = [{
                plotType = "LINE"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${local.control_plane_api_name}\""
                    aggregation = {
                      alignmentPeriod = "60s", perSeriesAligner = "ALIGN_RATE"
                    }

                } }

              }]
            }

          }

        },
        {
          xPos = 6, yPos = 0, width = 6, height = 4
          widget = {
            title = "Control Plane API latency"
            xyChart = {
              dataSets = [{
                plotType = "LINE"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\" resource.labels.service_name=\"${local.control_plane_api_name}\""
                    aggregation = {
                      alignmentPeriod = "60s", perSeriesAligner = "ALIGN_PERCENTILE_95"
                    }

                } }

              }]
            }

          }

        }
      ]

    }

  })
}
