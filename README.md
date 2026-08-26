# Shared Memory Platform for Google ADK

This repository implements a governed preference-memory service between ADK agents and Google
Vertex AI Memory Bank. Domain teams define preferences through the Admin Console and Admin API;
PostgreSQL is the control-plane source of truth. Agents consume one stable runtime API and never need Memory Bank SDKs, schema IDs, or
conflict-resolution logic.

## Current end-to-end flow

```text
Platform admin
  -> Admin Console: Create Memory Setup
  -> select organization and project
  -> preview and activate domain, preferences, schema, agent, grants, policies
  -> Memory API applies active schemas to Agent Engine context_spec
  -> profile instances remain lazy

User
  -> tells an ADK agent a preference in natural language
  -> agent chooses an attribute from writablePreferences
  -> Memory API resolves the single same-domain writable schema
  -> Memory Bank stores the explicit preference and ingests the event
  -> refreshed and later Sessions resolve the saved preference
```

The model and user do not provide a schema ID. The platform derives it from the authenticated
agent, its organization/project/domain ownership, active grants, and schema mappings. Unknown, read-only, cross-domain, and
ambiguous writes fail closed.

## Governance and Memory Bank scope

The control-plane hierarchy is:

```text
Organization (line of business)
└── Project
    ├── Agents
    └── Domains
        └── Schemas and preference fields
```

Projects and domains are authorization metadata in PostgreSQL; they are not Memory Bank partition
keys. The runtime authenticates the agent, derives its organization, and uses the exact Memory Bank
scope `organization_id + user_id`. This gives one canonical user profile per schema within an
organization while allowing the API to filter which project-owned schemas and fields an agent may
read or write. Legacy `appName` and `domain` request fields remain accepted for reference-agent
compatibility, but they do not determine the provider scope.

The initial implementation persists organizations/projects and validates that a domain and its
agents belong to the same organization/project. Cross-project field-level requests,
membership-derived RBAC enforcement, and implicit same-project grants remain subsequent
governance slices.

The **Organizations** screen presents a directory-first workspace instead of raw JSON. A platform
administrator selects an organization card to enter that organization's context. The left navigation
then exposes organization-specific **Overview**, **Projects**, and **Members & Roles** areas. Opening a
project adds project-specific **Overview**, **Domains**, **Agents**, and **Members & Roles** navigation.
From this workspace, a platform administrator can:

- add organization members with `OWNER`, `ADMIN`, or `VIEWER` roles;
- create projects with an owning team and description;
- see the projects and domains belonging to the organization;
- add project members and inspect their direct project roles.

Organizations are created as `ACTIVE` immediately in the POC because an organization approval
workflow is not implemented. Governed resources that use the existing lifecycle workflow continue
to start in `DRAFT` where applicable.

A principal must be an active organization member before being assigned directly to one of its
projects. Membership records are now durable and audited. This release still uses the existing
platform-admin authorization boundary for mutations; deriving every admin request from persisted
membership is the next security slice.

## Applications

| Component | Purpose | Local URL |
|---|---|---|
| `apps/admin-console` | Guided onboarding and advanced administration | `http://localhost:3000` |
| `apps/memory-api` | Control plane, authorization, resolution, and Memory Bank adapter | `http://localhost:8080` |
| `apps/reference-agent` | Thin ADK consumer used for demonstrations | `http://localhost:8000` |
| PostgreSQL | Durable control-plane metadata, grants, policies, and audit | Compose network only |

## Repository map

```text
geap-memory/
├── apps/
│   ├── admin-console/        React guided setup and administration UI
│   ├── memory-api/           FastAPI runtime and admin service
│   └── reference-agent/      ADK example consumer
├── docs/                     Current architecture, onboarding, demo, and operations guides
├── infrastructure/           Terraform and deployment support
├── packages/                 Cross-application test fixtures
├── scripts/                  Deployment, acceptance, and security utilities
├── docker-compose.yml        Local mock-backed stack
└── docker-compose.vertex.yml Vertex-backed local override
```

## Prerequisites

- Docker with Compose
- Python 3.12 and the repository `.venv` for direct development
- Node.js and npm for direct Admin Console development
- Google Cloud Application Default Credentials for the Vertex-backed flow
- An existing Agent Engine resource with Memory Bank enabled

Authenticate for local Vertex access:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_PROJECT"
```

## Run locally with the mock backend

Use this mode for deterministic development without cloud mutations:

```bash
cp .env.example .env
docker compose up --build
```

Activation reports `REGISTERED_LOCAL`. Schemas and profile data in the mock store are process-local
and are lost when the Memory API restarts. PostgreSQL metadata is retained in the
`shared-memory-postgres` Docker volume.

Wait for all services to become healthy, then open:

- Admin Console: `http://localhost:3000`
- Memory API health: `http://localhost:8080/healthz`
- Memory API OpenAPI: `http://localhost:8080/docs`

The reference agent is an optional Compose profile. Start it with the rest of the mock stack when
Google Cloud credentials and the model settings in `.env` are available:

```bash
docker compose --profile agent up --build
```

Then open ADK Web at `http://localhost:8000/dev-ui/?app=reference_agent`.

Useful lifecycle commands:

```bash
docker compose ps
docker compose logs -f memory-api admin-console
docker compose down
```

Use `docker compose down -v` only when intentionally deleting the local PostgreSQL volume and all
local control-plane data.

The `0002_org_project_governance` migration backfills an existing database into `default-org` and
`default-project`. For a disposable POC environment, reset the volume before testing the new
hierarchy if you prefer an empty control plane:

```bash
docker compose down -v
docker compose up --build
```

## Run locally with Vertex Memory Bank

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export AGENT_PLATFORM_MEMORY_BANK_ID=YOUR_AGENT_ENGINE_ID

docker compose \
  -f docker-compose.yml \
  -f docker-compose.vertex.yml \
  --profile agent \
  up --build
```

Activation must report `PROVISIONED` with backend `VertexMemoryBankStore`. A result of
`REGISTERED_LOCAL` means the API was started without the Vertex override.

Check the services:

```bash
curl http://localhost:8080/healthz
docker compose -f docker-compose.yml -f docker-compose.vertex.yml ps
```

For the complete local startup sequence, troubleshooting, and the GCP resource/deployment order,
see [Deployment and operations](docs/deployment-operations.md).

## Create a domain and schema from the UI

1. Open `http://localhost:3000`.
2. Open **Organizations** from the left context switcher, then create or select an organization and
   project.
3. Select **Create Memory Setup**.
4. Define the use case, choose that organization/project, and enter a DNS-style domain such as `travel`.
5. Select catalog preferences and add custom preferences such as
   `travel.seat_preference`.
6. Select the profile scope and memory behavior. Per-user scope compiles to
   `organization_id + user_id`.
7. Register an agent such as `travel-assistant`.
8. Set owned schema permission to `READ_WRITE` when the agent must save preferences.
9. Request shared schemas only for data owned by other domains; those requests remain pending.
10. Preview the non-mutating activation plan and activate.
11. Verify the result names `travel-preferences-v1` and shows the expected backend.

Activation creates the schema configuration, not a profile for every user. User-scoped profiles are
created lazily by the first authorized write or provider generation event.

The database starts without preloaded business domains. Create each environment's domains,
preferences, schemas, agents, grants, and policies through the Admin Console or versioned Admin API
automation. File-based YAML contract bootstrap and generated runtime JSON are no longer used.

The wizard creates a new version-1 schema. Adding fields to an existing active schema requires a
reviewed schema-version workflow and is intentionally rejected by the wizard.

## Use the setup from ADK Web

Stop any old ADK Web process before changing agent settings; Python tool signatures and environment
variables are loaded at process start.

```bash
cd apps/reference-agent
export MEMORY_API_URL=http://localhost:8080
export MEMORY_API_TOKEN=""
export MEMORY_API_AUDIENCE=""
export REFERENCE_AGENT_ID=travel-assistant
export PREFERENCE_DOMAIN=travel
export ADK_APP_NAME=travel_preferences

adk web --host 0.0.0.0 --port 8000 app
```

Open `http://localhost:8000/dev-ui/?app=reference_agent`, choose a user, and say:

```text
I always prefer a window seat.
```

The tool call should contain only the canonical attribute and value:

```json
{
  "attribute": "travel.seat_preference",
  "value": "window"
}
```

It must not contain `schemaId`. The effective snapshot exposes `writablePreferences`; the Memory
API uses that registration state to select `travel-preferences-v1` behind the scenes.

Ask `What preferences are you currently using?`, then create a new Session for the same user and ask
again. Managed profile consolidation is asynchronous, but the explicit-preference overlay is
available through the platform runtime path.

## Security boundary

- `AUTH_ENABLED=false` is local-only and uses `X-Agent-ID`.
- Production uses a Google-signed ID token and maps the verified principal to one active agent.
- Agent capabilities gate operations: `resolve_context`, `submit_candidates`, and
  `inspect_provenance`.
- Grants gate schema access. A readable shared schema is not writable.
- Automatic write routing considers only active `WRITE` or `READ_WRITE` grants owned by the
  consumer agent's domain.
- Agents never call Memory Bank directly and never make authorization decisions.

## Validation

```bash
PYTHONPATH=apps/memory-api/app:. .venv/bin/python -m pytest -q apps/memory-api/tests
PYTHONPATH=apps/reference-agent/app:. .venv/bin/python -m pytest -q apps/reference-agent/tests

cd apps/admin-console
npm run typecheck
npm test
npm run build
```

Unit and API tests prove deterministic behavior. A release is not end-to-end validated until a
live Vertex smoke test creates a new user preference and retrieves it in a later Session.

## Documentation

Start with [docs/README.md](docs/README.md). The canonical guides are:

- [Guided UI onboarding](docs/guided-memory-setup.md)
- [Domain onboarding](docs/domain-onboarding.md)
- [ADK Web demo](docs/adk-web-demo.md)
- [Architecture and flows](docs/agent-memory-setup.md)
- [Vertex Memory Bank](docs/vertex-memory-bank.md)
- [Deployment and operations](docs/deployment-operations.md)
- [Admin API](docs/admin-api.md)

Draw.io sources are the runtime/onboarding view
[agent-memory-flows.drawio](docs/agent-memory-flows.drawio) and the deployable Google service view
[google-cloud-services-architecture.drawio](docs/google-cloud-services-architecture.drawio).
