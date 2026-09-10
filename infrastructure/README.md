# Infrastructure

Infrastructure code provisions the deployable platform foundation: network/IAM integration,
database, Control Plane API, Admin Console, and related runtime configuration. Domain schemas and grants
are database-backed control-plane resources created through the Admin Console or Admin API after
the application is healthy.

## Enable Google APIs for a new project

Use the API bootstrap script with the immutable Google Cloud project ID, not its display name:

```bash
./scripts/enable_google_agent_platform_apis.sh YOUR_PROJECT_ID
```

The default `platform` profile enables the Agent Platform API used by Agent Runtime, Memory Bank,
Sessions, and agent evaluation. It also enables Gemini Enterprise/Agent Designer and Agent Registry
APIs, plus the deployment, Cloud SQL, eventing, analytics, and observability APIs used by this
repository.

Review the command without changing the project:

```bash
./scripts/enable_google_agent_platform_apis.sh YOUR_PROJECT_ID --dry-run
```

Enable only the managed agent features without this repository's Cloud Run/Cloud SQL infrastructure:

```bash
./scripts/enable_google_agent_platform_apis.sh YOUR_PROJECT_ID --profile core
```

Agent Gateway and classic Dataflow-based model evaluation activate larger optional API sets:

```bash
./scripts/enable_google_agent_platform_apis.sh YOUR_PROJECT_ID \
  --with-gateway \
  --with-classic-model-evaluation \
  --create-service-identities
```

The script is safe to rerun. API enablement does not create resources, grant IAM roles, link billing,
enable the Agent Designer product toggle, or provide access to Preview/allowlisted features. Read the
completion checklist printed by the script and use Terraform for durable environment provisioning.

## Provision the platform

Before applying changes, complete the deployment-input checklist in
`docs/deployment-operations.md`, validate tests, and review the exact project and region.

```bash
cp infrastructure/terraform/environments/dev/terraform.tfvars.example \
  infrastructure/terraform/environments/dev/terraform.tfvars
cp infrastructure/terraform/environments/dev/backend.tf.example \
  infrastructure/terraform/environments/dev/backend.tf

terraform -chdir=infrastructure/terraform/environments/dev init
terraform -chdir=infrastructure/terraform/environments/dev fmt -check -recursive
terraform -chdir=infrastructure/terraform/environments/dev validate
terraform -chdir=infrastructure/terraform/environments/dev plan -out=dev.tfplan
```

Apply only after approval. Deployment order is database/migrations, Control Plane API, Admin Console,
consumer agents, then schema activation/provisioning. See `docs/deployment-operations.md`.

The module provisions the Artifact Registry repository, VPC/private service networking, private
Cloud SQL PostgreSQL, Secret Manager entries, workload service accounts and IAM, three Cloud Run
services, a migration job, HTTPS load balancer/IAP, and monitoring. The GCP project, Terraform state
bucket, DNS record, IAP OAuth client, notification channels, Vertex Agent Engine/Memory Bank, and
container image builds must exist or be supplied separately.
