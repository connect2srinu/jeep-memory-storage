# Control Plane Admin API

All administrative routes are under `/api/v1/admin`. The Admin Console uses the same API.

## Authentication and roles

Local mode accepts development-only `X-Admin-User`, `X-Admin-Roles`, and `X-Admin-Domains` headers.
Authenticated environments verify a Google token and load roles from server-controlled bindings.
Organization and project memberships are persisted, audited, and enforced. An active organization
`OWNER` or `ADMIN` can manage organization settings, members, approvals, and all child projects. A
project `OWNER` or `ADMIN` can manage that project's settings, members, and runtime bindings.
`PLATFORM_ADMIN` retains global access.

Roles:

- `PLATFORM_ADMIN`: platform-wide administration;
- `DOMAIN_ADMIN`: domain lifecycle and policy;
- `SCHEMA_OWNER`: owned schema and access decisions;
- `AGENT_OWNER`: registered agent administration;
- `VIEWER`: read-only inspection.

## Guided endpoints

```text
POST /memory-setups/preview
POST /memory-setups/activate
```

Preview is non-mutating. Activate creates the owned resources transactionally, approves the owned
grant, leaves shared requests pending, provisions the configured backend, and returns resource IDs
plus provisioning status. Profile instances remain lazy.

Custom attribute IDs must contain a non-empty suffix and use the selected domain prefix. Owned
write-capable agents require `WRITE` or `READ_WRITE` permission.

## Resource endpoints

CRUD/lifecycle endpoints cover:

- organizations and projects;
- domains and scopes;
- preference catalog;
- schemas and versions;
- agents;
- resolution and dynamic-memory policies;
- access requests and approvals;
- audit events.

Organization workspace endpoints:

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

Domain and access inspection endpoints:

```text
GET /domains/{domain_id}/detail        Aggregated domain view: scopes, schemas (with active version
                                       and preference mappings), home agents, resolution policies,
                                       pending requests, and a recent audit slice, in one call.
GET /schemas/{schema_id}/agents        Agents that can access a schema, each labelled owning-project
                                       grant, cross-project grant, request-pending, or eligible but
                                       not granted.
GET /agents/{agent_id}/schema-access   Per-agent schema access matrix across the organization.
```

Access is explicit-grant-only: an agent in the schema's owning project is *eligible* but is not
granted access until an explicit grant exists. These endpoints report configured permission, not
observed read activity, which the platform does not currently track.

The hierarchy response groups organization members, projects, project members, domains, and agents.
A principal must be an active member of the parent organization before receiving a direct project
role. Organizations are created as `ACTIVE` immediately in this POC; other governed resources use
their existing lifecycle transitions.

Organization settings persist budget amount, period, actual/forecast notification thresholds,
recipients, Monitoring channel IDs, Pub/Sub topic, billing account, and billed GCP projects. A
budget-enabled update is marked `PENDING_SYNC`; a deployment reconciler must create/update the
Cloud Billing budget and set its external name before it is considered cloud-synchronized.

Project health is cached in `agent_health_snapshots`. Runtime bindings support Google Agent Runtime,
Cloud Run, and local ADK endpoints. Refreshing a Google Agent Runtime binding queries Cloud
Monitoring for the `aiplatform.googleapis.com/ReasoningEngine` resource. Provider or credential
failures produce `UNKNOWN` health with diagnostic details, not a false `UNHEALTHY` result.

Organization approval results separate incoming requests, outgoing requests, and decision history.
Incoming requests are determined from the target schema's owning domain and organization; outgoing
requests are determined from the requesting agent's immutable organization ID.

Use lifecycle transitions instead of deleting governed records. Access approval creates or updates
the active agent-schema grant in the same transaction. Rejection creates no grant; revocation or
expiry disables it.

## Local example

```bash
curl http://localhost:8080/api/v1/admin/domains \
  -H 'X-Admin-User: local-admin@example.com' \
  -H 'X-Admin-Roles: PLATFORM_ADMIN'
```

## Interactive API documentation

The service publishes an OpenAPI 3 schema with per-plane tags (`admin`, `runtime`), a description of
the response envelope and error model, and operation summaries. Browse it locally at:

- Swagger UI — `http://localhost:8080/docs`
- ReDoc — `http://localhost:8080/redoc`
- Raw schema — `http://localhost:8080/openapi.json`

Operational endpoints (`/healthz`, `/internal/metrics`) are intentionally excluded from the schema.

## Error codes

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `INVALID_ARGUMENT` | Validation or cross-reference failure |
| 401 | `UNAUTHENTICATED` | Missing or invalid identity |
| 403 | `PERMISSION_DENIED` | Role/domain/grant denial |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Existing active resource is incompatible |

Every error includes a correlation ID for logs and audit investigation.
