# Agent Memory Setup and Runtime Flows

## Purpose

The Shared Memory Platform separates business preference ownership from agent implementation and
provider SDK details. PostgreSQL is the control-plane source of truth; Vertex Memory Bank stores
user-scoped memory; the Memory API is the enforcement and resolution boundary.

## Components

| Component | Responsibility |
|---|---|
| Admin Console | Guided onboarding and governed administration |
| Memory API admin plane | Domains, schemas, agents, grants, policies, audit, provisioning |
| Memory API runtime plane | Identity, scope checks, reads, writes, resolution, provenance |
| PostgreSQL | Organizations, projects, memberships, and durable control-plane metadata |
| `MemoryStore` | Provider-neutral persistence contract |
| Vertex adapter | Structured profile retrieval, explicit overlays, event ingestion |
| Reference ADK agent | Thin tools and Session snapshot injection |

## Onboarding flow

```text
Admin Console preview
  -> select an active organization and project
  -> validate domain-prefixed attributes and cross-references
  -> render a non-mutating activation preview

Admin Console activate
  -> create domain, scope, preferences, schema, agent
  -> approve owned grant; submit shared requests
  -> create resolution/dynamic policies
  -> apply all active schemas to Agent Engine context_spec
  -> audit
```

Schema activation never creates user profile instances. Profiles remain lazy.

Organizations are immediately `ACTIVE` in the POC because no organization approval workflow is
implemented. Project membership requires active membership in the parent organization. Other
governed resources retain their documented lifecycle and approval behavior.

## Read flow

1. Authenticate and map the principal to one active registered agent.
2. Require `resolve_context` and an exact consumer-domain scope.
3. Load active readable schema grants and their field mappings.
4. Retrieve structured profiles and explicit overlays at exact `organization_id + user_id` scope.
5. Normalize provider fields to canonical preference attributes.
6. Apply deterministic resolution rules.
7. Return values, source, owner, reason, schema versions, provenance, and
   `writablePreferences`.
8. Cache the snapshot in ADK Session state and inject it before Gemini runs.

Gemini formats or applies the resolved result; it does not decide authorization or conflict
resolution.

## Write flow and automatic schema resolution

The model-facing tool sends `attribute` and `value`, optionally with original text. It does not send
`schemaId`.

The Memory API:

1. requires `submit_candidates`;
2. requires request domain = registered agent domain;
3. matches the canonical attribute or profile field against active grants;
4. retains only same-domain `WRITE` or `READ_WRITE` grants;
5. chooses the grant only when exactly one match remains;
6. maps the canonical attribute to the provider profile field;
7. persists through `MemoryStore`;
8. refreshes the effective snapshot.

No match or multiple matches returns `400`; read-only/cross-domain attempts return `403`. Trusted
legacy clients may still supply an explicit schema ID, but it receives the same authorization and
ownership checks.

## Vertex persistence model

Activation updates the Agent Engine `context_spec.memory_bank_config.structured_memory_configs`.
Explicit updates are stored as typed exact-scope memory facts because the provider does not expose a
direct field-level structured-profile update API. These facts are overlaid on retrieved structured
profiles for immediate platform reads. Event writes also call Memory Bank event ingestion so
provider profile generation can occur asynchronously.

## Ownership and sharing

- A canonical attribute has one owner domain.
- An owned profile schema contains only attributes owned by its domain.
- An agent may read an approved shared schema.
- Read access never implies write access.
- Automatic writes never select a cross-domain schema.
- A foreign preference must be updated by its owner-domain workflow, not copied into a consumer
  schema.

## Resolution

The resolver applies configured strategies in order, including source priority, schema/domain
priority, explicit-over-inferred preference, recency, and confidence. Output contains the winning
value and explanation. A Session snapshot is derived context, not a new source of truth.

## Capabilities

| Capability | Meaning |
|---|---|
| `resolve_context` | Resolve the authorized effective snapshot |
| `submit_candidates` | Submit explicit updates or memory-event candidates |
| `inspect_provenance` | Receive source/schema provenance and inspect raw profiles |
| `administer_memory` | Administrative operation; not granted to normal consumer agents |

Capabilities permit an operation class; schema grants determine the data the operation may access.

## Failure model

- missing/invalid identity: `401`;
- capability, grant, or domain denial: `403`;
- invalid, unknown, or ambiguous attribute: `400`;
- missing resource: `404`;
- incompatible active resource: `409`;
- provider failure: request fails; no fabricated success response;
- shared approval pending: no active grant until approval.

## Implementation invariants

- PostgreSQL is authoritative for organization/project ownership, schemas, grants, and policy.
- Memory Bank is authoritative for managed user memory; Session snapshots are derived context.
- A canonical preference attribute has exactly one owner domain.
- Schema domain, scope domain, and canonical attribute owner agree.
- Read access never implies write access, and automatic writes never cross domains.
- Schema selection, authorization, and conflict resolution are deterministic server operations, not
  Gemini decisions.

## Validation strategy

Use API/unit tests for identity, grant, mapping, scope, and routing behavior. Use frontend tests for
directory, organization/project navigation, forms, and wizard validation. A release still requires
a live multi-Session Vertex scenario for schema provisioning, schema-less write, later-Session
recall, user isolation, and cross-domain denial. ADK response quality belongs in agent evaluations;
deterministic platform contracts belong in code tests.

## Current limitations

- The guided wizard creates version 1 and cannot append fields to an active schema.
- Managed profile generation is asynchronous.
- The local mock backend is process-local.
- A real multi-Session Vertex write/recall smoke test is required for release acceptance.

## Related guides

- [Guided Memory Setup](guided-memory-setup.md)
- [ADK Web Demo](adk-web-demo.md)
- [Vertex Memory Bank](vertex-memory-bank.md)
- [Admin API](admin-api.md)
- [Deployment and Operations](deployment-operations.md)
