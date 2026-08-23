# Deployment placeholders

Fill these values in `infrastructure/terraform/environments/dev/terraform.tfvars`. Do not commit
the populated file.

| Placeholder | Source / decision |
|---|---|
| `<GCP_PROJECT_ID>` | Existing dev Google Cloud project with billing enabled. |
| `<GCP_REGION>` / `<REGION>` | Region shared by Cloud Run, Artifact Registry, Cloud SQL, and Memory Bank. |
| `<PROJECT_NUMBER>` | `gcloud projects describe <PROJECT_ID> --format=value(projectNumber)`. |
| `<ADMIN_DNS_NAME>` | DNS name you control for the IAP-protected console/load balancer. |
| `<IAP_OAUTH_CLIENT_ID>` | IAP OAuth client ID for the load-balancer backends. |
| `<IAP_OAUTH_CLIENT_SECRET>` | Matching IAP client secret; supply via secure CI variables, never Git. |
| `<MEMORY_API_BACKEND_ID>` | Terraform output after the first infrastructure apply; use it to form `iap_jwt_audience`, then apply again. |
| `<ADMIN_GROUP_EMAIL>` | Google Group allowed through IAP. |
| `<PLATFORM_ADMIN_EMAIL>` | Verified IAP email mapped to `PLATFORM_ADMIN`; add domain owners as needed. |
| `<AGENT_PLATFORM_MEMORY_BANK_ID>` | Existing Agent Runtime / reasoning engine ID whose context spec contains the approved profiles. |
| `<MEMORY_API_CLOUD_RUN_URL>` | Terraform `memory_api_url` output after the first apply; use as the workload ID-token audience, then apply again. |
| `<GEMINI_MODEL>` | Approved Vertex Gemini model, for example the project-standard flash model. |
| `<REFERENCE_AGENT_SERVICE_ACCOUNT_EMAIL>` | Terraform output `reference_agent_service_account`. Use in agent principal overrides. |
| `<CUSTOMER_AGENT_SERVICE_ACCOUNT_EMAIL>` | Workload identity for a deployed Customer acceptance agent, or omit that override outside the full acceptance environment. |
| `<INVENTORY_AGENT_SERVICE_ACCOUNT_EMAIL>` | Workload identity for a deployed Inventory acceptance agent, or omit that override outside the full acceptance environment. |
| `<REPOSITORY>` | Terraform-created Artifact Registry repository output. |
| `<IMMUTABLE_TAG>` | Commit SHA or immutable release tag; do not use `latest`. |
| `<CHANNEL_ID>` | Existing Cloud Monitoring email, PagerDuty, Slack, or Pub/Sub notification channel ID. |
| `<TERRAFORM_STATE_BUCKET>` | Pre-created, versioned, access-logged GCS Terraform state bucket. |

Also supply these only when running the live Phase 9 scenario:

- `GROCERY_AGENT_TOKEN`
- `CUSTOMER_AGENT_TOKEN`
- `INVENTORY_AGENT_TOKEN`
- `PHASE9_ADMIN_TOKEN`
- ADC for the configured dev project

The first apply can use temporary syntactically valid values for the two derived audiences. Replace
them with the exact Terraform outputs before testing any authenticated request. DNS must point
`<ADMIN_DNS_NAME>` to Terraform output `frontend_ip`. The managed certificate will
remain provisioning until DNS resolves.
