# Shared Memory API

The FastAPI service is the only memory boundary used by agents and the Admin Console. It owns
identity mapping, capabilities, schema grants, deterministic preference resolution, write routing,
PostgreSQL control-plane state, audit, and the provider-neutral `MemoryStore` adapter.

## Runtime API

Routes under `/api/v1/runtime`:

- `POST /preferences/resolve`
- `POST /preferences/refresh`
- `POST /profiles`
- `POST /memory/events`
- `PUT /preferences/{canonical_attribute}`

Resolve responses contain `writablePreferences`. An agent maps natural language to one attribute
from that allowlist. Write requests normally omit `schemaId`; the API resolves the schema by
matching the attribute against active same-domain `WRITE` or `READ_WRITE` grants.

Routing outcomes:

- one writable match: use it;
- matching shared/read-only schema: `403 PERMISSION_DENIED`;
- no match: `400 INVALID_ARGUMENT`;
- multiple writable matches: `400 INVALID_ARGUMENT`;
- explicit legacy `schemaId`: retain exact authorization checks.

Example local update:

```bash
curl -X PUT http://localhost:8080/api/v1/runtime/preferences/grocery.preferred_snack \
  -H 'Content-Type: application/json' \
  -H 'X-Agent-ID: grocery-agent' \
  -d '{
    "scope": {"userId": "demo-user", "appName": "grocery-app", "domain": "grocery"},
    "value": "mango chips"
  }'
```

## Guided setup API

- `POST /api/v1/admin/memory-setups/preview` performs validation and returns generated YAML without
  changing state.
- `POST /api/v1/admin/memory-setups/activate` transactionally creates the control-plane resources
  and provisions the configured backend.

Activation never creates user profile instances. With `MEMORY_BACKEND=mock`, it returns
`REGISTERED_LOCAL`. With `MEMORY_BACKEND=vertex`, it applies every active schema version to the
configured Agent Engine `context_spec` and returns `PROVISIONED`.

## Admin API

Governed resources under `/api/v1/admin` include domains, scopes, schemas, preference catalog,
agents, resolution policies, dynamic-memory policies, access requests, approvals, and audit.
Records use lifecycle transitions instead of physical deletion.

Supported roles are `PLATFORM_ADMIN`, `DOMAIN_ADMIN`, `SCHEMA_OWNER`, `AGENT_OWNER`, and `VIEWER`.
Domain-scoped roles also require an assigned domain.

## Backends

- `MockMemoryStore`: deterministic, process-local testing.
- `VertexMemoryBankStore`: retrieves structured profiles and dynamic memories from Agent Platform
  Memory Bank. Explicit preference writes are stored as typed exact-scope memory facts and overlaid
  on provider profiles; natural-language events are also ingested for lazy provider generation.

The provider currently has no direct field-level structured-profile update method, so the explicit
overlay is the authoritative immediate-write mechanism used by this platform.

## Run directly

```bash
PYTHONPATH=apps/memory-api/app uvicorn memory_api.main:app --reload --port 8080
curl http://localhost:8080/healthz
```

Compose runs Alembic before Uvicorn. A new database contains no business-domain configuration;
create it through the Admin Console or Admin API.

## Authentication

`AUTH_ENABLED=false` accepts `X-Agent-ID` for local development only. With authentication enabled,
the API verifies a Google ID token audience and maps the verified principal to one active agent.
Request-body agent IDs cannot establish identity.

## Validation

```bash
PYTHONPATH=apps/memory-api/app:apps/memory-api/tests .venv/bin/python -m pytest -q apps/memory-api/tests
.venv/bin/ruff check apps/memory-api/app apps/memory-api/tests
```

See `docs/admin-api.md`, `docs/vertex-memory-bank.md`, and `docs/agent-memory-setup.md`.
