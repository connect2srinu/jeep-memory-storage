# Current Memory Bank Architecture Validation

## Purpose

This document records the repository-backed validation of the shared-memory implementation. It supports
[ADR-0001](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md) and holds the
implementation detail the ADR omits.

Validation baseline:

- Branch reviewed: `feature/dynamic-household-members`
- Review date: 2026-09-23 (first review 2026-08-28 at `249dbc5` on `codex/org-project-governance`)
- Method: source inspection plus the repository's Python, frontend, and build checks

## Executive finding

The repository implements a credible enterprise control plane around Google Memory Bank: agents use a
platform API rather than the Google SDK; capabilities, schema grants, and purpose limitation gate
runtime operations; preferences are resolved deterministically; snapshots are cached in ADK session
state; household memory, confirmation turns, and a consent ledger are built in; and administrative
configuration is persisted in PostgreSQL with approval and audit records.

Since the first review, three of its production gates are closed: the Vertex adapter targets the
`agentplatform` 2.x surface and was exercised live, household scopes are supported end to end, and
dynamic-memory policy is enforced by the platform. The remaining production gates are organization read
isolation, global schema precedence, unsupported scope options in the wizard, write durability, two UI
defects, and IAM least privilege.

## Implemented architecture

```text
Admin user
  -> React Admin Console
  -> Control Plane API (admin plane)
  -> PostgreSQL: organizations, projects, memberships, domains, schemas and versions, agents, grants,
     policies, approvals, settings, household roster and aliases, consent ledger, audit

Customer
  -> ADK agent (memory-agent / reference-agent)
  -> Control Plane runtime API
       authenticate agent; check capability, grants, purpose
       find or create the customer's household (household setups)
       resolve the target member; screen sensitivity; confirm and record consent for health data
       read/write memory through the provider adapter
       resolve effective preferences
  -> Google Memory Bank or MockMemoryStore

Resolved snapshot
  -> ADK session state (resolved once per session)
  -> injected into model instructions and exposed through agent tools
```

### Application components

| Component | Responsibility |
|---|---|
| `apps/admin-console` | React/TypeScript admin UI: guided setup, organization/project workspace, domain detail, households, approvals, governance screens, Entra sign-in |
| `apps/control-plane-api` | FastAPI control plane and runtime gateway; SQLAlchemy persistence; capability, grant, scope, purpose, consent, policy, approval, retention, and audit enforcement |
| `apps/memory-agent` | Reference ADK agent: PostgreSQL sessions, governed long-term memory, household tools |
| `apps/reference-agent` | Minimal thin-consumer ADK agent |
| PostgreSQL | Governance metadata, workflow state, household roster, consent ledger. Not the preference-value store. |
| Memory provider adapter | `MockMemoryStore` or `VertexMemoryBankStore`, selected by `MEMORY_BACKEND` |

### Deployment components

Terraform defines Cloud Run services for the Control Plane API, Admin Console, and reference agent; a
Cloud Run migration job; private Cloud SQL for PostgreSQL; Artifact Registry; private networking;
Secret Manager; an external HTTPS load balancer with IAP; and Cloud Monitoring/Logging resources. It
does not create the Agent Engine / Memory Bank; activation updates an existing resource's memory context
configuration.

## Runtime read flow

1. The agent calls `POST /api/v1/runtime/preferences/resolve` once per session.
2. The API maps the authenticated principal to an active registered agent and checks `resolve_context`.
3. Active, unexpired grants whose schema allows the agent's purpose determine readable schemas.
4. For household schemas, the customer's household root is found or created.
5. For each readable schema, the adapter reads profiles and explicit overlays at that schema's exact
   scope (per-member schemas only when a member is named).
6. The resolver groups candidates by logical key and applies source, domain, explicitness, recency, and
   confidence rules.
7. The API returns values, provenance, schema and policy versions, writable attributes, approved topics,
   and the household roster.
8. The agent caches the snapshot in session state.

## Runtime write flows

### Explicit preference update

`PUT /api/v1/runtime/preferences/{attribute}` checks, before writing: authenticated agent;
`submit_candidates`; an active same-domain write grant allowed for the agent's purpose; a registered
attribute mapping; exact scope; for per-member attributes, the target member (matched, proposed, or
ambiguous) and guardian authority; the sensitivity screen; and for health data the confirmation and
consent gate.

The Vertex adapter retrieves the scope's existing facts to compute a write counter, then creates a new
typed fact. Its lock is process-local and does not provide concurrency control across Cloud Run
instances.

### Event submission

`POST /api/v1/runtime/memory/events` validates the same boundary, writes the candidate values, and
stores the event text as a fact. It never triggers provider generation. There is no Pub/Sub writer.

### Household operations

Add, rename, and merge members; move a value to another member; forget one value (withdrawing consent
for health data). All are scoped to the caller's own household.

## Governance and lifecycle capabilities

Persisted models and APIs exist for organizations, projects, and memberships; organization and project
settings; domains and scopes; schemas, versions, mappings, and the preference catalog; agents with
capabilities and purpose; schema grants and access requests; resolution policies (schema priorities
and attribute overrides); dynamic-memory policies; resource-change requests; runtime bindings and
health snapshots; the household roster, aliases, and consent ledger; retention sweeps; and append-only
audit events.

Schema edits use a versioned workflow: a new version is submitted, approved, and becomes active while
the previous one is deprecated; the runtime uses it without a restart. Domain edits use the same
change-request workflow.

## Scope and isolation behavior

The runtime supports exactly three provider scope shapes:

```text
organization_id + user_id
organization_id + household_id
organization_id + household_id + member_id
```

Any other key set is rejected. For household schemas, the household comes from the login; a request
naming another household is refused. Cross-organization reads work after an approved grant, reading the
owner organization's scope with the same identifiers. Cross-organization and cross-domain writes are
blocked.

## Production gates

| Gate (first review) | Status 2026-09-23 | Evidence / remaining work |
|---|---|---|
| **P0** Vertex SDK surface | ✅ Closed | Adapter and provisioner use `agentplatform` 2.x (`memory_banks.memories`, `runtimes.update`) and were exercised live against a real Agent Engine (DEART-56710 spike). The dependency range `google-cloud-aiplatform[agent_engines]>=1.112,<3.0` is still broad; pin it tighter. |
| **P0** Organization read isolation | ❌ Open | Settings, members, approvals, and runtime bindings check membership. Generic resource lists (`list_resources`) and `organization-hierarchy` still return every organization's records to any authenticated admin. |
| **P1** Global schema precedence | ❌ Open | The wizard stores schema priorities; the runtime loads only default rules and per-attribute overrides. Use attribute overrides until fixed. |
| **P1** Scope choices exceed runtime | 🟡 Partly closed | Per User, Per Household, and Household + members now work end to end. Per User + Store and Custom are still offered and still rejected at runtime. |
| **P1** Durable write guarantees | ❌ Open | No idempotency keys, outbox, retry queue, dead-letter handling, or distributed concurrency control. Provider `429` surfaces as HTTP 500. |
| **P1** UI settings overwrite | ❌ Open | Organization settings save email recipients, Monitoring channel IDs, and billed project IDs as empty and the threshold as 80% unless those fields were edited. |
| **P2** Approval action errors | ❌ Open | Loading errors are shown, but approve/reject/revoke actions have no error handling, so a denied decision (e.g. a purpose mismatch) fails silently in the UI. |
| **P2** Dynamic-memory policy enforcement | ✅ Closed | The platform enforces approved topics, per-topic sensitivity, confidence threshold, and retention on every dynamic write and resolve. |
| **P2** IAM breadth | ❌ Open | Runtime service accounts still hold `roles/aiplatform.user`; no Memory Bank-specific roles or IAM Conditions. |

## Validation results

Run on 2026-09-23 against the mock store:

| Check | Result |
|---|---|
| Python lint (`ruff check apps scripts tests`) | 1 error: `BLE001` in `scripts/memory_load_test.py` |
| Repository boundary tests | 5 passed |
| Control Plane API tests | 114 passed, 2 skipped (live-GCP and PostgreSQL integration tests are opt-in) |
| Reference agent tests | 9 passed |
| Memory agent tests | 3 passed |
| Admin Console tests / build | 17 passed / build succeeded |

These validate the control plane against the mock store. They don't validate live Memory Bank behavior
at scale, IAM Conditions, quotas, or failure recovery.

## Evidence map

| Finding | Repository area |
|---|---|
| Session cache, tools, confirmation contract | `apps/memory-agent/app/memory_agent/agent.py` |
| Runtime API client | `apps/memory-agent/app/memory_agent/client.py` |
| Runtime authorization, household context, consent, resolution | `apps/control-plane-api/app/control_plane_api/services/runtime_service.py` |
| Grants and resolution configuration | `apps/control-plane-api/app/control_plane_api/persistence/runtime_repository.py` |
| Member matching | `apps/control-plane-api/app/control_plane_api/domain/household_identity.py` |
| Vertex adapter | `apps/control-plane-api/app/control_plane_api/integrations/vertex_memory_store.py` |
| Provisioning | `apps/control-plane-api/app/control_plane_api/services/vertex_provisioning.py` |
| Governance, hierarchy, approvals | `apps/control-plane-api/app/control_plane_api/services/admin_service.py` |
| Retention | `apps/control-plane-api/app/control_plane_api/services/retention_service.py` |
| Data model | `apps/control-plane-api/app/control_plane_api/persistence/models.py`, `migrations/versions/` |
| Guided setup | `apps/control-plane-api/app/control_plane_api/services/guided_setup.py`, `apps/admin-console/src/features/memory-setup/` |
| Settings form | `apps/admin-console/src/features/organizations/OrganizationWorkspace.tsx` |
| Approval actions | `apps/admin-console/src/features/approvals/ApprovalsTable.tsx` |
| Cloud deployment | `infrastructure/terraform`, Docker Compose files |

## Production validation sequence

1. Enforce membership filtering on every organization/project read.
2. Load and test global schema precedence in the runtime resolver.
3. Hide or implement the Per User + Store and Custom scopes.
4. Add idempotency, retry/reconciliation, and `429` → `503` + `Retry-After` handling.
5. Fix the settings form and add error handling to approval actions.
6. Replace broad Vertex permissions with Memory Bank-specific roles and scope conditions.
7. Deploy to the landing zone and run live create, retrieve, delete, revision, quota, and failure tests.
8. Add telemetry for authorization decisions, provider operations, resolution outcomes, latency,
   quotas, and cost.

## Official references

- [Memory Bank overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank)
- [Memory profiles](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/profiles)
- [Generate memories](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/generate-memories)
- [Ingest events](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/ingest-events)
- [Memory revisions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/revisions)
- [Memory Bank IAM Conditions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/iam-conditions)
