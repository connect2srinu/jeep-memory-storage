# Infrastructure

Infrastructure code provisions the deployable platform foundation: network/IAM integration,
database, Memory API, Admin Console, and related runtime configuration. Domain schemas and grants
are control-plane resources activated after the application is healthy.

Before applying changes, complete `docs/deployment-placeholders.md`, validate contracts and tests,
and review the exact project and region.

```bash
terraform -chdir=infrastructure/terraform init
terraform -chdir=infrastructure/terraform validate
terraform -chdir=infrastructure/terraform plan -var-file=ENV.tfvars
```

Apply only after approval. Deployment order is database/migrations, Memory API, Admin Console,
consumer agents, then schema activation/provisioning. See `docs/deployment-operations.md`.
