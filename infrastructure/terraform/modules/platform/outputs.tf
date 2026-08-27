output "artifact_repository" {
  value = google_artifact_registry_repository.images.name
}
output "project_id" {
  value = var.project_id
}
output "frontend_ip" {
  value = google_compute_global_address.frontend.address
}
output "control_plane_api_url" {
  value = google_cloud_run_v2_service.control_plane_api.uri
}
output "reference_agent_url" {
  value = google_cloud_run_v2_service.reference_agent.uri
}
output "admin_url" {
  value = "https://${var.admin_domain}"
}
output "migration_job" {
  value = google_cloud_run_v2_job.migration.name
}
output "reference_agent_service_account" {
  value = google_service_account.reference_agent.email
}
output "iap_backend_service_id" {
  value = google_compute_backend_service.control_plane_api.generated_id
}
