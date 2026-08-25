# Organization and Project Governance Gap Analysis

## Status

Analysis only. No runtime, database, UI, or infrastructure implementation has been changed.

## Current architecture

| Area | Existing implementation | Assessment |
|---|---|---|
| Admin UI | React 19 and Vite. A guided memory-setup wizard and generic JSON-backed resource screens call the Admin API. | EXTEND |
| API | FastAPI with Pydantic request/response models and separate `/api/v1/admin` and `/api/v1/runtime` routes. | EXISTS |
| Persistence | PostgreSQL 16/Cloud SQL, SQLAlchemy asyncio, and Alembic. PostgreSQL stores control-plane metadata rather than user profile values. | EXISTS |
| Memory Bank | `VertexMemoryBankStore` uses `agentplatform.Client`, `retrieve_profiles`, memory retrieval/creation, and event ingestion. A mock store supports local development. | EXTEND |
| Profiles and schemas | Domains, scope definitions, profile schemas and versions, preference mappings, and Vertex schema definitions are normalized in PostgreSQL. | EXTEND |
| Preference catalog | Canonical attribute ID, owner domain, type, validation, sensitivity, and resolution metadata exist. | EXTEND |
| Resolver | `PreferenceResolver` is deterministic and runs in the API. It supports source priority, domain priority, explicit-over-inferred, recency, confidence, expiry, and provenance. | EXISTS |
| Effective snapshot | Runtime API authenticates an agent, loads active schema grants, retrieves Memory Bank profiles, resolves values, and returns versioned snapshots. | EXTEND |
| Agent integration | The reference ADK agent calls only the Shared Memory API and does not import the Memory Bank SDK. | EXISTS |
| Runtime authorization | Agent identity, capabilities, schema grants, same-domain write protection, and provenance checks are enforced server-side. | EXTEND |
| Admin authorization | IAP or Google ID-token authentication exists. Roles and domain assignments come from environment JSON; local mode uses trusted development headers. | REFACTOR |
| Access workflow | Schema-level requests, approval/rejection/revocation/expiry, schema grants, and audit records exist. | REFACTOR |
| Audit | Mutations create audit rows containing actor, action, target, correlation ID, and before/after metadata. | EXTEND |
| Infrastructure | Terraform creates Cloud Run services, private Cloud SQL, Secret Manager secrets, IAP, service accounts, networking, logging metrics, alerts, and dashboards. | EXTEND |

## Reuse map

| Requirement | Classification | Direction |
|---|---|---|
| Organization hierarchy | NEW | Add organizations and organization memberships. |
| Project hierarchy and RBAC | NEW | Add projects and direct project memberships; compute Organization Owner project access as inherited authorization. |
| Domains and agents | EXTEND | Add owning project and organization foreign keys; preserve current domain/agent IDs and runtime registrations. |
| Schema ownership and visibility | EXTEND | Add owning project, optional owner agent, visibility, and lifecycle metadata to existing profile schemas. |
| Preference attributes | EXTEND | Add `shareable`, lifecycle status, and soft-removal metadata to existing preference definitions/mappings. |
| Access requests | REFACTOR | Extend the existing request table with organization/project/domain context and selected-field child rows. Restrict cross-project permission to `READ`. |
| Active grants | REFACTOR | Evolve the existing agent-schema grant into an explicit directional grant and add field child rows. Preserve nullable `expires_at` for future use but create indefinite grants initially. |
| Approval concurrency | REFACTOR | Use one transactional conditional update (`PENDING` to decision) and create the grant in the same transaction. |
| Same-project access | EXTEND | Compute project-local read access without a cross-project request; only the designated owner receives default write authority. |
| Schema evolution | NEW | Add schema-field lifecycle operations that leave new fields ungranted and deactivate removed fields in active grants transactionally. |
| Notifications | NEW | Add a provider-neutral notification service and transactional outbox; the database remains authoritative. |
| Runtime field enforcement | EXTEND | Add an `AccessPolicyService` before profile retrieval/adaptation and filter retrieved profiles to authorized field mappings. |
| Resolver precedence | EXISTS | Preserve the current deterministic resolver and documented source ordering. Do not create another resolver. |
| Session/external/default candidates | EXTEND | The resolver models these sources, but the current runtime path supplies Memory Profile candidates only. Add adapters deliberately without changing precedence silently. |
| Admin navigation and workflows | REFACTOR | Introduce organization/project context, membership screens, catalog discovery, request wizard, approvals, grants, and audit views while retaining useful memory setup screens. |
| Audit protection | EXTEND | Add organization/project/resource context and required event names; protect rows from application update/delete operations. |
| Policy performance | EXTEND | Replace per-grant repository queries with joined/batched queries and indexes. Add caching only with a revocation-safe invalidation/version strategy. |

## Primary gaps and conflicts

1. There are no organization, project, user, organization-membership, or project-membership tables. Current roles (`PLATFORM_ADMIN`, `DOMAIN_ADMIN`, `SCHEMA_OWNER`, `AGENT_OWNER`, `VIEWER`) are not the required organization/project `OWNER`, `ADMIN`, and `VIEWER` roles.
2. Admin role bindings are environment JSON, not persisted membership. List and audit operations are broadly readable after a role check and are not organization/project scoped.
3. Current access requests and grants authorize a complete schema and allow `WRITE`/`READ_WRITE`. The new release requires directional, cross-project, field-level, read-only access.
4. Approval performs a read followed by mutation. It is not an atomic compare-and-set and can race between two reviewers.
5. Existing grants are keyed only by agent and schema. They do not record organization, requesting/target projects and domains, source request, field selection, revoker, or decision reason.
6. Schema and preference records lack visibility, shareability, designated owner-agent, and field soft-removal semantics. Cascading deletes can erase grant relationships rather than preserve audit history.
7. Guided setup auto-approves an owned schema request and creates schema-wide pending requests for shared schemas. It must switch to implicit same-project ownership plus field selection for cross-project sharing.
8. The UI sends local persona role/domain headers and contains navigation-level mutation checks. This is acceptable only for local development; production authorization must be derived from the authenticated subject and persisted memberships.
9. The runtime retrieves a full granted profile. Schema-wide grants currently make that valid, but field grants require filtering before values become resolver candidates and before `raw_profiles` returns data.
10. `RuntimeControlPlaneRepository.list_schema_grants` performs repeated queries per grant. Field authorization will magnify this N+1 pattern unless replaced with a batched query.
11. Runtime resolution currently uses only `MEMORY_PROFILE` candidates even though the resolver supports session, explicit external, dynamic/inferred, and default sources.
12. Scope is hard-coded as `user_id + app_name + domain`. Cross-domain reads replace only `domain` and retain the consumer application's `app_name`, which can miss an owner profile created under a different app name. Governance ownership and Memory Bank scope isolation are coupled.
13. Terraform grants the reference agent `roles/aiplatform.user`. The code uses the API boundary, but this broad role can permit direct Memory Bank access and weakens the intended enforcement point.
14. The Vertex adapter stores explicit updates as custom natural-memory JSON overlays. Current Google Memory Profiles expose structured-profile field memories, revisions, and Memory update operations; the structured write path should be evaluated instead of treating the overlay as the permanent design.
15. There is no notification abstraction or transactional outbox.

## Recommended design

### Identity and RBAC

- Add `users` (or external principals), `organizations`, `organization_memberships`, `projects`, and `project_memberships`.
- Persist the verified authentication subject and email; derive roles from database memberships.
- Keep `PLATFORM_ADMIN` only as an explicitly governed platform/break-glass role.
- Compute Organization Owner access to every child project. Do not materialize duplicate project membership rows.
- Require organization membership before inserting project membership.
- Scope every admin query by the authorization context to prevent IDOR and cross-tenant metadata disclosure.

### Ownership and sharing

- Add `project_id` to domains and agents, and owning project/domain plus optional owner agent and visibility to schemas.
- Add `shareable` and soft-removal state to preference definitions or schema-version fields.
- Extend/rename the existing access request and grant models rather than creating parallel schema-grant workflows.
- Store selected fields in request/grant child tables with foreign keys to stable schema-field metadata.
- Treat same-project reads as implicit policy. Treat owner-agent writes as implicit ownership policy. Do not create an approval request for these cases.
- Keep all cross-project grants directional and `READ` only.

### Runtime enforcement

- Preserve `RuntimeMemoryService` and `PreferenceResolver` as the only resolution path.
- Add an `AccessPolicyService` that returns authorized schemas plus exact attribute mappings for the authenticated agent.
- Fetch only authorized schemas where possible and always filter profile dictionaries to granted fields before creating resolver candidates.
- Apply the same field filtering to diagnostics such as `raw_profiles`.
- Include a safe internal grant reference in provenance, but do not expose sensitive governance details to ordinary agents.
- Batch the agent, project, schema, field, and policy lookup into a small number of indexed queries.

### Scope and Memory Bank

- Do not add organization/project/domain identifiers to Memory Bank scope solely for governance.
- Prefer a documented user-oriented scope such as `{"user_id": "..."}`; add `organization_id` only if tenant isolation requires it.
- Treat any change from the current three-key scope as a data migration because Memory Bank retrieval requires exact, immutable scope matching.
- Keep schema definitions and governance mappings in PostgreSQL, but keep profile values and revisions in Memory Bank.
- Prototype structured-profile field create/update/patch against the current Agent Platform API before replacing the existing explicit overlay.

### Audit and notifications

- Extend audit rows with organization, project, resource type/id, and structured metadata.
- Emit explicit governance events in the same transaction as each state change.
- Use soft deletion for schema fields and transactionally deactivate affected grant fields.
- Introduce `NotificationService` behind a transactional outbox. An email adapter can be added later without coupling workflow state to delivery success.

### IAM

- Grant the Memory API a specialized Memory Bank role (`memoryViewer`, `memoryEditor`, or `memoryUser`) based on required operations instead of broad `roles/aiplatform.user` where possible.
- Give business-agent identities only Shared Memory API invocation and the minimum model-inference permissions. Explicitly exclude Memory Bank permissions so normal credentials cannot bypass API governance.
- Use Memory Bank IAM Conditions only as defense in depth for coarse scope boundaries, not for application field grants.

## Proposed implementation sequence

1. Add organizations, projects, users/memberships, persisted RBAC, and scoped admin authorization; migrate existing domains into an initial organization/project.
2. Add project/domain/schema/agent ownership, schema visibility, shareable fields, and catalog discovery.
3. Extend existing access requests with field child rows and read-only cross-project validation.
4. Add atomic approval, explicit field grants, revoke/cancel behavior, and same-project implicit access.
5. Extend the current runtime repository and resolver input path with field-level `AccessPolicyService` enforcement.
6. Add schema-field evolution and grant cleanup with audit events.
7. Add notification outbox and adapters; harden append-only audit behavior.
8. Refactor the React navigation and implement organization/project/member/catalog/request/approval/grant screens.
9. Add RBAC, workflow concurrency, field filtering, schema evolution, bypass prevention, integration, and UI tests; update documentation.

## Design deviations to approve before implementation

1. Use implicit same-project access instead of creating same-project grant/request rows.
2. Retain nullable expiration columns for forward compatibility while issuing indefinite grants in this release.
3. Start with batched indexed authorization queries and no cross-instance cache; add caching only after a revocation-safe invalidation mechanism is defined.
4. Plan an explicit Memory Bank scope migration instead of silently changing the current exact scope.
5. Replace environment-based admin role bindings with database memberships after bootstrap, while retaining a narrowly controlled platform bootstrap path.

## Official Google behavior validated

- Memory Profiles use static schemas, maintain one profile per schema and exact scope, and represent profile fields as individual structured-profile Memory resources.
- Memory scope matching is exact and a memory's scope is immutable.
- Memory resources support update operations and revision history.
- Specialized Memory Bank IAM roles and scope-based IAM Conditions are available; these should complement rather than replace application governance.

References:

- https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/profiles
- https://docs.cloud.google.com/python/docs/reference/agentplatform/latest/vertexai._genai.memories.Memories
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/iam-conditions
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1beta1/projects.locations.memoryBanks.memories/patch
