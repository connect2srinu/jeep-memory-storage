# Domain Onboarding

This guide is for a domain owner adding governed preferences and connecting an ADK agent.

## Recommended path: Admin Console

1. Start the Vertex-backed stack as described in the root README.
2. Open `http://localhost:3000` and select **Create Memory Setup**.
3. Enter the use case, domain, and owning team.
4. Select existing catalog entries owned by the domain.
5. Add new canonical preferences with complete domain-prefixed IDs.
6. Choose the scope and memory behavior.
7. Register the agent and give its owned schema `READ_WRITE` if it saves preferences.
8. Request `READ` access to shared schemas instead of copying foreign attributes.
9. Order schemas when resolution is required.
10. review the generated preview and activate.

Example:

```text
Domain: travel
Preference: travel.seat_preference
Schema: travel-preferences-v1
Agent: travel-assistant
Owned permission: READ_WRITE
```

The schema name is generated and remains an internal platform detail.

## What the platform creates

- active domain and profile scope;
- canonical preference definitions;
- active version-1 structured profile schema and field mappings;
- registered agent and capabilities;
- automatically approved owned-schema grant;
- pending shared-schema access requests;
- resolution and dynamic-memory policies when selected;
- audit records;
- a Vertex `context_spec` update when the Vertex backend is configured.

Profiles are user-scoped and lazy. Onboarding never creates an empty profile for every user.

## Automated onboarding

PostgreSQL is the source of truth. Automation must call the versioned Admin API using an authorized
platform identity; it must not insert directly into tables or generate repository files. Use
`POST /api/v1/admin/memory-setups/preview` as the validation gate and
`POST /api/v1/admin/memory-setups/activate` to apply the same transaction used by the UI. Store the
reviewed request and response in the deployment system if an approval artifact is required.

## Connect the agent

```bash
cd apps/reference-agent
export MEMORY_API_URL=http://localhost:8080
export REFERENCE_AGENT_ID=travel-assistant
export PREFERENCE_DOMAIN=travel
export ADK_APP_NAME=travel_preferences
adk web --host 0.0.0.0 --port 8000 app
```

The user speaks naturally. The model selects from `writablePreferences`; it does not receive or
invent a schema ID.

## Completion checklist

- activation reports the intended backend;
- schema and agent are active;
- owned grant is `READ_WRITE` for write-capable agents;
- shared grants are explicitly approved and normally read-only;
- new attribute appears in `writablePreferences`;
- live write succeeds without `schemaId`;
- value resolves in a later Session for the same user;
- different users and domains remain isolated;
- audit and error responses contain correlation IDs.

## Current limitation

Adding fields to an already-active schema is not a wizard operation. Publish a reviewed new schema
version through the advanced Admin API and update the Agent Engine context before using the field.
