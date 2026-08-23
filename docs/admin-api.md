# Shared Memory Admin API

## Boundary and authentication

The Admin Console and automation clients call only `/api/v1/admin/*`. Admin operations never call
Memory Bank directly. Every mutation writes an audit event in the same database transaction.

For local development with `AUTH_ENABLED=false`, send:

```text
X-Admin-User: owner@example.com
X-Admin-Roles: DOMAIN_ADMIN,SCHEMA_OWNER
X-Admin-Domains: grocery,customer
```

For authenticated environments, send a Google ID token with the configured
`GOOGLE_ID_TOKEN_AUDIENCE`. The server maps its verified email using
`ADMIN_ROLE_BINDINGS_JSON`; role or domain headers cannot grant production permissions.

```json
{
  "owner@example.com": {
    "roles": ["SCHEMA_OWNER"],
    "domains": ["customer"]
  }
}
```

## Roles

| Role | Effective responsibility |
|---|---|
| `PLATFORM_ADMIN` | Create domains and platform policies; administer every domain |
| `DOMAIN_ADMIN` | Manage governed resources and access decisions for assigned domains |
| `SCHEMA_OWNER` | Manage schemas and decide requests targeting assigned domains |
| `AGENT_OWNER` | Manage agents and request their cross-domain access |
| `VIEWER` | Read control-plane resources and audit without mutation rights |

## Resource operations

Each resource supports list and create. Stable-ID resources also support get and patch:

```text
domains
scopes
schemas
preference-catalog
agents
resolution-policies
dynamic-memory-policies
```

Creation starts lifecycle-managed records in `DRAFT`. A patch contains optional metadata changes
and a status transition:

```json
{
  "status": "PENDING_APPROVAL",
  "changes": {
    "description": "Updated governed description"
  }
}
```

Allowed lifecycle paths are:

```text
DRAFT -> PENDING_APPROVAL -> APPROVED -> ACTIVE -> DEPRECATED -> RETIRED
  |             |              |           ^             |
  +-> RETIRED   +-> DRAFT      +-> RETIRED +-------------+
```

Invalid transitions return HTTP `409`. Unknown records return `404`; authentication and
authorization failures return `401` and `403` respectively. Physical deletion is intentionally not
available for governed records.

Schema creation is atomic: the request includes the first immutable schema version, its scope
definition, Vertex-compatible schema, generation configuration, and canonical attribute-to-profile
field mappings. The API rejects missing preferences, cross-domain mappings, and duplicate fields or
attributes. A schema lifecycle transition also moves its versions so a partially active schema
cannot reach the runtime.

Resolution-policy requests include ordered `schemaPriorities` and attribute-specific
`attributeOverrides`. Policy patches replace these ordered controls transactionally and accept the
same camelCase transport names used during creation.

## Access request flow

An agent owner requests cross-domain access:

```bash
curl -X POST http://localhost:8080/api/v1/admin/access-requests \
  -H 'Content-Type: application/json' \
  -H 'X-Admin-User: grocery-owner@example.com' \
  -H 'X-Admin-Roles: AGENT_OWNER' \
  -H 'X-Admin-Domains: grocery' \
  -d '{
    "requestingAgentId": "grocery-agent",
    "requestingTeam": "grocery-platform",
    "targetSchemaId": "customer-preferences-v1",
    "requestedPermission": "READ",
    "businessReason": "Apply fulfillment preferences",
    "expiration": "2026-12-31T23:59:59Z"
  }'
```

An owner of the target schema domain decides it:

```bash
curl -X POST \
  http://localhost:8080/api/v1/admin/access-requests/REQUEST_ID/approve \
  -H 'Content-Type: application/json' \
  -H 'X-Admin-User: customer-owner@example.com' \
  -H 'X-Admin-Roles: SCHEMA_OWNER' \
  -H 'X-Admin-Domains: customer' \
  -d '{}'
```

Other terminal actions use `/reject`, `/revoke`, or `/expire`. Approval activates the agent/schema
grant; rejection does not create one. Revocation and expiry disable the existing grant. None of
these operations copies, moves, or deletes user memory.

## Audit and API discovery

Read audit events with `GET /api/v1/admin/audit`. Events contain actor, action, target, correlation
ID, timestamp, and metadata-only before/after state. Preference values are not written by these
control-plane routes.

Interactive OpenAPI documentation is available at `http://localhost:8080/docs`.
