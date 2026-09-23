# Control Plane Platform for Google ADK

This repository implements a governed preference-memory service between ADK agents and Google
Vertex AI Memory Bank. Domain teams define preferences, schemas, agents, and access through the
Admin Console and Admin API; PostgreSQL is the control-plane source of truth. Agents call one stable
runtime API and never need Memory Bank SDKs, schema IDs, scope keys, or conflict-resolution logic.

## Current end-to-end flow

```text
Platform admin
  -> Admin Console: Organizations -> create organization and project
  -> Create Memory Setup wizard: domain, preferences, scope, memory, agents, (sharing, resolution)
  -> preview (non-mutating) and activate
  -> Control Plane API creates the domain, catalog preferences, schema(s), agent, grants, and policies
     and registers the schemas with the memory backend (profiles stay lazy)

Customer (ADK agent session)
  -> agent resolves the effective snapshot once per session and injects it every turn
  -> the agent's own LLM decides whether a message holds a preference and extracts it
  -> save_preference / remember_dynamic_preference call the Control Plane runtime API
  -> Control Plane validates: catalog + grant, scope + household member, sensitivity screen,
     health consent, purpose, audit
  -> Memory Bank stores a typed fact at the exact scope
  -> later Sessions resolve the saved value
```

The model and the customer never supply a schema ID. The platform derives it from the authenticated
agent, its organization/project/domain, its active grants, and the schema mappings. Unknown,
read-only, cross-domain, and ambiguous writes fail closed. Memory Bank's own managed extraction is
turned off, so nothing is stored unless it passed through these checks.

## Governance hierarchy and memory scopes

```text
Organization (line of business)
└── Project
    ├── Agents
    └── Domains
        └── Schemas (versioned) and preference fields
```

Organizations, projects, and domains are authorization metadata in PostgreSQL; they are not Memory
Bank partition keys. Each schema version is bound to one of three scope shapes:

| Scope level | Memory Bank scope | Holds |
|---|---|---|
| Member | `organization_id + user_id` | one customer's own preferences |
| Household | `organization_id + household_id` | preferences shared by the household |
| Household member | `organization_id + household_id + member_id` | one person's preferences (e.g. a child's allergies) |

For household setups, the logged-in customer (the ADK user ID) is the household root; the platform
creates the household and root member on first use with surrogate IDs. Other people are resolved or
proposed from names at runtime, new people and health data need a confirmation turn, and health data
records consent. See [Dynamic Household Members](docs/dynamic-household-members-design.md).

## Applications

| Component | Purpose | Local URL |
|---|---|---|
| `apps/admin-console` | Guided setup, organization/project workspace, households, governance screens | `http://localhost:3000` |
| `apps/control-plane-api` | Admin and runtime APIs, authorization, resolution, Memory Bank adapter | `http://localhost:8080` |
| `apps/memory-agent` | Reference ADK agent: Postgres sessions, governed long-term memory, household tools | `http://localhost:8000/dev-ui/?app=memory_agent` |
| `apps/reference-agent` | Minimal thin-consumer ADK agent (Compose `agent` profile) | `http://localhost:8000/dev-ui/?app=reference_agent` |
| PostgreSQL | Control-plane metadata, grants, policies, household roster, consent ledger, audit | Compose network; `127.0.0.1:15432` with the dev-UI overlay |

## Repository map

```text
geap-memory/
├── apps/
│   ├── admin-console/            React admin UI
│   ├── control-plane-api/        FastAPI admin + runtime service, Alembic migrations
│   ├── memory-agent/             Reference ADK agent (short-term Postgres, long-term governed memory)
│   └── reference-agent/          Minimal ADK consumer
├── docs/                         Guides, designs, and analyses (start at docs/README.md)
├── infrastructure/               Terraform and Cloud Run helpers
├── packages/test-fixtures/       Cross-application test fixtures
├── scripts/                      Deployment security check, API examples, load test
├── tests/                        Repository boundary and deployment-security tests
├── docker-compose.yml            Local mock-backed stack
├── docker-compose.devui.yml      Publishes PostgreSQL on 127.0.0.1:15432 for the memory-agent dev UI
├── docker-compose.pgadmin.yml    Same host mapping, for database tools
└── docker-compose.vertex.yml     Vertex-backed local stack
```

## Prerequisites

- Docker with Compose v2
- Python 3.12 (a repository `.venv` for the API and reference agent; `apps/memory-agent/.venv` for the
  memory agent)
- Node.js and npm for direct Admin Console development
- Google Cloud Application Default Credentials for Gemini and for the Vertex-backed flow
- An existing Agent Engine resource with Memory Bank enabled, for the Vertex-backed flow only

## Run locally with the mock backend

From the repository root:

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.devui.yml up -d --build --wait
```

This starts PostgreSQL, the Control Plane API (with `MEMORY_BACKEND=mock`), and the Admin Console, and
publishes PostgreSQL on `127.0.0.1:15432` so the memory-agent dev UI can store sessions. Open:

- Admin Console: `http://localhost:3000`
- API health: `http://localhost:8080/healthz`
- API docs: `http://localhost:8080/docs`

Stop with `docker compose -f docker-compose.yml -f docker-compose.devui.yml down`. Add `-v` only when
you intend to delete the PostgreSQL volume and all local control-plane data. Mock-store memories are
process-local and are lost when the API container restarts; PostgreSQL metadata survives.

Then start the agent dev UI (see [apps/memory-agent](apps/memory-agent/README.md)):

```bash
cd apps/memory-agent
CONTROL_PLANE_API_URL=http://localhost:8080 \
REFERENCE_AGENT_ID=<registered agent id> \
PREFERENCE_DOMAIN=<domain id> \
SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory \
.venv/bin/python -m memory_agent.serve
```

## Run locally with Vertex Memory Bank

```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export AGENT_PLATFORM_MEMORY_BANK_ID=YOUR_AGENT_ENGINE_ID

docker compose -f docker-compose.yml -f docker-compose.vertex.yml up --build
```

Activation must report `PROVISIONED` with backend `VertexMemoryBankStore`; `REGISTERED_LOCAL` means the
API is still on the mock backend. See [Deployment and Operations](docs/deployment-operations.md).

## Create a setup and use it

The complete, tested walkthrough — organization, project, wizard, agent, and a full customer journey
in the ADK dev UI — is [Household Memory — End-to-End UI Guide](docs/dynamic-household-test-guide.md).
In short:

1. **Organizations** (top of the left panel) → create an organization, then a project.
2. **Create Memory Setup** → Use Case → Preferences → Scope → Memory → Agents → Review → Activate.
   Give the agent `READ_WRITE` on its owned schema so it can save preferences.
3. Start the memory agent with the registered agent ID and domain, open the dev UI, and talk to it.

Activation registers schemas; it never creates a profile for every user. Profiles are created by the
first authorized write.

To add a preference to a live schema, open **Govern & manage → Schemas** with the organization
selected, pick the schema, and use **Create new version**; after approval in **Govern & manage →
Approvals** it is usable without a restart. The wizard itself never mutates an active schema.

## Security boundary

- `AUTH_ENABLED=false` is local-only: agents are identified by `X-Agent-ID` and admins by
  `X-Admin-*` headers.
- Deployed agents present a Google-signed ID token mapped to exactly one active registered agent.
- Admin users authenticate with Google (IAP or ID token) or Microsoft Entra ID
  ([Entra setup](docs/entra-authentication.md)).
- Agent capabilities gate operations (`resolve_context`, `submit_candidates`, `inspect_provenance`,
  `administer_memory`); schema grants gate data. A readable shared schema is never writable.
- Every write is screened for restricted and sensitive content; sensitive values must be
  user-directed; health data about someone else needs confirmation and consent, and is refused for
  other adults.
- An agent's declared purpose must be allowed by each schema it reads; advertising never reaches
  per-member or health data.
- Agents never call Memory Bank directly and never make authorization decisions.

## Validation

```bash
python scripts/validate_deployment_security.py
.venv/bin/ruff check apps scripts tests
PYTHONPATH=apps/control-plane-api/app:apps/control-plane-api/tests .venv/bin/python -m pytest -q apps/control-plane-api/tests
PYTHONPATH=apps/reference-agent/app .venv/bin/python -m pytest -q apps/reference-agent/tests
(cd apps/memory-agent && .venv/bin/python -m pytest -q tests)

cd apps/admin-console
npm run typecheck
npm test
npm run build
```

Unit and API tests run against the mock store. A release is not end-to-end validated until a live
Vertex smoke test creates a preference and retrieves it in a later Session.

## Documentation

Start with [docs/README.md](docs/README.md).
