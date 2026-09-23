# Reference ADK Agent

This agent demonstrates the thin-consumer pattern. It imports no Memory Bank SDK and delegates
identity, authorization, schema selection, persistence, and conflict resolution to the Shared
Control Plane API.

Before the first model call, the agent resolves an effective snapshot and stores it in ADK Session
state. The snapshot is injected into Gemini context and includes `writablePreferences`, the complete
allowlist of canonical attributes the agent may update.

Tools:

- `get_user_preferences`: return the cached snapshot;
- `refresh_user_preferences`: refresh it explicitly;
- `update_user_preference(attribute, value)`: save an explicit canonical value;
- `remember_dynamic_preference(topic, value)`: save a non-canonical fact within an approved topic;
- `submit_preference_event(text, attribute, value)`: ingest natural language and a candidate.

Neither canonical write tool exposes `schemaId`. The agent selects an attribute from
`writablePreferences`; the Control Plane API resolves the correct same-domain writable schema. For
non-canonical facts the agent selects a topic from `approvedTopics` and calls
`remember_dynamic_preference`; the platform rejects any topic outside that list. If a request maps to
neither list, the agent declines rather than inventing an attribute or topic. See
[Dynamic Memory Topic Gating](../../docs/dynamic-memory-topic-gating.md).

## Run for a registered domain

```bash
cd apps/reference-agent
export CONTROL_PLANE_API_URL=http://localhost:8080
export CONTROL_PLANE_API_TOKEN=""
export CONTROL_PLANE_API_AUDIENCE=""
export REFERENCE_AGENT_ID=travel-assistant
export PREFERENCE_DOMAIN=travel
export ADK_APP_NAME=travel_preferences

adk web --host 0.0.0.0 --port 8000 app
```

Restart ADK Web whenever these settings or Python tool signatures change. Open
`http://localhost:8000/dev-ui/?app=reference_agent` and say:

```text
I always prefer a window seat.
```

The agent should call a write tool with `travel.seat_preference` and `window`, without a schema ID.

For an authenticated API, set `CONTROL_PLANE_API_AUDIENCE` to the service audience. Application Default
Credentials mint the Google ID token; the API maps its verified principal to the registered agent.

## Validation

```bash
PYTHONPATH=apps/reference-agent/app .venv/bin/python -m pytest -q apps/reference-agent/tests
.venv/bin/ruff check apps/reference-agent/app apps/reference-agent/tests
```

This agent has no household tools and doesn't handle the `needs_confirmation` flow, so it is suited
to Per User setups; it cannot save per-member values. For household memory, dynamic members, and the complete
multi-session walkthrough, use the [memory agent](../memory-agent/README.md) and the
[end-to-end UI guide](../../docs/dynamic-household-test-guide.md).
