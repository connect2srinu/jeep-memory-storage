# Shared Memory Platform: DevOps Resources and Deployment Lifecycle

## Resources

| Layer | Resource | Creation time |
|---|---|---|
| Foundation | GCP project, APIs, IAM, networking | Environment bootstrap |
| Agent Platform | Existing Agent Engine with Memory Bank | Platform provisioning |
| Data | PostgreSQL/Cloud SQL | Application deployment |
| Runtime | Memory API and Admin Console | Application deployment |
| Control plane | Domains, schemas, agents, grants, policies | Admin Console or authorized Admin API activation |
| Memory | User-scoped memories/profiles | First authorized interaction; lazy |

## Local modes

Mock-backed:

```bash
docker compose up --build
```

Vertex-backed:

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export AGENT_PLATFORM_MEMORY_BANK_ID=YOUR_AGENT_ENGINE_ID
docker compose -f docker-compose.yml -f docker-compose.vertex.yml up --build
```

PostgreSQL is internal to the Compose network, avoiding host port 5432 collisions.

## Activation lifecycle

1. UI preview validates without mutation.
2. Activation commits control-plane resources and audit in PostgreSQL.
3. Owned grants are approved; shared requests remain pending.
4. Vertex mode updates the existing Agent Engine `context_spec` with all active schemas.
5. No user profile is created.
6. The first authorized ADK write creates exact-scope memory and submits an event.
7. Managed profile consolidation occurs asynchronously.

`PROVISIONED` proves the context update returned successfully. `REGISTERED_LOCAL` proves only local
mock registration.

## Required configuration

```text
DATABASE_URL
MEMORY_BACKEND
GOOGLE_CLOUD_PROJECT
GOOGLE_CLOUD_LOCATION
AGENT_PLATFORM_MEMORY_BANK_ID
GOOGLE_APPLICATION_CREDENTIALS
AUTH_ENABLED
GOOGLE_ID_TOKEN_AUDIENCE
ADMIN_ROLE_BINDINGS_JSON
```

Use Secret Manager/workload identity in production; do not package credentials into images.

## Release pipeline

1. run Python and frontend tests;
2. build immutable images;
3. plan infrastructure changes;
4. deploy database migrations;
5. deploy Memory API, then Admin Console and agents;
6. apply approved control-plane setup through the Admin API;
7. activate/provision approved schemas;
8. run health and authorization smoke tests;
9. run one environment-gated Vertex write/recall scenario;
10. monitor errors, latency, provider operations, and audit.

## Rollback

Roll back application images independently from control-plane data. Do not delete schema versions or
Memory Bank data as an application rollback. Retire/revoke new controls, restore the previous active
policy/schema version, and correct user data through an audited owner-domain workflow.

## Production gate

- verified service identities and least-privilege IAM;
- private connectivity and TLS;
- managed PostgreSQL backups and migration rehearsal;
- schema-version approval and rollback;
- alerting on `401`, `403`, `409`, provider failures, and latency;
- retention, export, correction, and deletion procedures;
- live multi-user/multi-domain isolation tests;
- ADK evals covering correct tool selection without schema IDs.

Related: `deployment-operations.md`, `deployment-placeholders.md`, and `vertex-memory-bank.md`.
