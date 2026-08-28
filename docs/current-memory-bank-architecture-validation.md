# Current Memory Bank Architecture Validation

## Purpose

This document records the repository-backed validation of the current shared-memory implementation. It supports [ADR-0001](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md) and intentionally contains implementation detail that is omitted from the ADR.

Validation baseline:

- Repository: `jeep-memory-storage`
- Branch reviewed: `codex/org-project-governance`
- Baseline commit: `249dbc5`
- Review date: 2026-08-28
- Validation method: source inspection plus the repository's Python, frontend, and build checks

## Executive finding

The repository implements a credible enterprise control plane around Google Memory Bank: agents use a platform API rather than the Google SDK directly; agent capabilities and schema grants gate runtime operations; preferences are resolved deterministically; snapshots are cached in ADK session state; and administrative configuration is persisted in PostgreSQL with approval and audit records.

The architecture is not yet production-ready. The live Vertex adapter targets obsolete or unsupported SDK surfaces, organization membership is not consistently enforced by read APIs, configured global schema precedence is not loaded by the runtime resolver, and the UI advertises scopes that the runtime rejects. These are production gates, not reasons to replace the managed memory engine.

## Implemented architecture

```text
Admin user
  -> React Admin Console
  -> Control Plane API
  -> PostgreSQL control-plane database
       organizations, projects, domains, schemas, agents,
       grants, policies, approvals, settings, and audit events

Business user
  -> ADK Reference Agent
  -> Control Plane runtime API
       authenticate agent
       validate capability and active grants
       derive authorized owner scopes
       read/write memory through provider adapter
       resolve effective preferences
  -> Google Memory Bank or MockMemoryStore

Resolved snapshot
  -> ADK session state key: shared_memory:effective_snapshot
  -> injected into model instructions and exposed through agent tools
```

### Application components

| Component | Implemented responsibility |
|---|---|
| `apps/admin-console` | React/TypeScript administrative UI, guided setup, governance views, approvals, settings, and Entra placeholders. |
| `apps/control-plane-api` | FastAPI control plane and runtime gateway; SQLAlchemy persistence; capability, grant, scope, policy, approval, and audit enforcement. |
| `apps/reference-agent` | Google ADK reference consumer; calls only the Control Plane API, caches resolved preferences in session state, and exposes preference tools. |
| PostgreSQL | Stores governance metadata and workflow state. It is not the canonical preference-value store in the managed architecture. |
| Memory provider adapter | Selects the local mock backend or the intended Vertex Memory Bank backend. |

### Deployment components

The Terraform and container assets define Cloud Run services for the Control Plane API, Admin Console, and reference agent; a Cloud Run migration job; Cloud SQL for PostgreSQL; Artifact Registry; private networking; Secret Manager; an external HTTPS load balancer with IAP; and Cloud Monitoring/Logging resources.

The repository does not provision a Memory Bank or Agent Engine directly. It expects an existing resource identifier and attempts to update its memory context configuration during activation.

## Runtime read flow

The implemented preference-resolution flow is:

1. The reference agent sends `POST /api/v1/runtime/preferences/resolve`.
2. The Control Plane API resolves the authenticated principal to an active registered agent.
3. The API verifies the `resolve_context` capability.
4. Active, non-expired schema grants determine which schemas the agent may read.
5. For each readable schema, the API derives the schema owner's organization/user scope.
6. The provider adapter retrieves profile and explicit-overlay memories.
7. The resolver groups candidates by logical preference suffix and applies source, domain, explicitness, recency, and confidence rules.
8. The API returns values, provenance, schema versions, policy version, snapshot version, and writable attributes.
9. The reference agent stores the result in `shared_memory:effective_snapshot` for the ADK session.

This design already matches an important Unified Memory Layer principle: memory is read at a controlled session boundary and exposed to the model through a platform-owned integration.

## Runtime write flows

### Explicit preference update

`PUT /api/v1/runtime/preferences/{attribute}` performs these checks before writing:

- authenticated agent identity;
- `submit_candidates` capability;
- active write grant;
- registered attribute mapping;
- exact runtime scope;
- same-domain and same-organization ownership for writes.

The current Vertex adapter retrieves existing overlay memory and creates a new explicit overlay fact. Its process-local lock does not provide distributed concurrency control across Cloud Run instances.

### Conversation/event submission

`POST /api/v1/runtime/memory/events` validates the same agent and grant boundary, creates a natural event fact, and requests provider-side ingestion/generation. There is no repository implementation of a Pub/Sub memory-writer pipeline.

### Refresh

`POST /api/v1/runtime/preferences/refresh` repeats the authorized provider reads and resolution, returning a fresh snapshot to replace the ADK session cache.

## Governance and lifecycle capabilities

The repository contains persisted models and APIs for:

- organizations, projects, and memberships;
- organization and project settings;
- domains and scope definitions;
- profile schemas, immutable versions, mappings, and preference definitions;
- registered agents and capability declarations;
- schema grants and cross-organization access requests;
- resolution policies, schema priority records, and attribute overrides;
- dynamic-memory policies;
- resource-change requests and approvals;
- agent runtime bindings and health snapshots;
- append-only control-plane audit events.

Guided setup registers a schema and agent configuration locally while keeping user profile instances lazy. Owned-schema access can be approved during setup; shared-schema access remains subject to approval.

Schema edits use an additive version workflow. A draft version is reviewed, then activated while the prior version is deprecated. Destructive scope, mapping removal, and rename operations are restricted to reduce data-integrity risk. Domain edits also use a resource-change approval workflow.

## Scope and isolation behavior

The runtime currently enforces one exact provider scope shape:

```text
organization_id + user_id
```

The guided UI and metadata model also describe household, user-store, and custom scopes. Those choices are not implemented end to end: the runtime owner-scope builder rejects any scope that is not exactly organization plus user. They must be hidden or marked future until implemented.

Cross-organization reads are conceptually supported: an approved read grant causes the resolver to read the owner organization's schema using the same user identifier. Cross-organization writes are blocked. This is aligned with the intended organization/project governance model, subject to the authorization gaps below.

## Validated gaps and production gates

### P0 — Vertex SDK integration does not match the supported public API

The Vertex adapter calls `client.memory_banks`, `client.memory_banks.memories`, and `ingest_events` through that surface. Provisioning calls `client.runtimes.update`. The supported Agent Platform examples use `client.agent_engines.memories` and `client.agent_engines.update`.

The current dependency range is broad enough to install SDK versions whose public surface does not match the adapter. Mock-backed tests do not exercise this integration. `MEMORY_BACKEND=vertex` therefore requires correction and a live integration test before production use.

### P0 — Organization read isolation is incomplete

Several administrative read paths accept an organization identifier without consistently verifying the caller's organization membership. The hierarchy response can also enumerate organizations, projects, members, domains, and agents more broadly than the caller's membership permits. UI filtering is not an authorization boundary; these checks must be enforced in the API repository/service layer.

### P1 — Global schema precedence is persisted but not executed

Guided setup persists schema-priority records. The runtime repository loads default resolution rules and attribute-specific overrides, but does not load the global schema-priority rows. Consequently, the wizard's global `schemaPrecedence` configuration is not applied unless equivalent precedence is expressed through an attribute override.

### P1 — Scope choices exceed runtime support

The UI and database can represent `USER`, `HOUSEHOLD`, `USER_STORE`, and custom scope definitions. Only the organization-user scope is accepted by the runtime. This mismatch can produce configurations that activate successfully but fail when an agent uses them.

### P1 — Durable write guarantees are missing

The write path has no durable outbox, idempotency key store, retry queue, dead-letter handling, or distributed optimistic concurrency control. Provider event ingestion can supply some asynchronous consolidation, but the platform still needs deterministic request deduplication and observable failure handling around its own API boundary.

### P1 — UI settings can overwrite loaded values

Organization and project settings forms combine asynchronous `defaultValue` fields with shadow form state. Saving without touching a field can serialize empty arrays or fallback thresholds over values that were loaded from the API. Controlled form state and regression tests are required.

### P2 — Approval mutations need robust UI error handling

Approval actions do not consistently expose pending, failure, and retry states. Backend enforcement remains authoritative, but an operator needs visible correlation IDs and a stable result state.

### P2 — Dynamic-memory policy behavior is only partially validated

Dynamic policy metadata is persisted and included in provider context configuration, but the local resolver does not independently enforce the policy. Live Memory Bank behavior has not been validated because of the SDK integration issue.

### P2 — IAM is broader than the design intends

Terraform grants a general Vertex AI user role to the runtime service account. Google documents Memory Bank-specific roles and IAM Conditions for scope-aware access. The deployment should use least-privilege roles and conditions after the application scope contract is finalized.

## Validation results

At the reviewed baseline:

| Check | Result |
|---|---|
| Python lint | Passed |
| Python unit/integration tests | 63 passed, 2 skipped |
| Frontend type check | Passed |
| Frontend tests | 17 passed |
| Frontend production build | Passed |

These results validate the mock-backed and control-plane implementation. They do not validate live Vertex Memory Bank interoperability, IAM Conditions, provider quotas, or production failure recovery.

## Evidence map

| Finding | Primary repository area |
|---|---|
| ADK session cache and tool flow | `apps/reference-agent/app/reference_agent/agent.py` |
| Control Plane HTTP client | `apps/reference-agent/app/reference_agent/client.py` |
| Runtime authorization and resolution | `apps/control-plane-api/app/control_plane_api/services/runtime_service.py` |
| SQL-backed resolution configuration | `apps/control-plane-api/app/control_plane_api/repositories/sqlalchemy_runtime_repository.py` |
| Vertex provider adapter | `apps/control-plane-api/app/control_plane_api/integrations/vertex_memory_store.py` |
| Agent-platform provisioning | `apps/control-plane-api/app/control_plane_api/services/vertex_provisioning.py` |
| Governance resources and hierarchy | `apps/control-plane-api/app/control_plane_api/services/admin_service.py` |
| Persistent data model | `apps/control-plane-api/app/control_plane_api/db/models.py` and Alembic migrations |
| Guided setup | `apps/control-plane-api/app/control_plane_api/services/guided_setup_service.py` and Admin Console setup views |
| Organization settings form | `apps/admin-console/src/features/organizations/OrganizationWorkspace.tsx` |
| Cloud deployment | `infra/terraform` and Docker Compose files |

## Production validation sequence

1. Correct the Vertex SDK calls and pin/test a compatible SDK version.
2. Run live create, retrieve, profile, event-ingestion, revision, and rollback tests in an isolated GCP project.
3. Enforce membership filtering on every organization/project read and mutation.
4. Load and test global schema precedence in the runtime resolver.
5. Limit the UI to the supported user scope or implement the additional scope shapes end to end.
6. Add durable idempotency, retry, and reconciliation around writes.
7. Replace broad Vertex permissions with Memory Bank-specific roles and scope conditions.
8. Add production telemetry for authorization decisions, provider operations, resolution outcomes, snapshot versions, latency, quotas, and cost.

## Official references

- [Memory Bank overview and scaling documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank)
- [Memory profiles](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/profiles)
- [Generate memories](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/generate-memories)
- [Ingest events](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/ingest-events)
- [Memory revisions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/revisions)
- [Memory Bank IAM Conditions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/iam-conditions)
