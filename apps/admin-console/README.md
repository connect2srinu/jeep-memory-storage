# Memory Admin Console

The React Admin Console is the human control-plane client for `/api/v1/admin/*`. It never calls
Vertex Memory Bank directly.

## Primary workflow

Use **Create Memory Setup** for new domains:

```text
Use Case -> Preferences -> Scope -> Memory -> Agent -> Sharing -> Resolution -> Review -> Activate
```

The wizard validates domain-prefixed custom attributes, previews the generated contract, and sends
one activation request. Activation creates or reuses the domain and scope, creates the owned schema,
registers the agent, grants owned access, creates shared-access requests, and provisions the
configured runtime backend.

Choose `READ_WRITE` for an owned schema when the agent must save preferences. Shared schemas should
normally be `READ`; they remain pending until the owning domain approves them.

Successful Vertex activation reports `PROVISIONED`. `REGISTERED_LOCAL` indicates the mock backend.
No user profiles are created at activation time; they remain lazy.

## Run locally

The Compose stack serves the console at `http://localhost:3000`:

```bash
docker compose up --build
```

For frontend development:

```bash
cd apps/admin-console
npm install
npm run dev
```

Open `http://localhost:5173`. Override the API proxy when necessary:

```bash
CONTROL_PLANE_API_PROXY_TARGET=http://127.0.0.1:8081 npm run dev -- --port 3002
```

The local persona bar supplies development-only `X-Admin-*` headers. Authenticated deployments
ignore those headers and use verified Google principals with server-controlled role bindings.

## Advanced administration

**Manage / Advanced** exposes domains, scopes, schemas, catalog entries, agents, access requests,
approvals, resolution policies, dynamic-memory policies, and audit events. Existing active schemas
are immutable through the wizard; adding fields requires a reviewed new schema version.

## Validation

```bash
npm run typecheck
npm test
npm run build
npm audit --audit-level=moderate
```

See `docs/guided-memory-setup.md` for the complete onboarding and validation flow.
