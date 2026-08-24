# Shared Memory Platform for Google ADK

This repository implements a governed preference-memory service between ADK agents and Google
Vertex AI Memory Bank. Domain teams define preferences through the Admin Console or reviewed YAML
contracts. Agents consume one stable runtime API and never need Memory Bank SDKs, schema IDs, or
conflict-resolution logic.

## Current end-to-end flow

```text
Platform admin
  -> Admin Console: Create Memory Setup
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
agent, its domain, active grants, and schema mappings. Unknown, read-only, cross-domain, and
ambiguous writes fail closed.

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
├── config/
│   ├── contracts/            Reviewed domain contract bundles
│   ├── generated/            Deterministically compiled artifacts
│   └── templates/            Optional GitOps onboarding templates
├── docs/                     Current architecture, onboarding, demo, and operations guides
├── infrastructure/           Terraform and deployment support
├── packages/                 Shared contracts and test fixtures
├── scripts/                  Contract, deployment, and diagnostic utilities
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
2. Select **Create Memory Setup**.
3. Define the use case and a DNS-style domain such as `travel`.
4. Select catalog preferences and add custom preferences such as
   `travel.seat_preference`.
5. Select the profile scope and memory behavior.
6. Register an agent such as `travel-assistant`.
7. Set owned schema permission to `READ_WRITE` when the agent must save preferences.
8. Request shared schemas only for data owned by other domains; those requests remain pending.
9. Preview the generated contract and activate.
10. Verify the result names `travel-preferences-v1` and shows the expected backend.

Activation creates the schema configuration, not a profile for every user. User-scoped profiles are
created lazily by the first authorized write or provider generation event.

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

Draw.io sources are [agent-memory-flows.drawio](docs/agent-memory-flows.drawio),
[shared-memory-platform.drawio](docs/shared-memory-platform.drawio), and the Google service view
[google-cloud-services-architecture.drawio](docs/google-cloud-services-architecture.drawio).
