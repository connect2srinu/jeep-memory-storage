# Memory Agent — short-term in Postgres, long-term in governed preference profiles

A minimal ADK agent that splits memory across two stores:

| Memory | Mechanism | Where it lives |
|---|---|---|
| **Short-term** (session / conversation state) | ADK `DatabaseSessionService` | Cloud SQL / **PostgreSQL** |
| **Long-term** (durable facts across sessions) | Control Plane runtime API (`/api/v1/runtime`) | **Governed structured preference profiles** (`{domain}-preferences-v1`) |

Long-term memory is **not** ADK Memory Bank here. Instead of free-form generated memories, durable
facts are written to the Control Plane's defined schemas, so they inherit deterministic resolution,
grants/authorization, and audit — the same pipeline the `reference-agent` uses.

## How it works

- Every turn's session state is persisted to Postgres by `DatabaseSessionService` (ADK v2 uses an
  async SQLAlchemy engine, so a `postgresql+asyncpg://…` URL is expected — the same driver the
  control plane uses).
- `before_agent_callback` resolves the effective preference snapshot for the Session
  (`POST /api/v1/runtime/preferences/resolve`, scope `{userId, appName, domain}`) and caches it in
  session state.
- `before_model_callback` injects that snapshot into Gemini's context, so the agent answers from the
  user's governed profile. Its `writablePreferences` list bounds what the agent may write.
- The `save_preference` tool writes a durable preference
  (`PUT /api/v1/runtime/preferences/{attribute}`); the platform resolves the owning writable schema
  and applies authorization + audit, then the snapshot is re-resolved.

## Configuration

| Env var | Purpose | Default |
|---|---|---|
| `SESSIONS_DATABASE_URL` | Postgres URL for short-term sessions (async driver) | `DATABASE_URL`, else the local compose Postgres |
| `CONTROL_PLANE_API_URL` | Control Plane runtime API base URL | `http://localhost:8080` |
| `CONTROL_PLANE_API_TOKEN` | Static bearer token (prod, if not minting ID tokens) | — |
| `CONTROL_PLANE_API_AUDIENCE` | Audience for minting Google ID tokens (prod) | — |
| `REFERENCE_AGENT_ID` | Registered control-plane agent id (sent as `X-Agent-ID` in dev) | `grocery-agent` |
| `PREFERENCE_DOMAIN` | Consumer domain for the scope | `grocery` |
| `GEMINI_MODEL` | Agent chat model | `gemini-3.5-flash` |
| `ADK_APP_NAME` | ADK app name | `dual_memory_agent` |

The control plane must have a **registered agent** (`REFERENCE_AGENT_ID`) with a **writable grant**
for the `PREFERENCE_DOMAIN`, or writes are rejected. In dev (`AUTH_ENABLED=false`) the agent id is
sent as `X-Agent-ID`; in prod set `CONTROL_PLANE_API_TOKEN` or `CONTROL_PLANE_API_AUDIENCE`.

## Run the demo

Needs a reachable Control Plane API and Postgres:

```bash
cd apps/memory-agent
pip install -e .
CONTROL_PLANE_API_URL=http://localhost:8080 \
REFERENCE_AGENT_ID=grocery-agent \
PREFERENCE_DOMAIN=grocery \
SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory \
python -m memory_agent.demo
```

Session 1 states a preference (the agent maps it to a writable attribute and calls
`save_preference`); session 2 (a fresh conversation) recalls it from the resolved snapshot.

## Run the dev UI

`adk web`'s built-in Postgres session support registers only the bare `postgresql` scheme, but
`DatabaseSessionService` needs an async driver URL (`postgresql+asyncpg://`) whose scheme the CLI
does not recognize — so a plain `adk web --session_service_uri postgresql+asyncpg://...` silently
falls back to SQLite. The `serve` launcher registers the async scheme and then starts the standard
ADK dev UI wired to Postgres (short-term); long-term goes through the runtime API from the agent's
callbacks:

```bash
cd apps/memory-agent
# same env as the demo (CONTROL_PLANE_API_URL, REFERENCE_AGENT_ID, PREFERENCE_DOMAIN, SESSIONS_DATABASE_URL, ...)
python -m memory_agent.serve
```

Then open `http://localhost:8000/dev-ui/?app=memory_agent`. `HOST`/`PORT` override the bind
(default `127.0.0.1:8000`).

## Notes

- This app reuses the `reference-agent`'s runtime-API contract (`X-Agent-ID`/Bearer auth, scope
  `{userId, appName, domain}`) via a self-contained minimal client, because the image only copies
  `apps/memory-agent`.
- `DatabaseSessionService` requires the `google-adk[db]` extra (SQLAlchemy); the `asyncpg` driver
  is included for Postgres.
