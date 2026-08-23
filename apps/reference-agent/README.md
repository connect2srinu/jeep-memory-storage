# Reference ADK Agent

Grocery Preference Assistant demonstrates consumption of the Shared Memory runtime API without
importing Vertex AI Memory Bank SDKs or platform service implementations. The Memory API remains
the only boundary for durable reads and writes.

```bash
cd apps/reference-agent
python -m pip install -e '.[dev]'
export MEMORY_API_URL=http://localhost:8080
export REFERENCE_AGENT_ID=grocery-agent
adk web app
```

Open `http://127.0.0.1:8000/dev-ui/`, select the reference agent, and create a Session. Before the
first Gemini call, the agent resolves an Effective Preference Snapshot and stores it under
`shared_memory:effective_snapshot` in ADK Session state. A before-model callback adds that
authorized snapshot to Gemini context. Subsequent turns reuse it without another read.

The tools have deliberately different behavior:

- `get_user_preferences` returns the cached Session snapshot.
- `refresh_user_preferences` explicitly calls the refresh endpoint and replaces the cache.
- `update_user_preference` sends an explicit canonical update and refreshes only after success.
- `submit_preference_event` submits a natural-language event with one candidate and refreshes only
  after success.

For a local Memory API, omit both token variables; the client sends `REFERENCE_AGENT_ID` through
`X-Agent-ID`. For a temporary development token, set `MEMORY_API_TOKEN`.

For Cloud Run or another Google-authenticated Memory API, configure the service URL as the token
audience. Application Default Credentials for the agent workload mint a fresh Google ID token for
each request:

```bash
export MEMORY_API_URL=https://memory-api.example.run.app
export MEMORY_API_AUDIENCE=https://memory-api.example.run.app
export REFERENCE_AGENT_ID=grocery-agent
```

The API maps the verified service-account email to the registered agent. The `agentId` request field
is informational and cannot establish identity. The registered agent also needs the relevant scope,
schema grants, and capabilities (`resolve_context` for reads and `submit_candidates` for writes).

Run the deterministic Phase 5 gate with:

```bash
cd apps/reference-agent
.venv/bin/ruff check app tests
.venv/bin/pytest -q
```
