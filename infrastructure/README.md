# Infrastructure

Infrastructure code provisions the deployable platform foundation: network/IAM integration,
database, Memory API, Admin Console, and related runtime configuration. Domain schemas and grants
are database-backed control-plane resources created through the Admin Console or Admin API after
the application is healthy.

Before applying changes, complete `docs/deployment-placeholders.md`, validate tests,
and review the exact project and region.

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

Apply only after approval. Deployment order is database/migrations, Memory API, Admin Console,
consumer agents, then schema activation/provisioning. See `docs/deployment-operations.md`.

The module provisions the Artifact Registry repository, VPC/private service networking, private
Cloud SQL PostgreSQL, Secret Manager entries, workload service accounts and IAM, three Cloud Run
services, a migration job, HTTPS load balancer/IAP, and monitoring. The GCP project, Terraform state
bucket, DNS record, IAP OAuth client, notification channels, Vertex Agent Engine/Memory Bank, and
container image builds must exist or be supplied separately.
