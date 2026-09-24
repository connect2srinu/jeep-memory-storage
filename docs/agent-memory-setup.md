# Agent Memory Setup and Runtime Flows

## Purpose

The platform separates business preference ownership from agent implementation and provider SDK
details. PostgreSQL is the control-plane source of truth; Vertex Memory Bank stores customer memory;
the Control Plane API is the enforcement and resolution boundary.

## Components

| Component | Responsibility |
|---|---|
| Admin Console | Guided setup, organization/project workspace, households, governance screens |
| Control Plane API — admin plane | Organizations, projects, memberships, domains, schemas and versions, catalog, agents, grants, policies, approvals, households and consents, retention sweep, audit, provisioning |
| Control Plane API — runtime plane | Agent identity, scope checks, household context, reads, writes, confirmation and consent, deletion, resolution, provenance |
| PostgreSQL | Durable control-plane metadata, household roster and aliases, consent ledger, audit |
| `MemoryStore` | Provider-neutral persistence contract (`MockMemoryStore`, `VertexMemoryBankStore`) |
| Memory agent | Reference ADK agent: session snapshot injection plus memory and household tools |
| Reference agent | Minimal thin-consumer ADK agent |

## Onboarding flow

```text
Admin Console preview
  -> select an active organization and project
  -> validate domain-prefixed attributes, retention limits, and cross-references
  -> render a non-mutating activation preview

Admin Console activate
  -> create domain, scope(s), catalog preferences, schema(s), agent
  -> approve owned grants; submit shared-schema requests
  -> create resolution / dynamic-memory policies
  -> register schemas with the memory backend (Vertex: context_spec)
  -> audit
```

Activation never creates customer profiles; they are created by the first authorized write.

## Scopes

Each schema version is bound to one scope contract:

| Contract | Keys |
|---|---|
| `organization-user-profile` | `organization_id + user_id` |
| `organization-household-profile` | `organization_id + household_id` |
| `organization-household-member-profile` | `organization_id + household_id + member_id` |

Any other key set is rejected at runtime. For household schemas the platform works out the household
from the login: the ADK user ID is the household root, created on first use with surrogate IDs
(`hh_…`, `mbr_…`). A request naming another household is refused. See
[Dynamic Household Members](dynamic-household-members-design.md).

## Read flow

1. Authenticate and map the principal to one active registered agent.
2. Require `resolve_context` and the agent's own consumer domain in the request scope.
3. Load active, unexpired grants whose schema version allows the agent's purpose.
4. For household schemas, find or create the caller's household root.
5. For each readable schema, read profiles and explicit overlays at that schema's exact scope.
   Household-shared schemas are always read; per-member schemas are read only when the request names
   a member (lazy).
6. Normalize provider fields to canonical attributes and apply the resolution policy.
7. Return values with source, owner, reason, sensitivity, schema versions and provenance, plus
   `writablePreferences` / `writablePreferenceDetails` (level, description, health flag),
   `approvedTopics` / `approvedTopicDetails`, and for households `householdId`, `householdMembers`,
   `actingMemberId`, and `resolvedMemberId`.
8. The agent caches the snapshot in ADK Session state once per session and injects it before each
   model call.

Gemini uses the resolved result; it does not decide authorization or conflict resolution.

## Write flow

The model-facing tool sends an attribute and value, and for a per-member attribute optionally a
`memberId`, or a person's name and relationship. It never sends a schema ID.

The Control Plane API:

1. requires `submit_candidates` and the agent's consumer domain;
2. matches the attribute to exactly one active same-domain `WRITE` / `READ_WRITE` grant;
3. for a per-member attribute, works out the target member: the given `memberId`, a name matched
   inside the household (exact name, alias, or close variant), or a newly proposed member;
4. screens the value: restricted content is rejected; sensitive content must be user-directed;
5. for health data about someone else: refused for another adult (`not_allowed`); for a minor, needs a
   confirmation turn that records consent;
6. writes through `MemoryStore` and emits a `memory_write` audit event.

Every attempt, whatever the outcome, also emits a `memory_decision` log event with the key, schema
version, level, data type, sensitivity, reason, and the value masked for sensitive, restricted, and
health data. On the agent side, the memory agent logs `agent_memory_decision` events for its writes and
for statements its model decided not to save (the `record_memory_decision` tool).

A write that needs the customer's answer writes nothing and returns `200` with
`status: needs_confirmation` (and a platform-worded `confirmationPrompt`), `ambiguous` (with
`candidates`), or `not_allowed` (with `message`). The agent asks the question and repeats the call with
`confirmed: true` only after the customer says yes.

Other runtime operations: forget one value, move a value to another member, add / rename / merge
household members, forget a member or household, purge by tier/attribute/topic, and dynamic topic
writes. See the [Control Plane API README](../apps/control-plane-api/README.md).

## Vertex persistence model

Activation updates the Agent Engine `context_spec.memory_bank_config.structured_memory_configs`.
Memory Bank has no field-level structured-profile update, so each explicit write is stored as a typed,
exact-scope memory fact (schema ID, schema version, attribute, value, write counter, timestamp) and
overlaid on retrieved profiles at read time. The newest write of each field wins.

Memory Bank's managed extraction is **not** used: event submissions store the text as a fact but never
trigger provider generation, so no ungoverned memories are created. See
[Vertex Memory Bank](vertex-memory-bank.md).

## Ownership and sharing

- A canonical attribute has one owner domain.
- An owned schema contains only attributes owned by its domain.
- An agent may read an approved shared schema; read access never implies write access.
- Writes never select a cross-domain schema.
- An approved read grant covers the whole logical schema, including preferences added in later
  versions.

## Resolution

The resolver applies the policy's strategies in order — source priority, domain priority,
explicit-over-inferred, recency, confidence — with a minimum-confidence gate. Per-attribute overrides can
set a schema precedence. The Session snapshot is derived context, not a new source of truth.

## Capabilities

Capabilities authorize classes of runtime operations. They never grant access to data by themselves; a
capability is combined with the agent's registered domain, the exact request scope, and a schema grant.

A normal business agent created by guided setup has:

```json
{
  "resolve_context": true,
  "submit_candidates": true,
  "inspect_provenance": true,
  "administer_memory": false
}
```

| Capability | What `true` permits | Additional enforcement |
|---|---|---|
| `resolve_context` | Resolve the effective snapshot. | Only active schemas with `READ` / `READ_WRITE` grants the agent's purpose allows; request domain must be the agent's domain. |
| `submit_candidates` | Save preferences, dynamic memories, events; forget/move values; manage household members through the conversational endpoints; forget a user or household. | Target attribute must belong to a schema owned by the agent's domain with `WRITE` / `READ_WRITE`. |
| `inspect_provenance` | Include provenance in the snapshot and read raw provider profiles. | Raw profiles still require a readable grant for every requested schema. |
| `administer_memory` | Organization-wide `purge`, and the administrative roster endpoints (`PUT` / `DELETE /households/{id}/members/{id}`). | Admin console operations use admin identities and roles, not this flag. |

A write is accepted only when all of these hold:

```text
submit_candidates capability
  + authenticated principal maps to the registered agent
  + request scope matches the agent's consumer domain
  + attribute is owned by that domain
  + schema grant is WRITE or READ_WRITE (and allowed for the agent's purpose)
  + the target member is in the caller's household (per-member attributes)
  + the value passes the sensitivity screen and, for health data, the consent gate
```

## Failure model

- missing or invalid identity: `401`;
- capability, grant, purpose, household, or domain denial: `403`;
- invalid, unknown, or ambiguous attribute; restricted content; bad scope keys: `400`;
- missing resource: `404`;
- incompatible active resource: `409`;
- customer answer needed: `200` with `needs_confirmation`, `ambiguous`, or `not_allowed`, and nothing
  written;
- provider failure: the request fails; no fabricated success.

## Implementation invariants

- PostgreSQL is authoritative for organizations, projects, schemas, grants, policies, the household
  roster, and consent; Memory Bank is authoritative for stored values; Session snapshots are derived.
- A canonical attribute has exactly one owner domain; schema domain, scope domain, and attribute owner
  agree.
- Read never implies write, and writes never cross domains.
- Schema selection, member resolution, authorization, consent, and conflict resolution are
  deterministic server operations, not model decisions.

## Validation strategy

API and unit tests cover identity, grants, mapping, scope, household resolution, consent, purpose,
retention, and routing, all against the mock store. Frontend tests cover navigation, forms, and wizard
validation. A release still needs a live multi-Session Vertex scenario: provisioning, schema-less
write, later-Session recall, user and household isolation, and cross-domain denial. Agent response
quality belongs in agent evaluations.

## Current limitations

- Schema precedence from the wizard's Resolution step is stored but not applied at runtime; use
  per-attribute overrides.
- Per User + Store and Custom scopes are offered by the wizard but rejected by the runtime.
- Values are not checked against the catalog `data_type` or `allowed_values` at write time.
- Grants cover whole schemas; there is no per-attribute grant.
- The mock backend is process-local.

## Related guides

- [Guided Memory Setup](guided-memory-setup.md)
- [Memory Agent](../apps/memory-agent/README.md)
- [Vertex Memory Bank](vertex-memory-bank.md)
- [Admin API](admin-api.md)
- [Deployment and Operations](deployment-operations.md)
