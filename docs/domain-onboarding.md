# Domain Onboarding

This guide is for a domain owner adding governed preferences and connecting an ADK agent.

## Recommended path: Admin Console

1. Start the stack as described in the root [README](../README.md).
2. Open `http://localhost:3000` and click **Organizations** at the top of the left panel.
3. Create or open the owning organization. New organizations are `ACTIVE` immediately.
4. Open **Projects**, create or select the project, and add organization members before assigning any
   direct project roles.
5. Select **Create Memory Setup** and follow the wizard ([Guided Memory Setup](guided-memory-setup.md)):
   use case and domain, preferences, scope, memory behavior, and agent.
6. Give the agent `READ_WRITE` on its owned schema if it saves preferences.
7. Request `READ` access to other teams' schemas instead of copying their attributes.
8. Review the non-mutating preview and activate.

Example:

```text
Domain:            travel
Preference:        travel.seat_preference
Schema:            travel-preferences-v1   (generated; an internal platform detail)
Agent:             travel-assistant
Owned permission:  READ_WRITE
```

For families, choose the **Household + members** scope: the wizard generates a household-shared
schema and a per-member schema, and the platform manages each customer's household at runtime. See
[Household Memory — End-to-End UI Guide](dynamic-household-test-guide.md).

## What the platform creates

- an active domain and its scope definition(s);
- canonical preference definitions;
- active version-1 schema(s) and field mappings;
- the registered agent and its capabilities;
- automatically approved owned-schema grants;
- pending access requests for shared schemas;
- resolution and dynamic-memory policies when selected;
- audit events;
- a Vertex `context_spec` update when the Vertex backend is configured.

Profiles are created lazily by the first authorized write. Organizations, projects, and domains are
authorization metadata in PostgreSQL, not Memory Bank scope keys.

## Automated onboarding

PostgreSQL is the source of truth. Automation calls the versioned Admin API with an authorized platform
identity; it must not insert directly into tables. Use `POST /api/v1/admin/memory-setups/preview` as the
validation gate and `POST /api/v1/admin/memory-setups/activate` to apply the same transaction the UI
uses. Store the reviewed request and response if an approval artifact is required.

## Connect the agent

Use the [memory agent](../apps/memory-agent/README.md) as the reference implementation, or follow
[New Agent Onboarding](new-agent-onboarding.md) to add the same memory tools to your own agent:

```bash
cd apps/memory-agent
CONTROL_PLANE_API_URL=http://localhost:8080 \
REFERENCE_AGENT_ID=travel-assistant \
PREFERENCE_DOMAIN=travel \
SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory \
.venv/bin/python -m memory_agent.serve
```

The customer speaks naturally. The model chooses from `writablePreferences`; it never receives or
invents a schema ID or a member ID.

## Adding preferences later

Publish a new schema version from **Govern & manage → Schemas → Create new version** and approve it in
**Govern & manage → Approvals**. The new version is used without restarting the API; start a new agent
session to see it. Existing values are kept, and approved access for other teams' agents continues to
apply to the whole schema (including new fields).

## Completion checklist

- activation reports the intended backend;
- schema(s) and agent are active;
- the owned grant is `READ_WRITE` for write-capable agents;
- shared grants are explicitly approved and read-only;
- new attributes appear in `writablePreferences`;
- a live write succeeds without `schemaId`;
- the value resolves in a later Session for the same user;
- different users, households, and domains stay isolated;
- audit events and error responses carry correlation IDs.
