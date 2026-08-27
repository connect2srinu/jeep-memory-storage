# Deployment and Operations Runbook

## Safety boundary

Terraform, cloud deployment, schema provisioning, live memory writes, and teardown mutate external
state. Run them only in the intended project/environment with reviewed placeholders and approvals.

## 1. Run the complete application locally with Docker Compose

### Prerequisites

- Docker Engine or Docker Desktop with Compose v2;
- ports `3000`, `8000`, and `8080` available on the host;
- Google Cloud CLI and Application Default Credentials only for Vertex-backed mode;
- a Vertex AI Agent Engine resource with Memory Bank enabled only for Vertex-backed mode.

PostgreSQL is intentionally not published on host port `5432`; it is reachable only as `postgres`
inside the Compose network. This avoids conflicts with an existing local PostgreSQL installation.

### Mock-backed stack

From the repository root:

```bash
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, Control Plane API, and Admin Console. Confirm the stack:

```bash
docker compose ps
curl http://localhost:8080/healthz
```

Open:

- Admin Console: `http://localhost:3000`
- Control Plane API health: `http://localhost:8080/healthz`
- Control Plane API OpenAPI: `http://localhost:8080/docs`

To include the reference ADK agent, set `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and
`GEMINI_MODEL` in `.env`, then run:

```bash
docker compose --profile agent up --build
```

Open `http://localhost:8000/dev-ui/?app=reference_agent`. The default Compose registration is
`grocery-agent` in the `grocery` domain. Change `REFERENCE_AGENT_ID`, `ADK_APP_NAME`, and
`PREFERENCE_DOMAIN` in Compose or run ADK Web directly when testing a newly onboarded agent.

### Vertex-backed local stack

Authenticate on the host and fill the cloud identifiers:

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export AGENT_PLATFORM_MEMORY_BANK_ID=YOUR_AGENT_ENGINE_ID

docker compose \
  -f docker-compose.yml \
  -f docker-compose.vertex.yml \
  --profile agent \
  up --build
```

The override mounts the standard gcloud Application Default Credentials file into the Control Plane API.
Activation must return `PROVISIONED` with backend `VertexMemoryBankStore`. `REGISTERED_LOCAL`
means the API is still using the mock backend.

### Stop, restart, and troubleshoot

```bash
docker compose logs -f control-plane-api admin-console reference-agent
docker compose restart control-plane-api
docker compose down
```

Use `docker compose down -v` only when intentionally deleting the local PostgreSQL volume. If a
host port is already occupied, identify and stop that process or change only the affected host-side
port mapping; do not expose the Compose PostgreSQL service unless an external client requires it.

## 2. Validate before deployment

```bash
PYTHONPATH=apps/control-plane-api/app:. .venv/bin/python -m pytest -q apps/control-plane-api/tests
PYTHONPATH=apps/reference-agent/app:. .venv/bin/python -m pytest -q apps/reference-agent/tests

cd apps/admin-console
npm run typecheck
npm test
npm run build
```

## 3. GCP resources and ownership

Use a separate GCP project per environment when production isolation is required. The checked-in
Terraform module creates the following resources in the selected project:

| Layer | Resources created by Terraform |
|---|---|
| APIs | Vertex AI, Artifact Registry, Cloud Build, Compute, IAP, Logging, Monitoring, Cloud Run, Secret Manager, Service Networking, and Cloud SQL Admin APIs |
| Images | Regional Artifact Registry Docker repository |
| Network | Custom VPC, subnet with Private Google Access, private service range, and Service Networking peering |
| Database | Private-IP PostgreSQL 16 Cloud SQL instance, `shared_memory` database/user, automated backups, and point-in-time recovery |
| Secrets | Database URL, admin role bindings, and agent-principal mappings in Secret Manager |
| Identities | Separate service accounts for Control Plane API, Admin Console, reference agent, and database migration job, with least-purpose IAM bindings |
| Runtime | Cloud Run services for Control Plane API, Admin Console, and reference agent, plus a Cloud Run migration/bootstrap job |
| Edge security | Serverless NEGs, external HTTPS load balancer, managed certificate, URL map, IAP, and invoker bindings |
| Operations | Log-based metrics, alert policies, and monitoring dashboard |

The following are prerequisites or lifecycle resources and are not created by the current Terraform
module:

1. the GCP project, billing account association, and deployer permissions;
2. the Terraform state bucket and `backend.tf` configuration;
3. the public DNS zone/record for `admin_domain`;
4. the IAP OAuth client ID and secret;
5. notification channels referenced by `notification_channel_ids`;
6. a Vertex AI Agent Engine resource with Memory Bank enabled;
7. container builds and immutable image pushes before `terraform apply`;
8. additional business agents deployed to Cloud Run or Agent Runtime;
9. production schema approvals and user-scoped memory profiles, which remain lazy and are created by
   authorized runtime use rather than infrastructure provisioning.

Do not place OAuth secrets, database passwords, or tokens in committed `.tfvars` files. Use your
approved secret delivery mechanism and protect Terraform state because it can contain sensitive
values.

## 4. Configure the environment

Complete and review these deployment inputs before any cloud mutation:

```text
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
AGENT_PLATFORM_MEMORY_BANK_ID=
GOOGLE_ID_TOKEN_AUDIENCE=
CONTROL_PLANE_API_SERVICE_ACCOUNT=
ADMIN_CONSOLE_SERVICE_ACCOUNT=
REFERENCE_AGENT_SERVICE_ACCOUNT=
DATABASE_INSTANCE=
DATABASE_NAME=shared_memory
ARTIFACT_REGISTRY_REPOSITORY=
CONTROL_PLANE_API_IMAGE=
ADMIN_CONSOLE_IMAGE=
REFERENCE_AGENT_IMAGE=
ADMIN_ROLE_BINDINGS_JSON=
```

For an ADK consumer, also record:

```text
REFERENCE_AGENT_ID=
PREFERENCE_DOMAIN=
ADK_APP_NAME=
CONTROL_PLANE_API_URL=
CONTROL_PLANE_API_AUDIENCE=
```

Do not add schema IDs to agent environment variables or prompts. The platform derives schema
selection from the registered agent, ownership, mappings, and active grants. Local Vertex-backed
Compose also needs Application Default Credentials at the standard gcloud path mounted by
`docker-compose.vertex.yml`.

Copy and fill the development Terraform inputs:

```bash
cd infrastructure/terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
cp backend.tf.example backend.tf
```

On a new environment, initialize Terraform and create the API/Artifact Registry bootstrap target
first, because the application services require images that do not exist until the repository is
available:

```bash
terraform -chdir=infrastructure/terraform/environments/dev init
terraform -chdir=infrastructure/terraform/environments/dev apply \
  -target=module.platform.google_artifact_registry_repository.images
```

Review and approve the targeted plan just as you would a full plan. Then build and push the three
immutable images from the repository root:

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export ARTIFACT_REPOSITORY=geap-memory-dev-containers
export IMAGE_TAG=YOUR_IMMUTABLE_COMMIT_SHA
./infrastructure/cloud-run/build-images.sh
```

Copy the resulting image URIs into `terraform.tfvars`. Review the script and completed deployment
inputs before allowing any cloud mutation.

## 5. Plan and deploy

From the repository root:

```bash
terraform -chdir=infrastructure/terraform/environments/dev init
terraform -chdir=infrastructure/terraform/environments/dev fmt -check -recursive
terraform -chdir=infrastructure/terraform/environments/dev validate
terraform -chdir=infrastructure/terraform/environments/dev plan -out=dev.tfplan
```

Review the plan and obtain deployment approval before running:

```bash
terraform -chdir=infrastructure/terraform/environments/dev apply dev.tfplan
```

After Terraform completes:

1. point the `admin_domain` DNS A record at `terraform output -raw frontend_ip` and wait for the
   managed certificate to become active;
2. replace any bootstrap audience placeholders with the actual Cloud Run URL and IAP backend ID
   from Terraform outputs, then plan and apply that configuration update;
3. execute the migration job returned by `terraform output -raw migration_job` with
   `gcloud run jobs execute JOB --region REGION --wait`;
4. wait for the Control Plane API health check to succeed;
5. verify Admin Console access through the HTTPS load balancer and IAP;
6. deploy or configure additional consumer agents in Cloud Run or Agent Runtime;
7. map each deployed agent identity in `AGENT_PRINCIPAL_OVERRIDES_JSON`;
8. create or promote approved control-plane records through the Admin API and activate/provision domain schemas;
9. approve only the required cross-domain shared-schema access;
10. run the smoke test below before directing production traffic.

The Control Plane API must use `MEMORY_BACKEND=vertex` in the cloud-backed environment. Successful guided
activation returns `PROVISIONED`; `REGISTERED_LOCAL` is not an acceptable production result.

## 6. Smoke test

Use a dedicated test user and domain:

1. resolve and verify `writablePreferences`;
2. submit an update without `schemaId`;
3. confirm the correct same-domain schema was selected;
4. resolve in a later Session;
5. verify another user cannot read it;
6. verify a shared read-only schema cannot be written;
7. inspect audit and correlation IDs.

Allow for asynchronous managed-profile consolidation. Do not repeatedly create profiles when
polling; use read-only resolve/inspection.

## 7. Observe

Monitor API availability, latency, `4xx`/`5xx` rates, authorization denials, ambiguous/unknown write
routing, provider operations, database saturation, schema provisioning failures, and audit volume.
Do not log raw sensitive preference values unless an approved policy explicitly allows it.

## 8. Roll back

Roll back application images first. Revoke/retire new grants and policies or restore the prior active
schema version; do not delete Memory Bank data as a deployment rollback. Correct user data through
audited owner-domain operations.

## 9. Teardown

Resolve exact targets before destruction. Preserve required exports and audit evidence, revoke
access, drain traffic, remove applications, then remove infrastructure according to retention policy.
