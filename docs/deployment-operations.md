# Phase 10 deployment and operations runbook

## Safety boundary

These commands target a development project. Review every Terraform plan. The repository never
runs `terraform apply`, a migration job, rollback, or teardown automatically. Production needs a
separate environment directory, remote state, approvals, backups, and change control.

## 1. Validate and build

```bash
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py --check
python scripts/validate_deployment_security.py
pytest -q
PYTHONPATH=apps/memory-api/app:. pytest -q apps/memory-api/tests
cd apps/reference-agent && .venv/bin/pytest -q && cd ../..
cd apps/admin-console && npm ci && npm test -- --run && npm run build && cd ../..
docker compose config
```

Create the Artifact Registry with a targeted reviewed Terraform apply if it does not already
exist, then set `ARTIFACT_REPOSITORY`, an immutable `IMAGE_TAG`, project, and region. Run
`infrastructure/cloud-run/build-images.sh`. Cloud Build users can submit `cloudbuild.yaml` instead.

## 2. Plan infrastructure

Copy `terraform.tfvars.example` to `terraform.tfvars`, fill the values in
`deployment-placeholders.md`, and configure the remote GCS backend from `backend.tf.example`.

```bash
cd infrastructure/terraform/environments/dev
terraform init
terraform fmt -check -recursive ../..
terraform validate
terraform plan -out=dev.tfplan
terraform show dev.tfplan
```

After approval, an operator may run `terraform apply dev.tfplan`. The first apply can use a
temporary syntactically valid IAP audience. Read `iap_backend_service_id` and `projectNumber`, set
the exact audience `/projects/PROJECT_NUMBER/global/backendServices/BACKEND_ID`, set
`memory_api_audience` to output `memory_api_url`, then plan and apply again before allowing
administrators or agents to use the services.

Point the admin DNS A record at output `frontend_ip` and wait for the managed certificate to become
ACTIVE.

## 3. Migrate and bootstrap

The Cloud Run service never runs schema migrations during startup. Execute the one-shot job after
the database backup and before shifting traffic:

```bash
gcloud run jobs execute "$(terraform output -raw migration_job)" \
  --project "$(terraform output -raw project_id 2>/dev/null || echo '<PROJECT_ID>')" \
  --region <REGION> --wait
```

The job applies Alembic, imports validated contracts idempotently, and maps registered agent IDs to
the service-account principals supplied in Secret Manager.

Export approved active profile schemas from the database and include the result in the controlled
Agent Runtime context update described in `vertex-memory-bank.md`. Profile instances remain lazy.

## 4. Smoke and acceptance

Grant the operator temporary `roles/run.invoker` only if needed, set the direct service URLs from
Terraform output, and run `infrastructure/cloud-run/smoke-test.sh`. Open
`https://<ADMIN_DNS_NAME>` as an IAP-authorized user and verify `/healthz`, domain listing, an access
approval, and audit history.

Run `scripts/run_phase9_acceptance.py` first against mock in Compose and then against the deployed
Vertex-backed API using the four ID-token variables documented in `phase9-acceptance.md`.

## Observability

Terraform creates a dashboard for Memory API request rate and p95 latency, an error-log metric, and
alerts for application errors and sustained 5xx responses. Correlation IDs are returned on every
API response and included in structured application events. Inspect:

- Cloud Monitoring → Dashboards → the environment Shared Memory Platform dashboard;
- Cloud Monitoring → Alerting for configured notification delivery;
- Cloud Logging with `resource.type="cloud_run_revision"` and the service name;
- Cloud Trace for the Reference Agent when ADK telemetry is enabled.

Prompt/response content capture is intentionally off. If enabled later, treat the GCS/BigQuery
completion store as sensitive user data and apply retention, regional, and access controls.

## Rollback

1. Stop new migrations and acceptance writers.
2. For application-only failures, list Cloud Run revisions and shift 100% traffic to the prior
   immutable revision with `gcloud run services update-traffic`.
3. Do not downgrade the database automatically. Use forward-compatible migrations and roll the app
   back only to a revision compatible with the current schema.
4. For a bad contract import, restore the approved contract commit, rerun the idempotent migration
   job, and verify grants/policies before traffic restoration.
5. Record revision names, image digests, migration version, and incident correlation IDs.

## Teardown

Take/export a Cloud SQL backup and preserve required audit data. Set `deletion_protection=false`,
review a destroy plan, then have an authorized operator run Terraform destroy. DNS records, the
remote state bucket, retained backups, Artifact Registry retention, and the externally managed
Memory Bank are deliberately outside automatic teardown; remove them only under their own data
retention approvals.
