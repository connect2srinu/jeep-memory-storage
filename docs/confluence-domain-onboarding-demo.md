# Shared Memory Platform: New Domain Onboarding and Demo Runbook

## Goal

Create a new domain and preference in the Admin Console, provision the schema to Vertex Memory Bank,
connect the reference ADK agent, save a preference without supplying a schema ID, and retrieve it in
a later Session.

## Example

```text
Use case: Travel Personalization
Domain: travel
Preference: travel.seat_preference
Allowed values: aisle, window, middle
Agent: travel-assistant
Owned permission: READ_WRITE
Generated schema: travel-preferences-v1
```

## Admin Console steps

1. Open `http://localhost:3000` and select **Create Memory Setup**.
2. Enter the use case and owning team.
3. Add `travel.seat_preference`; do not leave an ID ending in `travel.`.
4. Choose user profile scope and memory settings.
5. register `travel-assistant` with owned `READ_WRITE` access.
6. Add shared schemas only if required; shared requests remain pending.
7. Review the schema precedence when sharing is enabled.
8. Preview the generated contract.
9. Activate.

For a cloud-backed demonstration, activation must report:

```text
PROVISIONED
VertexMemoryBankStore
profileInstancesCreated: 0
```

Zero profiles is expected because user profiles are lazy.

## ADK Web steps

```bash
cd apps/reference-agent
export MEMORY_API_URL=http://localhost:8080
export REFERENCE_AGENT_ID=travel-assistant
export PREFERENCE_DOMAIN=travel
export ADK_APP_NAME=travel_preferences
adk web --host 0.0.0.0 --port 8000 app
```

Open `http://localhost:8000/dev-ui/?app=reference_agent`, choose user `travel-demo-001`, and prompt:

```text
I always prefer a window seat.
```

Expected tool data:

```json
{
  "attribute": "travel.seat_preference",
  "value": "window"
}
```

No schema ID should be present. The platform derives `travel-preferences-v1` from the registered
agent and its active same-domain writable grant.

Ask:

```text
What preferences are you currently using?
```

Create a new Session for the same user and ask again. Then create a different user and verify the
value is absent.

## Expected controls

- `writablePreferences` contains only domain-owned writable attributes;
- shared `READ` attributes cannot be updated;
- unknown attributes fail instead of being invented;
- ambiguous mappings fail instead of selecting arbitrarily;
- profile generation may be asynchronous;
- the explicit platform overlay provides immediate platform read-after-write behavior.

## GitOps alternative

Regulated or bulk onboarding can use `config/templates/domain-onboarding`, contract validation, and
deterministic compilation. The UI and GitOps paths represent the same resource model; do not run a
separate command-line profile-generation script as the normal onboarding path.

## Completion checklist

- correct backend status;
- active domain/schema/agent;
- active owned `READ_WRITE` grant;
- preference visible in `writablePreferences`;
- schema-less ADK write succeeds;
- later-Session recall succeeds;
- cross-user and cross-domain isolation succeeds;
- audit/correlation data is available.
