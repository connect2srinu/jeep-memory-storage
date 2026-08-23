# Shared Memory Platform Migration Plan

## Purpose and status

This plan transforms the current single-package POC into three independently runnable applications:

```text
apps/reference-agent
apps/memory-api
apps/admin-console
```

It is based on the baseline documented in `existing-architecture-analysis.md`. The plan uses
incremental, test-gated changes. Existing behavior remains available until its replacement passes
unit, contract, and integration tests.

## Migration principles

1. Use a strangler migration; do not rewrite the working resolver and adapters.
2. Establish API contracts before moving the ADK agent out of process.
3. Keep Memory Bank calls exclusively in the Memory API after the cutover.
4. Keep Google-specific objects out of the platform domain model.
5. Derive agent identity from a verified principal, never only from request data.
6. Default-deny agent, schema, operation, and scope authorization.
7. Store control-plane metadata in PostgreSQL and memory data in Memory Bank.
8. Keep mock and Vertex backends behaviorally compatible.
9. Preserve provenance and version every input that changes resolution.
10. Resolve deterministically; reserve an ambiguity interface without invoking an LLM by default.
11. Create profile instances lazily from user events; the Admin Console provisions definitions only.
12. Keep root regression tests green throughout the transition.

## Target repository layout

```text
.
├── apps/
│   ├── reference-agent/
│   │   ├── app/
│   │   │   ├── agent.py
│   │   │   ├── client.py
│   │   │   ├── extraction.py
│   │   │   ├── session.py
│   │   │   └── settings.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── memory-api/
│   │   ├── app/
│   │   │   ├── api/runtime/
│   │   │   ├── api/admin/
│   │   │   ├── domain/
│   │   │   ├── services/
│   │   │   ├── repositories/
│   │   │   ├── integrations/vertex_memory_bank/
│   │   │   ├── security/
│   │   │   ├── models/
│   │   │   └── config/
│   │   ├── migrations/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── admin-console/
│       ├── src/
│       ├── tests/
│       ├── package.json
│       ├── Dockerfile
│       └── README.md
├── packages/
│   ├── contracts/
│   ├── python-client/
│   └── test-fixtures/
├── infrastructure/
│   ├── terraform/modules/
│   ├── terraform/environments/dev/
│   └── cloud-run/
├── config/contracts/
├── docs/
├── docker-compose.yml
└── README.md
```

During migration, the existing `app/`, `scripts/`, and `tests/` remain until equivalent target paths
are exercised. Compatibility modules may re-export moved objects for one release.

## Target application boundaries

### Reference Agent

Owns ADK configuration, Grocery prompt, agent-specific extraction, Session snapshot loading, and a
typed Memory API client. It receives `MEMORY_API_URL` and obtains an ID token for the configured
audience in authenticated environments. It does not import Memory Bank SDKs or Memory API service
implementations.

Session flow:

```text
new ADK session -> resolve once through Memory API -> store snapshot/version in Session state
user preference change -> call Memory API -> refresh snapshot explicitly
ordinary turn -> use Session snapshot without another resolution call
```

### Shared Memory API

Owns runtime and admin APIs, verified workload identity, agent/schema/scope authorization,
PostgreSQL metadata, deterministic resolution, audit, caching, and all Memory Bank integration.
Runtime and control-plane modules share domain services but expose separate routers and permissions.

### Admin Console

Owns human control-plane workflows and calls only `/api/v1/admin/*`. It uses role-based UI guards but
relies on API authorization as the security boundary. It never calls Memory Bank.

### Shared packages

`packages/contracts` owns transport schemas/OpenAPI artifacts and onboarding contract definitions.
`packages/python-client` provides the Reference Agent client. `packages/test-fixtures` owns seed
profiles and acceptance data. Shared packages must not import an application.

## Path migration map

| Current path | Target path | Migration method |
|---|---|---|
| `app/agents/grocery_agent.py` | `apps/reference-agent/app/agent.py` | Copy/move after client facade exists; compatibility re-export |
| `app/agents/grocery_extraction.py` | `apps/reference-agent/app/extraction.py` | Move with current extractor tests |
| `app/tools/preference_tools.py` | `apps/reference-agent/app/client.py` and tool wrappers | Replace in-process service calls with HTTP client |
| `app/api.py` | `apps/memory-api/app/main.py` | Create target entry point, retain root wrapper temporarily |
| `app/shared_memory/api/routes.py` | `apps/memory-api/app/api/runtime/` | Introduce target versioned routes and contract tests |
| `app/shared_memory/models` | `apps/memory-api/app/domain` | Move domain types; expose separate request/response DTOs |
| catalog/policies/resolver | `apps/memory-api/app/domain` | Move behavior unchanged first |
| services | `apps/memory-api/app/services` | Move behind repository and integration interfaces |
| auth | `apps/memory-api/app/security` | Split authenticator from authorization policy |
| adapters | `apps/memory-api/app/integrations/vertex_memory_bank` | Conform to a unified `MemoryStore` protocol |
| snapshot/candidate stores | `apps/memory-api/app/repositories` | Keep in-memory implementations; add SQL implementations |
| contract compiler/models | `packages/contracts` | Move with compatibility imports and deterministic artifact tests |
| `config/contracts` | root `config/contracts` initially | Preserve GitOps source; add database seed/import command |
| `app/shared_memory/demo.py` | `packages/test-fixtures` plus demo script | Preserve acceptance data and expected results |
| `scripts/*` | app-specific `scripts/` or root compatibility wrappers | Move one command at a time |
| root tests | target app/package tests | Duplicate coverage first, remove old path only after parity |

## Target domain and persistence model

PostgreSQL tables use stable IDs, foreign keys, timestamps, actor metadata, and optimistic versioning.
Flexible rule details may use JSONB, but entity relationships must not be one configuration blob.

| Entity | Key relationships and purpose |
|---|---|
| `memory_domains` | business ownership, status, owner team/contact |
| `scope_definitions` | governed scope type and ordered scope keys |
| `profile_schemas` | stable schema identity and owning domain |
| `profile_schema_versions` | immutable schema/version/status and Vertex representation |
| `preference_definitions` | enterprise canonical attribute catalog |
| `schema_preference_mappings` | schema field to canonical attribute mapping |
| `registered_agents` | runtime-agnostic agent and verified service principal |
| `agent_schema_grants` | `NONE`, `READ`, `WRITE`, or `READ_WRITE`, with expiry/revocation |
| `access_requests` | durable owner approval workflow and business reason |
| `resolution_policies` | agent policy identity and active version |
| `resolution_policy_schema_priorities` | default ordered schema precedence |
| `resolution_attribute_overrides` | attribute-specific precedence and rules |
| `dynamic_memory_policies` | platform/domain/schema thresholds and retention |
| `audit_events` | actor, action, target, correlation ID, redacted before/after metadata |

Alembic owns schema migrations. Repositories isolate SQLAlchemy from domain services. Seed/import
logic loads the existing YAML bundle as initial approved/active configuration.

## Runtime API contract

Initial target routes:

| Method and route | Purpose |
|---|---|
| `POST /api/v1/runtime/preferences/resolve` | Return agent-specific Effective Preference Snapshot |
| `POST /api/v1/runtime/profiles` | Return authorized raw profiles for debug-authorized callers |
| `POST /api/v1/runtime/memory/events` | Ingest interaction events for lazy generation |
| `PUT /api/v1/runtime/preferences/{attribute}` | Deterministic explicit preference update |
| `POST /api/v1/runtime/preferences/refresh` | Force snapshot recomputation if a separate route is useful |

The request carries scope and operation data. Authentication middleware establishes a principal;
the Agent Registry maps that principal to `agent_id`. A body/header agent ID may be logged for
diagnostics but cannot establish identity. `include_provenance` is honored only when the agent grant
allows it.

The snapshot includes agent ID, scope, preferences, provenance when authorized, snapshot version,
policy version, schema versions, and generation time.

## Admin API and Console plan

Admin resources are exposed below `/api/v1/admin`:

```text
domains, schemas, preference-catalog, scopes, agents, access-requests,
approvals, resolution-policies, dynamic-memory-policies, audit, provisioning
```

The Console implements Dashboard, Domains, Schemas, Preference Catalog, Agents, Access Requests,
Approvals, Resolution Policies, Dynamic Memory Policies, and Audit pages. Schema creation reuses
catalog attributes and initially detects duplicates through normalized-name matching behind a
replaceable similarity interface. Resolution controls only list schemas with approved READ grants.

RBAC roles are `PLATFORM_ADMIN`, `DOMAIN_ADMIN`, `SCHEMA_OWNER`, `AGENT_OWNER`, and `VIEWER`.

## Authentication and security migration

1. Define `AgentAuthenticator.authenticate(request) -> AuthenticatedPrincipal`.
2. Provide a local test authenticator only when `AUTH_ENABLED=false`.
3. Add Google ID-token verification with issuer, audience, expiry, and signature validation.
4. Map the token service-account principal to one active Registered Agent.
5. Authorize agent -> operation -> schema -> scope; default deny.
6. Run Memory API with a least-privilege service account; agents receive no Memory Bank role.
7. Add admin user authentication and role/domain ownership checks.
8. Hash scope identifiers in logs and redact sensitive values by default.
9. Store production secrets in Secret Manager and never in images or source.

## Memory backend plan

Define one async `MemoryStore` interface for profile retrieval, natural-memory retrieval, event
generation/ingestion, and explicit create/update. Implement:

- `MockMemoryStore`: scope-aware in-memory store with schema profiles and deterministic writes;
- `VertexMemoryBankStore`: wrapper around current adapters and `agentplatform.Client`;
- contract tests executed against both implementations where cloud configuration permits.

Profile retrieval should make one provider call for all applicable schemas when the API supports it,
then filter by active schema grants before resolution. Preserve the existing schema-owner admission
guard. If the provider requires domain-specific calls, encapsulate that limitation in the adapter and
record it in metrics.

## Incremental delivery phases and gates

### Phase 0 — Analysis and planning

- [x] Inventory repository and dependencies.
- [x] Record lint/test baseline.
- [x] Produce existing architecture analysis.
- [x] Produce migration plan and mapping.
- [x] Commit Phase 0 documents separately.

Gate: documents match the repository and no runtime code changes are included.

### Phase 1 — Repository separation without behavior change

- [x] Create the three application directories and shared package directories.
- [x] Add independent READMEs, package manifests, a health endpoint, and Dockerfiles.
- [x] Add compatibility entry points while leaving the legacy package intact.
- [x] Move/copy the Memory API entry point first; keep current root tests green.
- [x] Add a runnable React Console shell that calls the Memory API health endpoint.
- [x] Add Docker Compose topology and application-boundary regression tests.

Gate: all three applications start independently; existing 63 tests still pass.

### Phase 2 — Platform domain and PostgreSQL control plane

- [x] Add typed domain entities and repository interfaces.
- [x] Add normalized SQLAlchemy models, async database lifecycle, and an initial Alembic migration.
- [x] Add an idempotent importer for existing validated YAML contracts.
- [x] Preserve YAML validation/compilation as the initial GitOps interface.
- [x] Add SQLite repository tests and an opt-in PostgreSQL contract test.
- [ ] Run the PostgreSQL contract test against the Compose database and record the result.

Gate: repository contract tests pass against PostgreSQL; no runtime reads are switched yet.

### Phase 3 — Mock Memory Bank

- [x] Add scope registry and `MemoryStore` protocol.
- [x] Implement mock schemas, profiles, natural memories, event generation, and explicit writes.
- [x] Port resolver and authorization tests to the Memory API package.

Gate: required resolver, authorization, scope isolation, and backend contract tests pass offline.

### Phase 4 — Runtime API and workload identity

- Add runtime routers, DTOs, middleware, correlation IDs, and structured metrics.
- Implement authenticator interface, local mode, and Google ID-token verifier.
- Resolve schema grants and scopes from PostgreSQL.
- Return versioned Effective Preference Snapshots.

Gate: API tests cover resolve, raw-profile filtering, event ingestion, explicit writes, denials, and
no cross-user leakage.

### Phase 5 — Reference ADK Agent cutover

- Add typed async Memory API client and token provider.
- Load a snapshot once during Session initialization.
- Add `get_user_preferences` and `refresh_user_preferences` tools.
- Route writes/events through the API and refresh only after changes or explicit requests.
- Remove Memory Bank SDK dependencies from the Reference Agent package.

Gate: an end-to-end mock test proves session start, Gemini context, update, refresh, and changed
behavior. Only then retire agent-side in-process service calls.

### Phase 6 — Admin APIs and approval workflow

- Add CRUD/state-transition services for domains, scopes, schemas, catalog, agents, policies, and
  dynamic-memory policies.
- Implement request, approve, reject, revoke, and expire grant flows.
- Write audit events in the same database transaction as control-plane changes.

Gate: RBAC, ownership, transition, expiry, and audit tests pass.

### Phase 7 — React Admin Console

- Build the required pages and typed API client.
- Add schema preview, normalized duplicate warnings, ordered resolution controls, and approval UX.
- Add component and browser-level workflow tests.

Gate: the acceptance configuration can be created using only the Console and Admin API.

### Phase 8 — Vertex integration

- Adapt existing Memory Bank/Profile code to `VertexMemoryBankStore`.
- Add provider provisioning from approved active schema versions.
- Validate GenerateMemories, available event ingestion, RetrieveProfiles, exact scopes, and lazy
  profile creation.
- Document provider limitations and isolation choices.

Gate: the MemoryStore contract suite and acceptance data pass in a configured GCP environment.

### Phase 9 — End-to-end integration

- Seed Customer, Grocery, and Inventory domains/schemas and user `1001`.
- Exercise access request and owner approval.
- Apply Grocery default precedence and Customer-first `preferred_store` override.
- Resolve, update a preference, refresh, and verify provenance/version changes.

Gate: the complete scenario passes first with mock, then Vertex.

### Phase 10 — Deployment and operations

- Add Docker Compose for PostgreSQL, Memory API, and Admin Console.
- Add Terraform dev modules for APIs, service accounts, Artifact Registry, Cloud Run, Cloud SQL,
  Secret Manager, IAM, and networking.
- Add Cloud Run deployment configuration for all three apps.
- Add dashboards/alerts, migration jobs, rollback procedures, and security checks.

Gate: documented dev deployment, smoke test, rollback, and teardown succeed without automatically
creating production resources.

## Test strategy

| Layer | Required coverage |
|---|---|
| Domain/resolver | no conflict, duplicates, schema conflict, attribute override, canonical/dynamic, confidence, recency, missing/empty schema |
| Authorization | `READ_WRITE`, `READ`, `NONE`, expired/revoked grant, wrong principal, wrong scope |
| Scope | construction, allowed keys, exact match, no cross-user/household/store leakage |
| Backend contract | profile retrieval, natural memory, explicit write, event generation, schema filtering |
| Runtime API | resolve, provenance option, raw profiles, events, explicit write, refresh, error contracts |
| Admin API | CRUD, state transitions, request/approval/revocation, policy activation, audit |
| Agent | initialization snapshot, no per-turn resolve, write then refresh, absent-value behavior |
| Console | role guards, forms, schema preview, access workflow, ordering controls |
| End-to-end | full user `1001` scenario on mock and configured Vertex backend |

Every migration PR runs the legacy suite until final retirement. Each moved component gets import or
contract compatibility tests. Deletion requires evidence that the target path covers the old path.

## Local development and deployment plan

`docker compose up` starts PostgreSQL, Memory API, and Admin Console. The Reference Agent may run
with ADK Web separately and connects to `MEMORY_API_URL`. Default local configuration uses:

```text
MEMORY_BACKEND=mock
AUTH_ENABLED=false
DATABASE_URL=postgresql+asyncpg://...
```

Vertex mode adds project, location, Memory Bank ID, and ADC/workload identity. Production Cloud Run
uses `AUTH_ENABLED=true`, private ingress where practical, dedicated service accounts, Secret
Manager references, Cloud SQL connectivity, and no static service-account keys.

## Observability and invalidation

Runtime logs and traces carry correlation ID, authenticated agent ID, hashed scope, policy/schema
versions, total and provider/resolver latency, cache result, profile counts, result status, and
authorization decision. Raw identifiers and sensitive values remain redacted.

Cache invalidation occurs after explicit writes, completed memory generation, policy/schema/grant
activation changes, TTL expiry, and explicit refresh. The POC uses in-memory caching behind an
interface; Redis is a later implementation.

## Acceptance configuration

Seed Customer Experience, Grocery, and Inventory domains and schemas. Register Grocery Assistant
with Grocery `READ_WRITE`; request and approve Customer and Inventory `READ`. For user `1001`, seed:

```text
grocery:   dietary_preference=vegetarian, preferred_store=Store-A
customer:  preferred_store=Store-B, fulfillment_preference=pickup
inventory: preferred_store=Store-C
```

Grocery default precedence is Grocery > Customer > Inventory, with `preferred_store` overridden to
Customer > Grocery > Inventory. Expected snapshot: vegetarian from Grocery, Store-B from Customer,
and pickup from Customer, each with provenance. A user update must flow through the Runtime API,
invalidate the snapshot, update mock/Vertex memory lazily, and appear after refresh.

## Risks and explicit decisions

| Risk | Mitigation/decision |
|---|---|
| Big-bang package move breaks ADK discovery | Compatibility shims and entry-point tests |
| Agent still bypasses API | Make HTTP client cutover a Phase 5 gate; remove Memory SDK dependency afterward |
| YAML and database drift | Versioned import/export plus one active source per environment and CI comparison |
| Provider schema-selection limitation | Preserve read guard; evaluate separate banks or unique scope signatures |
| Unverified local identity leaks into production | Production startup fails when auth is disabled |
| In-memory queues/cache lose state | PostgreSQL workflow first; replaceable cache interface |
| Sensitive data enters logs/audit | Redaction by default and metadata-only before/after records |
| Extra LLM cost and nondeterminism | No LLM in normal resolution; unused ambiguity interface only |

## Migration completion checklist

- [ ] Three applications run independently.
- [ ] Reference Agent imports no Vertex/Memory Bank integration.
- [ ] Runtime identity maps a verified principal to a Registered Agent.
- [ ] PostgreSQL stores normalized control-plane entities and audit.
- [ ] Mock and Vertex MemoryStore implementations pass the same contract suite.
- [ ] Runtime and Admin APIs are versioned and documented.
- [ ] Access approval produces/revokes schema grants without copying memory.
- [ ] React Console completes the acceptance configuration.
- [ ] Snapshot resolution is agent- and attribute-specific with provenance and versions.
- [ ] Profile instances are created lazily, never bulk-provisioned by the Console.
- [ ] Docker Compose runs the local POC.
- [ ] Terraform dev configuration validates and is not auto-applied.
- [ ] Mock and Vertex acceptance scenarios pass.
- [ ] Obsolete code is removed only after replacement tests pass.
