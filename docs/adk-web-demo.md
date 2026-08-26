# ADK Web End-to-End Demo

This script proves UI onboarding, platform-managed schema selection, Vertex persistence, and
cross-Session recall. It does not ask the user or model for schema IDs.

## 1. Start the Vertex-backed platform

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export AGENT_PLATFORM_MEMORY_BANK_ID=YOUR_AGENT_ENGINE_ID

docker compose \
  -f docker-compose.yml \
  -f docker-compose.vertex.yml \
  up --build
```

Verify `http://localhost:8080/healthz` and open `http://localhost:3000`.

## 2. Onboard a demo domain in the Admin Console

From **Organizations**, create or open an organization, create a project, and then start **Create
Memory Setup**. Example ownership:

```text
Organization: retail-demo
Project: travel-experiences
```

Create:

```text
Use case: Travel Personalization
Domain: travel
Preference: travel.seat_preference
Type: string
Allowed values: aisle, window, middle
Agent ID: travel-assistant
Owned schema permission: READ_WRITE
```

Preview and activate. The result must show:

```text
Schema: travel-preferences-v1
Status: PROVISIONED
Backend: VertexMemoryBankStore
Profile instances created: 0
```

`profileInstancesCreated: 0` is normal because user profiles are lazy.
The default provider scope is `organization_id + user_id`; the project/domain registration controls
which schemas the agent may resolve or update.

## 3. Start ADK Web

Stop an existing ADK process before changing its environment.

```bash
cd apps/reference-agent
export MEMORY_API_URL=http://localhost:8080
export MEMORY_API_TOKEN=""
export MEMORY_API_AUDIENCE=""
export REFERENCE_AGENT_ID=travel-assistant
export PREFERENCE_DOMAIN=travel
export ADK_APP_NAME=travel_preferences

adk web --host 0.0.0.0 --port 8000 app
```

Open `http://localhost:8000/dev-ui/?app=reference_agent`. Use user ID `travel-demo-001` and create a
new Session.

## 4. Inspect the writable allowlist

Prompt:

```text
What preferences can you update for me?
```

The resolved snapshot should include:

```json
{
  "writablePreferences": ["travel.seat_preference"]
}
```

If the list is empty, verify the agent ID/domain and its active `READ_WRITE` grant.

## 5. Save a preference naturally

Prompt:

```text
I always prefer a window seat.
```

Expected tool arguments:

```json
{
  "attribute": "travel.seat_preference",
  "value": "window"
}
```

There must be no `schemaId`. The platform maps the attribute to the single writable
`travel-preferences-v1` grant. The tool refreshes the snapshot after a successful write.

## 6. Read it back

Prompt:

```text
What preferences are you currently using?
```

Expect `travel.seat_preference = window`, with owner domain `travel` and provenance when the agent
has `inspect_provenance`.

## 7. Prove cross-Session behavior

Create a new Session for the same user `travel-demo-001` and ask:

```text
Which seat should you choose for me?
```

The new Session resolves the stored preference before the first model call. Provider-generated
profiles can consolidate asynchronously; retry resolution after a short interval if inspecting the
managed profile itself. The explicit platform overlay is the immediate read-after-write path.

## 8. Prove user isolation

Create user `travel-demo-002` and ask for current preferences. It must not inherit the first user's
seat preference.

## 9. Prove write protection

If the agent has `READ` access to a shared customer schema, ask it to update a customer-owned
attribute. The agent should refuse because the attribute is absent from `writablePreferences`; a
direct request must return `403`.

## Troubleshooting

| Symptom | Check |
|---|---|
| `REGISTERED_LOCAL` | Start Compose with `docker-compose.vertex.yml` |
| `403` on write | Agent ID, domain, `submit_candidates`, and owned `READ_WRITE` grant |
| Empty `writablePreferences` | Active field mapping and same-domain writable grant |
| Old tool asks for schema ID | Stop and restart ADK Web |
| Unknown preference | Onboard the canonical attribute; do not invent an ID |
| Existing schema rejects a new field | Publish a reviewed new schema version |
| Value not visible in provider profile immediately | Memory Bank generation is asynchronous |

## Success criteria

- onboarding reports `PROVISIONED`;
- the agent receives the expected writable allowlist;
- the write tool contains no schema ID;
- the correct same-domain schema receives the value;
- a later Session for the same user resolves it;
- a different user does not;
- a shared read-only schema cannot be updated.
