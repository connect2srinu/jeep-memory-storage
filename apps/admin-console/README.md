# Memory Admin Console

The React Admin Console is the human control-plane client for `/api/v1/admin/*`. It never calls
Memory Bank directly. It provides role-aware pages for domains, scopes, schemas, preference
catalog, agents, access requests, approvals, resolution policies, dynamic-memory policies, and
audit.

## Run locally

Start the Memory API on port 8080, then run:

```bash
cd apps/admin-console
npm install
npm run dev
```

Open `http://localhost:5173`. To proxy to a different local API:

```bash
MEMORY_API_PROXY_TARGET=http://127.0.0.1:8081 npm run dev -- --port 3002
```

The persona bar supplies the local `X-Admin-*` development identity. Select a role and its assigned
domains to exercise API-enforced guards. In authenticated deployments, these headers do not grant
permissions; verified Google principals use server-controlled `ADMIN_ROLE_BINDINGS_JSON` entries.

## Workflows

- Resource pages list current records and offer governed JSON creation templates when the role can
  mutate that resource.
- Schema creation includes an inline Vertex schema preview and normalized duplicate detection for
  canonical attributes/profile fields.
- Resolution Policy creation exposes ordered schema priorities with up/down controls.
- Access Requests and Approvals expose request, approve, reject, revoke, and expiry states.
- Audit is read-only and shows the actor, action, target, time, and correlation ID.

Run the frontend gate:

```bash
npm run typecheck
npm test
npm run build
npm audit --audit-level=moderate
```

The browser workflow validates API connectivity, schema data/preview, viewer role guards, resource
navigation, policy ordering, and audit rendering against a current Memory API.
