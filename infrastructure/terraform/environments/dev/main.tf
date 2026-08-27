module "platform" {
  source = "../../modules/platform"

  project_id                     = var.project_id
  region                         = var.region
  environment                    = "dev"
  name_prefix                    = "geap-memory"
  admin_domain                   = var.admin_domain
  iap_oauth_client_id            = var.iap_oauth_client_id
  iap_oauth_client_secret        = var.iap_oauth_client_secret
  iap_jwt_audience               = var.iap_jwt_audience
  iap_members                    = var.iap_members
  admin_role_bindings_json       = var.admin_role_bindings_json
  agent_principal_overrides_json = var.agent_principal_overrides_json
  memory_bank_resource_id        = var.memory_bank_resource_id
  control_plane_api_audience     = var.control_plane_api_audience
  gemini_model                   = var.gemini_model
  control_plane_api_image        = var.control_plane_api_image
  admin_console_image            = var.admin_console_image
  reference_agent_image          = var.reference_agent_image
  notification_channel_ids       = var.notification_channel_ids
  deletion_protection            = var.deletion_protection
}
