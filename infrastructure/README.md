# Development deployment

`terraform/environments/dev` composes the reusable `modules/platform` module. It defines required
APIs, four least-privilege service accounts, Artifact Registry, private networking, private Cloud
SQL PostgreSQL, Secret Manager values, three Cloud Run services, a migration job, HTTPS load
balancing with IAP, alerts, and a dashboard.

Terraform is declarative only. Nothing in this directory applies itself. Copy
`terraform.tfvars.example` to an ignored `terraform.tfvars`, fill the documented placeholders, and
follow `docs/deployment-operations.md`.

The external HTTPS load balancer serves the Admin Console by default and routes `/api/*`,
`/healthz`, and `/internal/*` to the Memory API. Both backends require IAP. The Reference Agent uses
the authenticated direct Memory API Cloud Run URL and has `roles/run.invoker`; it receives no
Memory Bank resource administration role.
