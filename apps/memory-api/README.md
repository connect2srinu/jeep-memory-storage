# Shared Memory API

This application is the runtime-independent API boundary for agents and the Admin Console. During
the first migration slice its entry point reuses the tested legacy platform services. Subsequent
slices move those services into this package without changing the HTTP boundary.

Run from the repository root:

```bash
PYTHONPATH=apps/memory-api/app uvicorn memory_api.main:app --reload --port 8080
```

Health check:

```bash
curl http://localhost:8080/healthz
```

Create or upgrade the control-plane schema and import the validated YAML contracts:

```bash
docker compose exec memory-api alembic -c apps/memory-api/alembic.ini upgrade head
docker compose exec memory-api \
  sh -c 'PYTHONPATH=apps/memory-api/app:. python apps/memory-api/scripts/bootstrap_contracts.py'
```

The Docker image runs Alembic before starting Uvicorn. The importer is idempotent and preserves the
YAML contracts as the initial GitOps source. Runtime resolution continues to use the compatibility
core until the database-backed authorization and policy repositories pass their later migration
gates.

The provider-neutral `MemoryStore` protocol and strict scope registry now define the next runtime
boundary. `MockMemoryStore` supplies deterministic offline schemas, lazy profile creation, natural
memories, event ingestion, explicit writes, and scope isolation while the Vertex implementation is
being moved behind the same contract.

The Memory API package also owns a pure deterministic resolver and default-deny authorization
service. Offline tests cover precedence, expiration, confidence thresholds, provenance, capability
checks, schema grants, cross-domain access rules, and cross-user scope isolation. This completes the
Phase 3 offline gate; the versioned HTTP routes and verified workload identity are introduced in
Phase 4.

## Phase 4 runtime API

Runtime operations are available below `/api/v1/runtime`:

- `POST /preferences/resolve`
- `POST /preferences/refresh`
- `POST /profiles`
- `POST /memory/events`
- `PUT /preferences/{canonical_attribute}`

With `AUTH_ENABLED=false`, callers must send `X-Agent-ID`; this mode is only for local development.
With `AUTH_ENABLED=true`, callers must send a Google-signed bearer ID token whose audience equals
`GOOGLE_ID_TOKEN_AUDIENCE`. The verified service-account email is mapped to one active agent in the
PostgreSQL registry. Request-body agent IDs are diagnostic only and cannot establish identity.

Legacy `/v1/memory/*` routes are disabled by default. Set `INCLUDE_LEGACY_ROUTES=true` only during a
controlled compatibility window. Production deployments must keep it false.

Example local update:

```bash
curl -X PUT http://localhost:8080/api/v1/runtime/preferences/grocery.preferred_snack \
  -H 'Content-Type: application/json' \
  -H 'X-Agent-ID: grocery-agent' \
  -d '{
    "scope": {"userId": "demo-user", "appName": "grocery-app", "domain": "grocery"},
    "schemaId": "grocery-preferences-v1",
    "value": "mango chips"
  }'
```
