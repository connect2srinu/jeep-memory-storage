# Reference ADK Agent

This agent demonstrates the thin-consumer pattern. It imports no Memory Bank SDK and delegates
identity, authorization, schema selection, persistence, and conflict resolution to the Shared
Memory API.

Before the first model call, the agent resolves an effective snapshot and stores it in ADK Session
state. The snapshot is injected into Gemini context and includes `writablePreferences`, the complete
allowlist of canonical attributes the agent may update.

Tools:

- `get_user_preferences`: return the cached snapshot;
- `refresh_user_preferences`: refresh it explicitly;
- `update_user_preference(attribute, value)`: save an explicit value;
- `submit_preference_event(text, attribute, value)`: ingest natural language and a candidate.

Neither write tool exposes `schemaId`. The agent selects an attribute from `writablePreferences`;
the Memory API resolves the correct same-domain writable schema.

## Run for a registered domain

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

Restart ADK Web whenever these settings or Python tool signatures change. Open
`http://localhost:8000/dev-ui/?app=reference_agent` and say:

```text
I always prefer a window seat.
```

The agent should call a write tool with `travel.seat_preference` and `window`, without a schema ID.

For an authenticated API, set `MEMORY_API_AUDIENCE` to the service audience. Application Default
Credentials mint the Google ID token; the API maps its verified principal to the registered agent.

## Validation

```bash
PYTHONPATH=apps/reference-agent/app:. .venv/bin/python -m pytest -q apps/reference-agent/tests
.venv/bin/ruff check apps/reference-agent/app apps/reference-agent/tests
```

See `docs/adk-web-demo.md` for the complete multi-session demonstration.
