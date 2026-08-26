# Shared Memory Admin API

All administrative routes are under `/api/v1/admin`. The Admin Console uses the same API.

## Authentication and roles

Local mode accepts development-only `X-Admin-User`, `X-Admin-Roles`, and `X-Admin-Domains` headers.
Authenticated environments verify a Google token and load roles from server-controlled bindings.
Organization and project memberships are persisted and audited, but this POC still requires
`PLATFORM_ADMIN` for organization/project membership mutations. Membership-derived authorization is
the next governance slice.

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
```

The hierarchy response groups organization members, projects, project members, domains, and agents.
A principal must be an active member of the parent organization before receiving a direct project
role. Organizations are created as `ACTIVE` immediately in this POC; other governed resources use
their existing lifecycle transitions.

Use lifecycle transitions instead of deleting governed records. Access approval creates or updates
the active agent-schema grant in the same transaction. Rejection creates no grant; revocation or
expiry disables it.

## Local example

```bash
curl http://localhost:8080/api/v1/admin/domains \
  -H 'X-Admin-User: local-admin@example.com' \
  -H 'X-Admin-Roles: PLATFORM_ADMIN'
```

OpenAPI is available at `http://localhost:8080/docs`.

## Error codes

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `INVALID_ARGUMENT` | Validation or cross-reference failure |
| 401 | `UNAUTHENTICATED` | Missing or invalid identity |
| 403 | `PERMISSION_DENIED` | Role/domain/grant denial |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Existing active resource is incompatible |

Every error includes a correlation ID for logs and audit investigation.
