data "google_project" "current" {
  project_id = var.project_id
}

locals {
  name                   = "${var.name_prefix}-${var.environment}"
  control_plane_api_name = "${local.name}-control-plane-api"
  admin_name             = "${local.name}-admin"
  agent_name             = "${local.name}-reference-agent"
  iap_service_account = (
    "service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"
  )
  required_apis = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "compute.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each           = local.required_apis
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = "${local.name}-containers"
  format        = "DOCKER"
  depends_on    = [google_project_service.required]
}

resource "google_compute_network" "platform" {
  project                 = var.project_id
  name                    = "${local.name}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.required]
}

resource "google_compute_subnetwork" "platform" {
  project                  = var.project_id
  region                   = var.region
  name                     = "${local.name}-subnet"
  network                  = google_compute_network.platform.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

resource "google_compute_global_address" "private_services" {
  project       = var.project_id
  name          = "${local.name}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.platform.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.platform.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

resource "random_password" "database" {
  length  = 32
  special = false
}

resource "google_sql_database_instance" "postgres" {
  project             = var.project_id
  region              = var.region
  name                = "${local.name}-postgres"
  database_version    = "POSTGRES_16"
  deletion_protection = var.deletion_protection

  settings {
    tier              = var.database_tier
    availability_type = "ZONAL"
    disk_autoresize   = true
    disk_type         = "PD_SSD"
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true

    }
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.platform.id
      ssl_mode        = "ENCRYPTED_ONLY"

    }

  }
  depends_on = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "control_plane" {
  project  = var.project_id
  instance = google_sql_database_instance.postgres.name
  name     = "shared_memory"
}

resource "google_sql_user" "application" {
  project  = var.project_id
  instance = google_sql_database_instance.postgres.name
  name     = "shared_memory"
  password = random_password.database.result
}

resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "${local.name}-database-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  secret_data = format(
    "postgresql+asyncpg://%s:%s@/%s?host=/cloudsql/%s",
    google_sql_user.application.name,
    random_password.database.result,
    google_sql_database.control_plane.name,
    google_sql_database_instance.postgres.connection_name,
  )
}

resource "google_secret_manager_secret" "admin_bindings" {
  project   = var.project_id
  secret_id = "${local.name}-admin-role-bindings"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "admin_bindings" {
  secret      = google_secret_manager_secret.admin_bindings.id
  secret_data = var.admin_role_bindings_json
}

resource "google_secret_manager_secret" "agent_principals" {
  project   = var.project_id
  secret_id = "${local.name}-agent-principal-overrides"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "agent_principals" {
  secret      = google_secret_manager_secret.agent_principals.id
  secret_data = var.agent_principal_overrides_json
}

resource "google_service_account" "control_plane_api" {
  project      = var.project_id
  account_id   = "${substr(local.name, 0, 18)}-memory"
  display_name = "Control Plane API ${var.environment}"
}

resource "google_service_account" "reference_agent" {
  project      = var.project_id
  account_id   = "${substr(local.name, 0, 18)}-agent"
  display_name = "Reference Agent ${var.environment}"
}

resource "google_service_account" "admin_console" {
  project      = var.project_id
  account_id   = "${substr(local.name, 0, 18)}-admin"
  display_name = "Memory Admin Console ${var.environment}"
}

resource "google_service_account" "migration" {
  project      = var.project_id
  account_id   = "${substr(local.name, 0, 18)}-migration"
  display_name = "Memory schema migration ${var.environment}"
}

locals {
  control_plane_api_roles = toset([
    "roles/aiplatform.user",
    "roles/cloudsql.client",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
    "roles/secretmanager.secretAccessor",
  ])
  reference_agent_roles = toset([
    "roles/aiplatform.user",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
  ])
  migration_roles = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/secretmanager.secretAccessor",
  ])
}

resource "google_project_iam_member" "control_plane_api" {
  for_each = local.control_plane_api_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.control_plane_api.email}"
}

resource "google_project_iam_member" "reference_agent" {
  for_each = local.reference_agent_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.reference_agent.email}"
}

resource "google_project_iam_member" "migration" {
  for_each = local.migration_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.migration.email}"
}
