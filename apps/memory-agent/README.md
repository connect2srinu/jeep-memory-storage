# Memory Agent — short-term in Postgres, long-term in Memory Bank

A minimal ADK agent that splits memory across two stores, using ADK's own service abstractions:

| Memory | ADK service | Where it lives |
|---|---|---|
| **Short-term** (session / conversation state) | `DatabaseSessionService` | Cloud SQL / **PostgreSQL** |
| **Long-term** (durable facts across sessions) | `VertexAiMemoryBankService` | **Vertex AI Memory Bank** |

The `Runner` composes the two independently, which is a supported Google/ADK pattern
([ADK Memory Bank quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/adk-quickstart)).

## How it works

- Every turn's session state is persisted to Postgres by `DatabaseSessionService` (ADK v2 uses an
  async SQLAlchemy engine, so an `postgresql+asyncpg://…` URL is expected — the same driver the
  control plane uses).
- `PreloadMemoryTool` loads relevant long-term memories from Memory Bank into context at session
  start; `LoadMemoryTool` lets the model search on demand.
- The `after_agent_callback` calls `callback_context.add_session_to_memory()`, which sends a
  `GenerateMemories` request to Memory Bank so the finished session becomes long-term memory.
- Retrieval and generation are performed by Memory Bank's own (Google) model; the split does not
  change that.

## Configuration

| Env var | Purpose | Default |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | Memory Bank project | — (required) |
| `GOOGLE_CLOUD_LOCATION` | Memory Bank location | `us-central1` |
| `AGENT_PLATFORM_MEMORY_BANK_ID` | Memory Bank Agent Engine id | — (required) |
| `SESSIONS_DATABASE_URL` | Postgres URL for short-term sessions (async driver) | `DATABASE_URL`, else the local compose Postgres |
| `GEMINI_MODEL` | Agent chat model | `gemini-3.5-flash` |
| `ADK_APP_NAME` | ADK app name | `dual_memory_agent` |

## Run the demo

Needs Application Default Credentials, a Memory Bank Agent Engine, and a reachable Postgres:

```bash
cd apps/memory-agent
pip install -e .
GOOGLE_CLOUD_PROJECT=your-project \
AGENT_PLATFORM_MEMORY_BANK_ID=your-memory-bank-id \
SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:5432/shared_memory \
python -m memory_agent.demo
```

Session 1 states a preference; session 2 (a fresh conversation) recalls it from Memory Bank.

## Run the dev UI

`adk web`'s built-in Postgres session support registers only the bare `postgresql` scheme, but
`DatabaseSessionService` needs an async driver URL (`postgresql+asyncpg://`) whose scheme the CLI
does not recognize — so a plain `adk web --session_service_uri postgresql+asyncpg://...` silently
falls back to SQLite. The `serve` launcher registers the async scheme and then starts the standard
ADK dev UI wired to Postgres (short-term) + Memory Bank (long-term):

```bash
cd apps/memory-agent
# same env as the demo (GOOGLE_CLOUD_PROJECT, AGENT_PLATFORM_MEMORY_BANK_ID, SESSIONS_DATABASE_URL, ...)
python -m memory_agent.serve
```

Then open `http://localhost:8000/dev-ui/?app=memory_agent`. `HOST`/`PORT` override the bind
(default `127.0.0.1:8000`).

## Notes

- This app is independent of the preference `reference-agent`; it demonstrates the native ADK
  session/memory split rather than the Control Plane preference profiles.
- `DatabaseSessionService` requires the `google-adk[db]` extra (SQLAlchemy); the `asyncpg` driver
  is included for Postgres.
