# Memory Admin Console

The React Admin Console is the human client for `/api/v1/admin/*`. It never calls Vertex Memory Bank or
other Google Cloud APIs directly.

## Navigation

- **Organizations** (the button at the top of the left panel): the organization directory. Selecting an
  organization card sets it as the context and adds **Organization → Overview / Projects / Members &
  Roles**; opening a project adds **Project → Overview / Domains / Agents / Members & Roles**. A
  project's domain opens a detail view with Overview, Schemas, Preference Catalog, Agent Access,
  Resolution, Sharing, and Audit tabs (read-only).
- **Create Memory Setup**: the guided wizard.
- **Govern & manage**: Organizations & Projects, Households, Domains, Scopes, Schemas, Preference
  Catalog, Agents, Access Requests, Approvals, Resolution Policies, Dynamic Memory Policies, Audit.

Schema edits (**Create new version**) happen in **Govern & manage → Schemas** with an organization
selected; approvals (schema versions, domain changes, access requests) happen in **Govern & manage →
Approvals**. **Households** shows each household's members, kinds, aliases, the consent ledger, and the
retention sweep.

## Create Memory Setup

```text
Use Case -> Preferences -> Scope -> Memory -> Agents -> [Sharing] -> [Resolution] -> Review -> Activate
```

The wizard validates domain-prefixed custom attributes (including a *Health data* flag), assigns
preferences to household or member tiers for the **Household + members** scope, checks retention limits,
previews the plan, and sends one activation request. Activation creates or reuses the domain and
scope(s), creates the owned schema(s), registers the agent, grants owned access, creates shared-access
requests, and registers the schemas with the runtime backend.

Choose `READ_WRITE` for an owned schema when the agent must save preferences. Shared schemas are `READ`
and stay pending until the owning team approves them. Vertex activation reports `PROVISIONED`;
`REGISTERED_LOCAL` indicates the mock backend. No customer profiles are created at activation.

See [docs/guided-memory-setup.md](../../docs/guided-memory-setup.md) and the
[end-to-end UI guide](../../docs/dynamic-household-test-guide.md).

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

## Identity

With Entra disabled, the console sends development-only `X-Admin-*` headers built from
`VITE_LOCAL_ADMIN_USER`, `VITE_LOCAL_ADMIN_ROLE`, and `VITE_LOCAL_ADMIN_DOMAINS` (rebuild after changing
them). With `VITE_ENTRA_AUTH_ENABLED=true` users sign in with Microsoft Entra ID and the console sends
the access token. See [docs/entra-authentication.md](../../docs/entra-authentication.md). The API is the
security boundary; the console only hides actions a role can't perform.

## Validation

```bash
npm run typecheck
npm test
npm run build
npm audit --audit-level=moderate
```
