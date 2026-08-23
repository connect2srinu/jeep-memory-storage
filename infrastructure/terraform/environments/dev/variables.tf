variable "project_id" {
  type = string
}
variable "region" {
  type    = string
  default = "us-central1"
}
variable "admin_domain" {
  type = string
}
variable "iap_oauth_client_id" {
  type = string
}
variable "iap_oauth_client_secret" {
  type      = string
  sensitive = true
}
variable "iap_jwt_audience" {
  type = string
}
variable "iap_members" {
  type = set(string)
}
variable "admin_role_bindings_json" {
  type      = string
  sensitive = true
}
variable "agent_principal_overrides_json" {
  type      = string
  sensitive = true
}
variable "memory_bank_resource_id" {
  type = string
}
variable "memory_api_audience" {
  type = string
}
variable "gemini_model" {
  type    = string
  default = "gemini-3.5-flash"
}
variable "memory_api_image" {
  type = string
}
variable "admin_console_image" {
  type = string
}
variable "reference_agent_image" {
  type = string
}
variable "notification_channel_ids" {
  type    = list(string)
  default = []
}
variable "deletion_protection" {
  type    = bool
  default = true
}
