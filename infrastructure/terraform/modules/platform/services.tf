resource "google_cloud_run_v2_service" "control_plane_api" {
  project             = var.project_id
  location            = var.region
  name                = local.control_plane_api_name
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = var.deletion_protection

  template {
    service_account = google_service_account.control_plane_api.email
    timeout         = "300s"
    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.platform.name
        subnetwork = google_compute_subnetwork.platform.name

      }
      egress = "PRIVATE_RANGES_ONLY"

    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }

    }
    containers {
      image = var.control_plane_api_image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu = "1", memory = "2Gi"
        }
        cpu_idle = true
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name  = "MEMORY_BACKEND"
        value = "vertex"
      }
      env {
        name  = "AUTH_ENABLED"
        value = "true"
      }
      env {
        name  = "ADMIN_AUTH_MODE"
        value = "iap"
      }
      env {
        name  = "IAP_JWT_AUDIENCE"
        value = var.iap_jwt_audience
      }
      env {
        name  = "GOOGLE_ID_TOKEN_AUDIENCE"
        value = var.control_plane_api_audience
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "AGENT_PLATFORM_MEMORY_BANK_ID"
        value = var.memory_bank_resource_id
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }

      }
      env {
        name = "ADMIN_ROLE_BINDINGS_JSON"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.admin_bindings.secret_id
            version = "latest"
          }
        }

      }
      startup_probe {
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 24
        http_get {
          path = "/healthz"
          port = 8080
        }

      }
      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
      }

    }

  }
  depends_on = [google_project_iam_member.control_plane_api]
}

resource "google_cloud_run_v2_service" "admin_console" {
  project             = var.project_id
  location            = var.region
  name                = local.admin_name
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = var.deletion_protection
  template {
    service_account = google_service_account.admin_console.email
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }
    containers {
      image = var.admin_console_image
      ports {
        container_port = 80
      }
      resources {
        limits = {
          cpu = "1", memory = "512Mi"
        }
        cpu_idle = true
      }
      liveness_probe {
        http_get {
          path = "/"
          port = 80
        }
      }

    }

  }
  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service" "reference_agent" {
  project             = var.project_id
  location            = var.region
  name                = local.agent_name
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection
  template {
    service_account = google_service_account.reference_agent.email
    timeout         = "300s"
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.platform.name
        subnetwork = google_compute_subnetwork.platform.name

      }
      egress = "PRIVATE_RANGES_ONLY"

    }
    containers {
      image = var.reference_agent_image
      ports {
        container_port = 8000
      }
      resources {
        limits = {
          cpu = "1", memory = "4Gi"
        }
        cpu_idle = true
      }
      env {
        name  = "CONTROL_PLANE_API_URL"
        value = google_cloud_run_v2_service.control_plane_api.uri
      }
      env {
        name  = "CONTROL_PLANE_API_AUDIENCE"
        value = google_cloud_run_v2_service.control_plane_api.uri
      }
      env {
        name  = "REFERENCE_AGENT_ID"
        value = "grocery-agent"
      }
      env {
        name  = "ADK_APP_NAME"
        value = "grocery_shared_preferences"
      }
      env {
        name  = "PREFERENCE_DOMAIN"
        value = "grocery"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }

    }

  }
  depends_on = [google_project_iam_member.reference_agent]
}

resource "google_cloud_run_v2_job" "migration" {
  project             = var.project_id
  location            = var.region
  name                = "${local.name}-migrate"
  deletion_protection = var.deletion_protection
  template {
    template {
      service_account = google_service_account.migration.email
      timeout         = "900s"
      max_retries     = 1
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres.connection_name]
        }

      }
      containers {
        image   = var.control_plane_api_image
        command = ["/bin/sh", "-c"]
        args = [
          "alembic -c apps/control-plane-api/alembic.ini upgrade head"
        ]
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }

        }
        env {
          name = "AGENT_PRINCIPAL_OVERRIDES_JSON"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.agent_principals.secret_id
              version = "latest"
            }
          }

        }

      }

    }

  }
}

resource "google_cloud_run_v2_service_iam_member" "reference_to_control_plane_api" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.control_plane_api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.reference_agent.email}"
}

resource "google_compute_region_network_endpoint_group" "control_plane_api" {
  project               = var.project_id
  region                = var.region
  name                  = "${local.name}-memory-neg"
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.control_plane_api.name
  }
}

resource "google_compute_region_network_endpoint_group" "admin_console" {
  project               = var.project_id
  region                = var.region
  name                  = "${local.name}-admin-neg"
  network_endpoint_type = "SERVERLESS"
  cloud_run {
    service = google_cloud_run_v2_service.admin_console.name
  }
}

resource "google_compute_backend_service" "control_plane_api" {
  project               = var.project_id
  name                  = "${local.name}-memory-backend"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.control_plane_api.id
  }
  iap {
    enabled              = true
    oauth2_client_id     = var.iap_oauth_client_id
    oauth2_client_secret = var.iap_oauth_client_secret

  }
}

resource "google_compute_backend_service" "admin_console" {
  project               = var.project_id
  name                  = "${local.name}-admin-backend"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.admin_console.id
  }
  iap {
    enabled              = true
    oauth2_client_id     = var.iap_oauth_client_id
    oauth2_client_secret = var.iap_oauth_client_secret

  }
}

resource "google_cloud_run_v2_service_iam_member" "iap_memory_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.control_plane_api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.iap_service_account}"
}

resource "google_cloud_run_v2_service_iam_member" "iap_admin_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.admin_console.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.iap_service_account}"
}

resource "google_iap_web_backend_service_iam_member" "memory_users" {
  for_each            = var.iap_members
  project             = var.project_id
  web_backend_service = google_compute_backend_service.control_plane_api.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}

resource "google_iap_web_backend_service_iam_member" "admin_users" {
  for_each            = var.iap_members
  project             = var.project_id
  web_backend_service = google_compute_backend_service.admin_console.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}

resource "google_compute_global_address" "frontend" {
  project = var.project_id
  name    = "${local.name}-frontend-ip"
}

resource "google_compute_managed_ssl_certificate" "frontend" {
  project = var.project_id
  name    = "${local.name}-certificate"
  managed {
    domains = [var.admin_domain]
  }
}

resource "google_compute_url_map" "frontend" {
  project         = var.project_id
  name            = "${local.name}-url-map"
  default_service = google_compute_backend_service.admin_console.id
  host_rule {
    hosts        = [var.admin_domain]
    path_matcher = "platform"
  }
  path_matcher {
    name            = "platform"
    default_service = google_compute_backend_service.admin_console.id
    path_rule {
      paths   = ["/api/*", "/healthz", "/internal/*"]
      service = google_compute_backend_service.control_plane_api.id

    }

  }
}

resource "google_compute_target_https_proxy" "frontend" {
  project          = var.project_id
  name             = "${local.name}-https-proxy"
  url_map          = google_compute_url_map.frontend.id
  ssl_certificates = [google_compute_managed_ssl_certificate.frontend.id]
}

resource "google_compute_global_forwarding_rule" "https" {
  project               = var.project_id
  name                  = "${local.name}-https"
  ip_address            = google_compute_global_address.frontend.id
  port_range            = "443"
  target                = google_compute_target_https_proxy.frontend.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
