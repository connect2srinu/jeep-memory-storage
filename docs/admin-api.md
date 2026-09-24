# Control Plane Admin API

All administrative routes are under `/api/v1/admin`. The Admin Console uses the same API.

## Authentication and roles

Local mode (`AUTH_ENABLED=false`) accepts development-only `X-Admin-User`, `X-Admin-Roles`, and
`X-Admin-Domains` headers. Authenticated environments verify a Google token (IAP assertion or ID token)
with roles from the server-controlled `ADMIN_ROLE_BINDINGS_JSON`, or a Microsoft Entra ID token whose
app roles map to platform roles ([Entra setup](entra-authentication.md)).

Roles:

- `PLATFORM_ADMIN`: platform-wide administration;
- `PLATFORM_USER`: read access plus whatever persisted organization/project membership grants;
- `DOMAIN_ADMIN`: domain lifecycle and policy;
- `SCHEMA_OWNER`: owned schemas and access decisions;
- `AGENT_OWNER`: registered agent administration;
- `VIEWER`: read-only inspection.

Organization and project memberships are persisted and audited. An active organization `OWNER` or
`ADMIN` can manage that organization's settings, members, approvals, and child projects; a project
`OWNER` or `ADMIN` can manage that project's settings, members, and runtime bindings. Domain-scoped
roles come from the role binding (or local headers), not from membership. Generic resource lists and
the organization hierarchy are not yet filtered by membership: any authenticated admin can read them.

## Guided endpoints

```text
POST /memory-setups/preview
POST /memory-setups/activate
```

Preview is non-mutating. Activate creates the owned resources in one transaction, approves the owned
grants, leaves shared requests pending, registers schemas with the configured backend, and returns
resource IDs plus provisioning status. Profile instances stay lazy. Custom attribute IDs need the domain
prefix and a non-empty suffix; retention must be within the platform limits. See
[Guided Memory Setup](guided-memory-setup.md).

## Resource endpoints

List, create, read, and update (lifecycle transitions instead of deletes) for:

```text
/organizations  /projects  /domains  /scopes  /schemas  /preference-catalog
/agents  /resolution-policies  /dynamic-memory-policies
```

Notable fields:

- **Schemas / schema versions:** `retentionDays` (bounded per sensitivity tier: 1095 days normal,
  730 days sensitive or health) and `allowedPurposes` (default `["personalization"]`; `advertising` is
  never allowed for per-member or health schemas).
- **Agents:** `purpose` (`personalization`, `analytics`, or `advertising`); access is granted only to
  schemas whose active version allows it.
- **Preference catalog:** `sensitivityClassification`, `validationRules.health` for health data.

### Schema versions

```text
POST /schemas/{schema_id}/versions        submit a new version (returns 202, pending approval)
GET  /resource-change-requests            pending and decided change requests
POST /resource-change-requests/{id}/approve
POST /resource-change-requests/{id}/reject
```

Approving a version makes it `ACTIVE` and the previous version `DEPRECATED`. The runtime picks up the
new version on its next request; no restart is needed. Retention and purposes carry forward unless the
new version sets them. Domain edits use the same change-request workflow.

### Access requests

```text
GET  /access-requests
POST /access-requests
POST /access-requests/{id}/approve | /reject | /revoke | /expire
```

Approval creates or re-activates the agent-schema grant in the same transaction and checks that the
schema allows the agent's purpose. Rejection creates no grant; revocation or expiry disables it. A grant
covers the whole logical schema across versions.

## Organization workspace endpoints

```text
GET  /organization-hierarchy
POST /organizations/{organization_id}/members
POST /projects/{project_id}/members
GET  /organizations/{organization_id}/settings
PUT  /organizations/{organization_id}/settings
GET  /organizations/{organization_id}/approvals
GET  /projects/{project_id}/settings
PUT  /projects/{project_id}/settings
GET  /projects/{project_id}/health
POST /projects/{project_id}/health/refresh
GET  /agents/{agent_id}/runtime-binding
PUT  /agents/{agent_id}/runtime-binding
```

A principal must be an active member of the parent organization before receiving a direct project role.
Organizations are created `ACTIVE`; other governed resources follow their lifecycle transitions.

Organization settings persist budget amount, period, notification thresholds, recipients, Monitoring
channel IDs, Pub/Sub topic, billing account, and billed GCP projects. A budget-enabled update is marked
`PENDING_SYNC`; a deployment reconciler must create the Cloud Billing budget and record its name.

Project health is cached in `agent_health_snapshots`. Runtime bindings support Google Agent Runtime,
Cloud Run, and local ADK endpoints. Refreshing a Google Agent Runtime binding queries Cloud Monitoring;
provider or credential failures produce `UNKNOWN` health with details, not a false `UNHEALTHY`.

Organization approvals separate incoming requests (by the target schema's owning organization),
outgoing requests (by the requesting agent's organization), and decision history.

## Domain and access inspection

```text
GET /domains/{domain_id}/detail        Scopes, schemas (active version + mappings), home agents,
                                       resolution policies, pending requests, recent audit
GET /schemas/{schema_id}/agents        Agents that can access a schema: owning-project grant,
                                       cross-project grant, request pending, or eligible but not granted
GET /agents/{agent_id}/schema-access   Per-agent schema access matrix across the organization
```

Access is explicit-grant-only: an agent in the schema's owning project is *eligible* but has no access
until a grant exists. These endpoints report configured permission, not observed reads.

## Households, consent, and retention

```text
GET    /organizations/{org}/households
GET    /organizations/{org}/households/{household_id}/members
PUT    /organizations/{org}/households/{household_id}/members/{member_id}
DELETE /organizations/{org}/households/{household_id}/members/{member_id}
GET    /organizations/{org}/households/{household_id}/consents
POST   /organizations/{org}/retention/sweep
```

- Members carry kind (`ROOT`, `DEPENDENT`, `PROXY_ADULT`), `minor`, provenance, status (including
  provisional and merged), and aliases. Admin enrolment refuses a login that already belongs to another
  household.
- The consent ledger lists `PENDING`, `GRANTED`, `WITHDRAWN`, and `EXPIRED` health-data consents.
- The retention sweep deletes canonical values older than each schema version's `retentionDays`,
  expires provisional members after 60 days and pending consents after 24 hours, and records a
  `retention.swept` audit event. `dryRun` (the default) previews; `asOf` previews what would expire
  at a later date and is allowed only with `dryRun`.

The Admin Console's **Govern & manage → Households** screen uses these endpoints.

## Audit

`GET /audit` returns append-only admin audit events (actor, action, target, correlation ID, before and
after state). Runtime memory writes and deletions are logged as structured `memory_write` /
`memory_deletion` events in the API logs, not in this table; every write attempt is also logged as a
`memory_decision` event with its outcome and a masked value.

## Local example

```bash
curl http://localhost:8080/api/v1/admin/domains \
  -H 'X-Admin-User: local-admin@example.com' \
  -H 'X-Admin-Roles: PLATFORM_ADMIN'
```

## Interactive API documentation

The service publishes an OpenAPI 3 schema with `admin` and `runtime` tags:

- Swagger UI — `http://localhost:8080/docs`
- ReDoc — `http://localhost:8080/redoc`
- Raw schema — `http://localhost:8080/openapi.json`

`/healthz` and `/internal/metrics` are excluded from the schema.

## Error codes

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `INVALID_ARGUMENT` | Validation or cross-reference failure |
| 401 | `UNAUTHENTICATED` | Missing or invalid identity |
| 403 | `PERMISSION_DENIED` | Role, membership, domain, grant, or purpose denial |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Existing active resource is incompatible |

Every error includes a correlation ID for logs and audit investigation.
