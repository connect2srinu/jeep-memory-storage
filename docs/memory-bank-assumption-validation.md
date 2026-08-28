# Memory Bank Assumption Validation

## Purpose

This document separates verified behavior, repository-specific assumptions, and unresolved questions for the managed Memory Bank option. It is supporting evidence for [ADR-0001](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md).

Status labels:

- **VALIDATED** — supported by current repository behavior or current official Google documentation.
- **PARTIAL** — some layers implement the behavior, but the end-to-end path is incomplete.
- **NOT VALIDATED** — present as configuration or intent without a successful provider-backed proof.
- **CONFLICT** — the implementation contradicts the assumption.
- **OPEN QUESTION** — a product or governance decision is still required.

## Assumptions and findings

| ID | Assumption | Status | Finding / required action |
|---|---|---|---|
| MB-01 | Business agents do not need direct Google Memory Bank access. | VALIDATED | The reference agent calls the Control Plane API only. Keep the provider SDK and credentials inside the platform boundary. |
| MB-02 | The Control Plane API validates agent identity, capability, scope, and grants before memory access. | PARTIAL | Runtime endpoints validate the registered agent, capabilities, active grants, writable mappings, and exact scope. Administrative read APIs still require consistent organization-membership enforcement. |
| MB-03 | Resolved preferences are loaded once at the session boundary and cached in ADK session state. | VALIDATED | The reference agent stores the result under `shared_memory:effective_snapshot` and supports explicit refresh after a write. |
| MB-04 | One profile can be maintained per schema and scope. | VALIDATED | This is the documented Memory Bank profile model. The repository registers schemas and leaves user profile instances lazy. |
| MB-05 | Memory Bank performs extraction and consolidation from ingested events. | VALIDATED / NOT LIVE-TESTED | Google documents extraction, consolidation, profile generation, and asynchronous event ingestion. The repository intends to call those capabilities, but its current SDK integration must be fixed before the live path is proven. |
| MB-06 | Memory Bank provides revision history and rollback. | VALIDATED / NOT LIVE-TESTED | Google documents immutable memory revisions and rollback. The repository does not yet expose a complete operator workflow for provider revisions. |
| MB-07 | `organization_id + user_id` can isolate profiles across organizations in one Memory Bank. | PARTIAL | The application builds that exact scope and Google supports arbitrary scope dictionaries with IAM Conditions. Isolation still depends on correct API enforcement and least-privilege IAM; current admin reads and broad runtime IAM are gaps. |
| MB-08 | All configured scope types are usable at runtime. | CONFLICT | The runtime accepts only exact organization/user scope. Household, user-store, and custom scope options are not end-to-end implementations. |
| MB-09 | Cross-organization schema reads work after approval and writes remain owner-only. | PARTIAL | The runtime reads an approved schema using its owner organization's scope and blocks cross-owner writes. The hierarchy/listing APIs must be hardened so discovery and approval data are also isolated. |
| MB-10 | Configured schema precedence controls resolution. | PARTIAL | Attribute overrides are loaded, but global schema-priority rows created by guided setup are not loaded by the runtime repository. |
| MB-11 | Dynamic-memory preprocessing/policy takes effect in a subsequent session. | NOT VALIDATED | Policy metadata is persisted and intended to update provider context configuration. Live provider behavior and propagation timing have not been demonstrated with the current adapter. A session refresh/new session is still required to observe a changed snapshot. |
| MB-12 | Explicit writes are idempotent and concurrency-safe. | CONFLICT | The adapter uses a process-local lock and creates overlay facts. It lacks durable idempotency, distributed locking/OCC, retry state, and reconciliation. |
| MB-13 | Event ingestion is durably decoupled from the agent request. | PARTIAL | Memory Bank `IngestEvents` is designed for asynchronous generation, but the application calls the provider in the request path and has no platform outbox or Pub/Sub retry layer. |
| MB-14 | Event overlap is deduplicated. | PARTIAL | Google documents event-ID-based deduplication for overlapping streams. The application must supply stable event identifiers and verify behavior; current production integration is unproven. |
| MB-15 | Provider quotas and operational costs are observable. | NOT VALIDATED | Infrastructure includes basic monitoring, but the repository does not yet provide provider-operation, token, quota, or per-organization cost attribution sufficient for production budgets. |
| MB-16 | Current Terraform deploys the complete managed memory resource. | CONFLICT | Terraform deploys the application stack and accepts an existing Agent Engine/Memory Bank resource identifier. It does not create the managed memory resource itself. |
| MB-17 | The current Vertex adapter uses the supported public SDK surface. | CONFLICT | It targets `memory_banks` and `runtimes`; current official examples use `agent_engines.memories` and `agent_engines.update`. Correct and live-test before production. |
| MB-18 | Existing tests prove production Memory Bank compatibility. | CONFLICT | Tests and builds pass against local/mocked components. They do not exercise a real Memory Bank, IAM Conditions, quotas, revisions, or failure recovery. |
| MB-19 | Control-plane audit records are equivalent to complete memory lineage. | PARTIAL | Control-plane mutations capture correlation and before/after state. Provider memory revisions and field-level provenance must be correlated to deliver end-to-end lineage. |
| MB-20 | A single Memory Bank is always the correct topology for every organization. | OPEN QUESTION | A shared bank can be logically isolated by scope and IAM Conditions. Regulatory residency, encryption keys, blast radius, quotas, or hard tenant boundaries may justify separate banks/projects for selected organizations. |

## Provider semantics that should shape the design

### Profiles and generation

Google describes memory profiles as structured, schema-driven memory associated with a scope. Generation extracts and consolidates information into the profile. This is materially more than a key/value store and overlaps the proposed UML extraction, consolidation, provenance, and revision responsibilities.

### Streaming ingestion

`IngestEvents` decouples event submission from generation. Google documents generation triggers based on event count, idle time, or explicit controls, with automatic flushing. A platform Pub/Sub pipeline should therefore be justified by application-level durability, backpressure, replay, or audit needs—not by assuming Memory Bank lacks asynchronous ingestion.

### Revisions

Memory Bank maintains immutable revision history. The platform should expose revision IDs and rollback through its governance API instead of building a second competing revision mechanism for managed profiles.

### IAM and scope

Google supports Memory Bank-specific roles and IAM Conditions over scope values. The application should combine those provider controls with its database grants. The database authorization decision is the business-policy layer; provider IAM is defense in depth.

## Decisions still required before production

1. **Tenant topology:** one shared bank, one bank per regulatory boundary, or a tiered model.
2. **Scope contract:** keep only organization/user initially, or implement household/store/custom shapes before exposing them.
3. **Write durability:** synchronous provider request plus idempotency, transactional outbox plus worker, or another reliable delivery pattern.
4. **Conflict semantics:** which source wins, when confirmation is required, and whether domain owners can override another domain's value.
5. **Deletion and privacy:** user erasure, retention, legal hold, consent, sensitive-field masking, and audit retention.
6. **Cost attribution:** allocation by organization, project, agent, schema, read/write operations, generation tokens, and storage.
7. **Provider failure policy:** fail closed, return a last-known snapshot, or degrade to defaults for each use case.
8. **Migration:** how profile schema versions and provider revisions are reconciled during additive schema changes.

## Recommended validation tests

- Create two organizations with the same `user_id`; prove that neither can enumerate or resolve the other's profiles without an approved grant.
- Approve a cross-organization read grant; prove the consumer resolves the shared field but cannot write it.
- Revoke and expire the grant; prove access disappears without restarting the API.
- Configure conflicting values in multiple schemas; prove global precedence and attribute overrides independently.
- Submit duplicate event IDs and repeated explicit write idempotency keys; prove a single effective mutation.
- Run concurrent writes from multiple Cloud Run instances; prove deterministic conflict behavior.
- Update a dynamic policy; measure propagation and prove the next session's generated snapshot reflects it.
- Inspect provider revision history, roll back, refresh, and prove the snapshot version and provenance change.
- Exercise IAM Conditions directly with allowed and denied scopes.
- Inject provider timeouts, throttling, partial failure, and retry exhaustion; prove the user-visible and operational outcomes.

## Official references

- [Memory profiles](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/profiles)
- [Generate memories](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/generate-memories)
- [Ingest events](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/ingest-events)
- [Memory revisions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/revisions)
- [Memory Bank IAM Conditions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/iam-conditions)
