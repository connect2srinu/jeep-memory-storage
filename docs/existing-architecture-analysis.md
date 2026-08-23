# Existing Architecture Analysis

## Document status

- Assessment date: 2026-08-22
- Baseline branch: `main`
- Baseline commit: `94880d9`
- Scope: Phase 0 analysis only; no application code was changed during this assessment
- Test baseline: 63 passed, 1 Google Cloud integration test skipped, 5 dependency warnings

## Executive summary

The repository is a single installable Python package that combines an ADK Grocery reference agent,
a FastAPI facade, domain contracts, deterministic preference resolution, Google Agent Platform
adapters, and local test doubles. The internal layering is stronger than the physical deployment
boundary: agents call `SharedMemoryPlatformService` through in-process Python tools, while the same
service is also exposed through FastAPI.

The code already proves several target concepts:

- framework-neutral preference and provenance models;
- domain and catalog authorization with default-deny consumer registration;
- deterministic, attribute-level resolution without an LLM call;
- parallel retrieval of Session, explicit profile, Memory Profile, and dynamic memory sources;
- Memory Bank and Session adapters behind service protocols;
- YAML contracts compiled into deterministic runtime JSON;
- an in-memory snapshot cache and cross-domain candidate queue;
- redacted structured logging; and
- a Grocery ADK consumer plus Store and Delivery reference consumers.

It does not yet implement three independently runnable applications. There is no React Admin
Console, PostgreSQL control-plane store, Alembic migration, durable approval workflow, Docker
Compose environment, Cloud Run packaging, Terraform, workload-token verification, or admin API.
The current REST API also accepts `agentId` and user/session identifiers as request data and performs
presence/registry checks rather than cryptographic workload authentication.

The safest migration is a strangler refactor: preserve the existing service and tests, move the
platform core behind the Memory API, introduce an HTTP client in the Reference Agent, and only then
remove the in-process dependency.

## Current system topology

```text
ADK Web / local Runner
        |
        v
app/agents/grocery_agent.py
        |
        v
app/tools/preference_tools.py
        |
        | in-process call
        v
SharedMemoryPlatformService <--------- app/api.py / FastAPI routes
        |
        +--> SessionContextService ------> ADK tool state / in-memory / managed read adapter
        +--> ProfilePreferenceService ---> static MockProfileAdapter
        +--> LongTermMemoryService ------> Agent Platform Memory Bank + Memory Profiles
        +--> AuthorizationService -------> compiled consumer/domain/catalog policy
        +--> PreferenceResolver ---------> deterministic effective context
        +--> InMemorySnapshotService
        +--> InMemoryCandidateRepository

config/contracts/*.yaml
        |
        v
contract loader + compiler
        |
        v
catalog, policy, consumer, profile, manifest, and JSON Schema artifacts
```

The FastAPI surface and the ADK tools share the same in-process bootstrap. The API is therefore not
yet the exclusive boundary between an agent and Memory Bank.

## Repository inventory

| Area | Current purpose | Primary dependencies | Assessment |
|---|---|---|---|
| `app/agent.py` | Backward-compatible ADK discovery entry point | Grocery agent | Keep as a compatibility shim until the Reference Agent package owns its entry point |
| `app/agents/` | Grocery ADK agent, deterministic extraction, Store/Delivery examples | Google ADK, shared-memory models/services | Split: agent runtime moves to Reference Agent; extraction can remain agent-owned |
| `app/tools/` | ADK tools that resolve and submit preferences | In-process platform bootstrap | Refactor to an authenticated Memory API client |
| `app/api.py` | Uvicorn entry point | FastAPI application factory and platform bootstrap | Move to Memory API |
| `app/config.py` | Google/ADK environment settings | environment and dotenv | Split into application-specific settings; centralize Google settings in Memory API |
| `app/logging_config.py` | JSON logging formatter | Python logging | Reuse in shared observability package or Memory API |
| `app/shared_memory/models/` | Runtime-neutral preference, candidate, result, and snapshot dataclasses | standard library | Move to Memory API domain; publish transport DTOs through contracts |
| `app/shared_memory/catalog/` | Loads generated canonical preference catalog | compiled JSON | Move to Memory API control/runtime modules |
| `app/shared_memory/policies/` | Loads domain and resolution policy artifacts | compiled JSON | Move to Memory API; later source from PostgreSQL active versions |
| `app/shared_memory/auth/` | Consumer capability and domain/key authorization | compiled registry and policies | Move to Memory API security; retain policy checks, replace authentication stub |
| `app/shared_memory/resolver/` | Pure deterministic resolver | models, catalog, policies | Reuse in Memory API domain with its unit tests |
| `app/shared_memory/services/` | Resolution orchestration, writes, cache, candidate routing | adapters, auth, resolver | Move to Memory API services; replace in-memory control-plane pieces incrementally |
| `app/shared_memory/adapters/` | Session, Memory Bank, Memory Profile, and mock profile integrations | `agentplatform.Client`, ADK tool state | Google adapters move to Memory API integrations; ADK tool-state adapter stays agent-side only if needed |
| `app/shared_memory/contracts/` | Typed YAML loader/compiler and generated consumer registry | Pydantic, PyYAML | Move to shared contracts/control-plane package and reuse from Memory API provisioning |
| `app/shared_memory/observability/` | Identifier hashing and structured event logging | Python logging | Reuse and extend in Memory API |
| `app/shared_memory/bootstrap.py` | Builds the entire platform from environment | all adapters/services | Replace with Memory API dependency injection; remove agent-side use after HTTP cutover |
| `app/shared_memory/demo.py` | In-memory deterministic acceptance scenario | platform services and test adapters | Move to test fixtures/demo package |
| `config/contracts/` | Domain-owned YAML source of truth | compiler models | Preserve during transition; import into PostgreSQL with version and audit metadata |
| `config/schemas/` | Generated JSON Schemas for YAML contracts | compiler | Move to shared contracts package; never hand-edit |
| `config/generated/` | Generated profile manifest | compiler | Keep as build/provisioning artifact until database-backed activation exists |
| `config/templates/` | Copyable domain onboarding templates | documentation | Keep in shared contracts package |
| `scripts/` | Contract validation, demo, deployment, inspection, seeding, ADK Web | current monolith imports | Re-home by owner; retain wrappers during migration |
| `tests/` | Unit, contract, platform, adapter, tool, and one cloud integration test | pytest/unittest, ADK/Google SDK | Preserve; split only after equivalent target tests pass |
| `.github/workflows/memory-contracts.yml` | Contract compile check and Python tests | GitHub Actions | Expand to per-application CI, frontend tests, image builds, and Terraform validation |
| `agents-cli-manifest.yaml` | Agent Runtime packaging metadata | Agent Platform tooling | Move to Reference Agent deployment assets |
| `docs/` | Architecture, setup, onboarding, operations, demos, draw.io diagrams | Markdown/draw.io | Preserve and revise as target components become real |

## Current runtime components

### Reference ADK agent

`app/agents/grocery_agent.py` defines `grocery_assistant` with Gemini and three tools. Its prompt
correctly tells the model not to query or resolve memory sources. However, the tools import
`platform_dependencies` and call the platform facade in the same process. This violates the target
deployment boundary even though the logical abstraction is already present.

`grocery_extraction.py` is a transparent regex-based POC extractor. It supports temporary and
long-term Grocery preferences, dynamic Grocery keys, and a Delivery candidate. It is intentionally
narrow and belongs with the Reference Agent, not the platform core.

### Shared Memory API

`app/api.py` exposes a FastAPI application with three routes:

| Current route | Behavior | Gap from target |
|---|---|---|
| `POST /v1/memory/context/resolve` | Builds an effective context | Rename/version under `/api/v1/runtime`; identity must come from authentication |
| `POST /v1/memory/preferences` | Submits a structured candidate | Add explicit-write and event-ingestion APIs with schema grants |
| `GET /v1/memory/users/{userId}/effective-context` | Resolves via query parameters | Retain only if needed; avoid user/agent identity ambiguity |

There are no `/api/v1/admin/*` routes. There is no raw-profile debugging endpoint, OpenAPI client
generation workflow, correlation-ID middleware, metrics endpoint, or database transaction layer.

### Authentication and authorization

`AuthorizationService.authenticate` only verifies that `user_id` and `agent_id` are non-empty.
`ConsumerRegistry` does provide useful fail-closed registration, domain matching, and operation
capability enforcement. Domain policies and catalog-level reader/writer lists provide a second
authorization layer.

This is authorization scaffolding, not workload authentication. The API currently trusts the
caller-provided agent ID. Production migration must verify a Google-signed ID token (or another
pluggable authenticator), map its principal to a registered agent, and ignore conflicting agent IDs
in request bodies.

### Resolution and snapshot behavior

`PreferenceContextService` retrieves Session values, explicit mock profile values, Memory Profiles,
and dynamic memories concurrently. Source failures degrade to warnings. It filters unauthorized or
invalid values, invokes the pure resolver, optionally strips provenance based on capability, and
caches the result.

The resolver groups by logical catalog key and applies configured strategies in order: source
priority, domain priority, explicit-over-inferred, recency, and confidence. It has no network or LLM
dependency. `EffectivePreferenceContext` carries resolved values, provenance, policy IDs, warnings,
and a snapshot version, but does not yet carry all schema versions required by the target design.

The in-memory cache key includes user, consumer domain, context hash, catalog version, and policy
version. It must evolve to use authenticated agent identity plus governed scope and become
replaceable by Redis.

### Preference writes and candidate routing

`SharedMemoryPlatformService` canonicalizes and validates a candidate, checks domain and catalog
write policy, stores Session scope through a session adapter, and writes authorized long-term values
as Memory Bank facts. Unauthorized cross-domain writes enter `InMemoryCandidateRepository` and are
not persisted to the owner domain.

The candidate repository is process-local and has no approval API or UI. Long-term canonical writes
are stored through the dynamic-memory create API; structured profile generation is a separate CLI
workflow. The target needs explicit preference semantics, event ingestion, durable access requests,
and durable audit records.

## Google and session integrations

| Integration | Current implementation | Important behavior/limitation |
|---|---|---|
| Agent Platform Sessions | Tool-context state delta, in-memory adapter, managed read adapter | Out-of-band managed writes are unsupported in the SDK path used; ADK writes must be event state deltas |
| Dynamic Memory Bank | `AgentPlatformMemoryBankAdapter` | Exact domain scope plus legacy `customer.grocery` read compatibility; create-only preference facts |
| Memory Profiles | `AgentPlatformMemoryProfileAdapter` | Retrieves per requested domain and rejects unknown/foreign schema fields using compiled owner registry |
| Profile generation | `scripts/generate_profile.py` | Calls `memories.generate` for a scope; installed API does not select a schema ID |
| Explicit profile | `MockProfileAdapter` | Static process data, not a real profile service or database |
| Deployment | `scripts/deploy.py` | Deploys ADK App/Agent Runtime and structured profile configuration; may create staging bucket |

All Google SDK access is already concentrated in adapters/scripts, which is reusable. The target
Memory API should own these calls. The current structured-profile schema-owner read guard must be
preserved. Because schemas share the same scope-key signature, provider-side generation may still
produce foreign-schema data; full write isolation may require separate Memory Bank resources or
independently selectable scope signatures.

## Contract and configuration model

The YAML contract system models domains, preferences, resolution policies, Memory Profiles, and
consumer capabilities. It validates cross-references and compiles eleven deterministic artifacts.
The current bundle contains five domains, eleven preferences, four profiles, four consumers, and
nineteen YAML files.

This is a good GitOps bootstrap and onboarding format. It is not the requested relational
control-plane model: approvals, grants, status transitions, schema versions, actors, and audit events
are not durable entities. Migration should import or seed active YAML definitions into normalized
PostgreSQL tables, while keeping export/compile compatibility until the database path is proven.

## Environment and deployment assessment

The project uses one `pyproject.toml`, one requirements file, one `.env.example`, and one Agent
Runtime deployment script. Current settings cover Google project/location, model, app/domain,
confidence, profile enablement, Agent Platform resource IDs, and staging bucket.

Missing target settings include `MEMORY_BACKEND`, `DATABASE_URL`, `AUTH_ENABLED`, `MEMORY_API_URL`,
token audience/issuer, CORS policy, and application-specific service settings. No secrets are tracked.

There are no Dockerfiles, `docker-compose.yml`, Node package, Terraform files, Cloud Run service
definitions, Cloud SQL configuration, Secret Manager bindings, Artifact Registry setup, or Alembic
migrations.

## Test baseline and gaps

Current automated coverage includes contract compilation, resolver behavior, authorization rules,
context degradation, candidate extraction, ADK tool identity, Memory Profile owner filtering,
profile service behavior, platform writes, snapshots, and the deterministic final scenario. One
integration test exercises configured Agent Platform resources when explicitly enabled.

Baseline on 2026-08-22:

```text
ruff:  all checks passed
pytest: 63 passed, 1 skipped, 5 dependency warnings
```

Missing tests correspond to missing capabilities: authenticated HTTP identity, schema-level grants,
scope registry and cross-user leakage, admin CRUD, access approval/revocation, database migrations,
event ingestion, explicit write authority, API client integration, React workflows, Docker Compose,
and end-to-end mock/Vertex parity.

## Existing component migration mapping

| Existing component | Current responsibility | Target application | Action |
|---|---|---|---|
| `app/agents/grocery_agent.py` | ADK root agent | Reference Agent | Move after HTTP client exists; keep compatibility import temporarily |
| `app/agents/grocery_extraction.py` | Grocery-specific extraction | Reference Agent | Move with tests |
| `app/agents/reference_consumers.py` | In-process Store/Delivery examples | Test fixtures/examples | Replace with HTTP consumer examples, then deprecate |
| `app/tools/preference_tools.py` | ADK-to-platform bridge | Reference Agent | Refactor from service calls to authenticated HTTP calls |
| `app/api.py` and `shared_memory/api` | REST facade | Memory API | Move and split into runtime/admin routers |
| Runtime preference dataclasses | Platform domain model | Memory API | Reuse; add API DTO mapping and schema-version metadata |
| Catalog and policy registries | Runtime configuration | Memory API | Reuse behind repository interfaces; later load active DB versions |
| Contract loader/compiler | GitOps configuration toolchain | Shared contracts package | Move without behavior change; add DB import/export path later |
| Authorization service | Domain/key/capability decisions | Memory API security | Reuse policy checks; introduce verified principal authenticator and schema grants |
| Consumer registry | Generated consumer capabilities | Memory API control plane | Migrate to RegisteredAgent and AgentSchemaGrant repositories |
| Preference resolver | Deterministic conflict resolution | Memory API domain | Move unchanged first; extend with agent schema precedence and ambiguity interface |
| Context and shared-memory services | Runtime orchestration | Memory API services | Move behind API; preserve degradation and provenance |
| Session adapters | ADK and managed Session state | Split | Tool-context adapter stays agent integration; managed/read abstractions move to API if needed |
| Memory Bank/Profile adapters | Google storage integration | Memory API integration | Move, wrap in `MemoryStore`, preserve schema-owner guard |
| `MockProfileAdapter` | Static explicit-profile data | Test fixtures | Replace with mock `MemoryStore`; retain fixtures until parity tests pass |
| In-memory snapshot cache | Effective-context cache | Memory API repository | Keep as default implementation; add Redis interface later |
| In-memory candidate repository | Cross-domain queue | Memory API control plane | Replace with PostgreSQL access/approval workflow after migration tests |
| `config/contracts` | Domain onboarding source | Shared contracts/control plane | Preserve; seed/import PostgreSQL and keep Git review workflow |
| Deployment and inspection scripts | Agent Runtime/cloud operations | Per-app operations | Split among Reference Agent, Memory API, infrastructure, and demos |
| Current tests | Regression safety net | Per-app/shared tests | Keep running at root until each target suite has equivalent coverage |
| Existing documentation | POC architecture/runbooks | Root docs | Preserve and update; mark obsolete statements during cutover |

## Obsolete or transitional code

Nothing should be deleted in Phase 0. The following are candidates for later retirement only after
replacement tests pass:

- `app/agent.py` compatibility entry point;
- in-process Store/Delivery reference consumers;
- direct `platform_dependencies` imports from ADK tools;
- static `MockProfileAdapter` production wiring;
- legacy `customer.grocery` scope reads;
- current unversioned `/v1/memory/*` routes;
- in-memory candidate repository; and
- root scripts whose responsibilities move into an application package.

## Phase 0 conclusion

The repository should be refactored, not rewritten. The resolver, contract compiler, normalized
models, service protocols, schema-owner guard, and most tests are reusable. The first implementation
slice must create deployment boundaries and a typed HTTP contract while leaving the current import
paths operational. No working code should be removed until the Reference Agent communicates with
the Memory API in an end-to-end mock test.
