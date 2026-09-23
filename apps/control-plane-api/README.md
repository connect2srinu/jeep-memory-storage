# Control Plane API

The FastAPI service is the only memory boundary used by agents and the Admin Console. It owns identity
mapping, capabilities, schema grants, household context, consent, deterministic preference resolution,
write routing, PostgreSQL control-plane state, audit, and the provider-neutral `MemoryStore` adapter.

## Runtime API

Routes under `/api/v1/runtime`:

| Method | Path | Purpose | Capability |
|---|---|---|---|
| POST | `/preferences/resolve` | Effective snapshot (also `/preferences/refresh`) | `resolve_context` |
| POST | `/profiles` | Raw provider profiles for readable schemas | `inspect_provenance` |
| PUT | `/preferences/{attribute}` | Save a canonical value (member, household, or per-member) | `submit_candidates` |
| POST | `/preferences/{attribute}/forget` | Delete one value | `submit_candidates` |
| POST | `/preferences/{attribute}/move` | Move a per-member value to another member | `submit_candidates` |
| POST | `/memory/dynamic` | Save a fact within an approved topic | `submit_candidates` |
| POST | `/memory/events` | Store an event with candidate values | `submit_candidates` |
| POST | `/memory/forget` | Forget a user, a member, or a household (cascades) | `submit_candidates` |
| POST | `/memory/purge` | Organization-wide delete by tier/attribute/topic (`dryRun` default) | `administer_memory` |
| POST | `/household/members` | Propose or add a member by name | `submit_candidates` |
| PATCH | `/household/members/{member_id}` | Rename, or correct the `minor` flag | `submit_candidates` |
| POST | `/household/members/merge` | Merge two entries for the same person | `submit_candidates` |
| PUT / DELETE | `/households/{household_id}/members/{member_id}` | Administrative roster upsert / deactivate | `administer_memory` |

The request `scope` is `{userId, appName?, domain?, householdId?, memberId?}`. `userId` is the logged-in
customer; for household schemas the platform finds or creates their household and refuses any other
`householdId`.

Write requests normally omit `schemaId`; the API matches the attribute against active same-domain
`WRITE` / `READ_WRITE` grants:

- one writable match: use it;
- matching shared/read-only schema: `403 PERMISSION_DENIED`;
- no match or several writable matches: `400 INVALID_ARGUMENT`;
- explicit legacy `schemaId`: same authorization checks.

A per-member write may pass `scope.memberId` or `memberName` + `relationship`. When the customer has to
answer first, nothing is written and the response is `200` with `status` `needs_confirmation` (plus
`confirmationPrompt` and `memberId`), `ambiguous` (plus `candidates`), or `not_allowed` (plus `message`);
the agent repeats the call with `confirmed: true` after a yes.

Example local update:

```bash
curl -X PUT http://localhost:8080/api/v1/runtime/preferences/travel.seat_preference \
  -H 'Content-Type: application/json' \
  -H 'X-Agent-ID: travel-assistant' \
  -d '{"scope": {"userId": "demo-user", "domain": "travel"}, "value": "window"}'
```

## Guided setup API

- `POST /api/v1/admin/memory-setups/preview` validates and returns a review summary without changing
  state.
- `POST /api/v1/admin/memory-setups/activate` creates the control-plane resources in one transaction and
  registers the schemas with the configured backend.

Activation never creates customer profiles. With `MEMORY_BACKEND=mock` it returns `REGISTERED_LOCAL`;
with `MEMORY_BACKEND=vertex` it applies every active schema version to the Agent Engine `context_spec`
and returns `PROVISIONED`.

## Admin API

Governed resources under `/api/v1/admin` include organizations, projects, memberships, domains, scopes,
schemas and versions, preference catalog, agents, resolution and dynamic-memory policies, access
requests, resource-change requests, households and consents, the retention sweep, and audit. Records use
lifecycle transitions instead of physical deletion. See [docs/admin-api.md](../../docs/admin-api.md).

## Backends

- `MockMemoryStore`: deterministic, process-local; used by tests and the default Compose stack.
- `VertexMemoryBankStore`: reads structured profiles and memories from Agent Platform Memory Bank.
  Explicit writes are stored as typed exact-scope memory facts and overlaid on provider profiles.
  Managed generation is never triggered.

A new schema version replaces the registered one in either store without a restart.

## Run directly

```bash
PYTHONPATH=apps/control-plane-api/app uvicorn control_plane_api.main:app --reload --port 8080
curl http://localhost:8080/healthz
```

Compose waits for the database, runs Alembic (`upgrade head`, currently `0009_dynamic_household_members`),
then starts Uvicorn. A new database
contains no business configuration; create it through the Admin Console or Admin API.

## Authentication

`AUTH_ENABLED=false` accepts `X-Agent-ID` and `X-Admin-*` headers for local development only. With
authentication enabled, agents present a Google ID token mapped to one active registered agent, and
admins authenticate with Google (IAP or ID token) or Microsoft Entra ID. Request-body agent IDs cannot
establish identity.

## Validation

From the repository root:

```bash
PYTHONPATH=apps/control-plane-api/app:apps/control-plane-api/tests .venv/bin/python -m pytest -q apps/control-plane-api/tests
.venv/bin/ruff check apps/control-plane-api/app apps/control-plane-api/tests
```

See [docs/agent-memory-setup.md](../../docs/agent-memory-setup.md) and
[docs/vertex-memory-bank.md](../../docs/vertex-memory-bank.md).
