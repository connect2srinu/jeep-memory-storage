# Memory Agent — short-term in Postgres, long-term in governed memory

A minimal ADK agent that splits memory across stores and tiers:

| Memory | Mechanism | Where it lives |
|---|---|---|
| **Short-term** (session / conversation state) | ADK `DatabaseSessionService` | Cloud SQL / **PostgreSQL** |
| **Long-term · canonical** (structured preferences) | Control Plane runtime API — `PUT /preferences/{attribute}` | **Governed schemas** (`{domain}-preferences-v1`) |
| **Long-term · dynamic** (non-canonical facts) | Control Plane runtime API — `POST /memory/dynamic` | **Approved topics only** (per-domain policy) |

Long-term memory is **not** ADK Memory Bank here. Durable facts are written to the Control Plane,
so they inherit deterministic resolution, grants/authorization, and audit — the same pipeline the
`reference-agent` uses. Dynamic memory is deliberately **not** an open store: the platform only
persists non-canonical facts that fall inside the domain's **approved topics**.

## How it works

- Every turn's session state is persisted to Postgres by `DatabaseSessionService` (ADK v2 uses an
  async SQLAlchemy engine, so a `postgresql+asyncpg://…` URL is expected — the same driver the
  control plane uses).
- `before_agent_callback` resolves the effective preference snapshot for the Session
  (`POST /api/v1/runtime/preferences/resolve`, scope `{userId, appName, domain}`) and caches it in
  session state.
- `before_model_callback` injects that snapshot into Gemini's context. The snapshot carries the
  current values (`preferences`), the canonical attributes the agent may write
  (`writablePreferences`), and the approved non-canonical categories (`approvedTopics`).
- **Reading:** the agent answers preference questions with the `get_preferences` tool (returns the
  cached snapshot), and the same snapshot is also injected into context.
- **Writing** — the agent follows one governed decision order when asked to remember something:
  1. Maps to a `writablePreferences` entry → `save_preference` (canonical;
     `PUT /preferences/{attribute}`).
  2. Else fits an `approvedTopics` entry → `remember_dynamic_preference` (dynamic;
     `POST /memory/dynamic`).
  3. Else it is declined — the agent never invents an attribute or a topic.
- The **platform**, not the agent, enforces the boundaries: writes to an unregistered attribute or
  an unapproved topic are rejected, and sensitive content (phone/SSN/card/email/secret) is blocked.
- **Per-dependent preferences (Option C):** the snapshot lists the member's `dependents`
  (`{dependentId, displayName}`) and annotates each writable attribute with a `level`
  (`member` or `dependent`) in `writablePreferenceDetails`. For a dependent-level attribute (e.g. a
  child's allergies), the agent passes the `dependentId` to `save_preference` / `get_preferences`;
  the platform routes the write/read to that dependent's scope and requires the id. The agent holds
  no scope logic — it only maps a named dependent to its id from the snapshot.
- **Household preferences:** the snapshot also carries `householdId` and `householdMembers`
  (`{memberId, displayName, relationship, hasLogin, isGuardian}`), and the attribute `level` can be
  `household` (shared) or `household_member` (per person). The platform **derives** the household
  from the acting member, so the agent passes nothing for `household` attributes; for
  `household_member` attributes it passes the `memberId` of the named person (writing another member
  requires the caller to be their guardian — enforced by the platform).

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
for the `PREFERENCE_DOMAIN`, or canonical writes are rejected. For **dynamic** memory the domain must
also have an **enabled dynamic-memory policy with approved topics** (configured in the admin console's
Create Memory Setup, stored in `dynamic_memory_policies.memory_topics`); otherwise every dynamic write
is rejected. In dev (`AUTH_ENABLED=false`) the agent id is sent as `X-Agent-ID`; in prod set
`CONTROL_PLANE_API_TOKEN` or `CONTROL_PLANE_API_AUDIENCE`.

## Choosing the ADK version (2.x vs 1.28)

The **same agent code** runs on Google ADK 2.x (default) and ADK 1.28 — the API surface the agent
uses (`Agent`, `Gemini`, `LlmRequest.append_instructions`, `DatabaseSessionService`, `ToolContext`,
`App`, `Runner`, `service_registry`, `get_fast_api_app`) is identical across the two. The governed
memory it talks to is a plain HTTP API, so nothing about the memory setup changes. The only
constraint is that ADK 1.x and 2.x **cannot coexist in one virtualenv**, so keep one venv per
version and pick the one you want to test.

```bash
cd apps/memory-agent

# ADK 2.x (default, from pyproject.toml)
python3 -m venv .venv && .venv/bin/pip install -e .

# ADK 1.28 (pinned set; --no-deps so the editable install does not re-pull ADK 2.x)
python3 -m venv .venv-v1 && .venv-v1/bin/pip install -r requirements-adk1.txt && .venv-v1/bin/pip install -e . --no-deps
```

Then run the demo or dev UI with whichever venv you want — e.g. `source .venv-v1/bin/activate` for
1.28, `source .venv/bin/activate` for 2.x. Confirm the active version any time:

```bash
python -c "import importlib.metadata as m; print('google-adk', m.version('google-adk'))"
```

Both venvs are git-ignored.

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
# same env as the demo:
CONTROL_PLANE_API_URL=http://localhost:8080 \
REFERENCE_AGENT_ID=grocery-agent \
PREFERENCE_DOMAIN=grocery \
SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory \
python -m memory_agent.serve
```

Then open `http://localhost:8000/dev-ui/?app=memory_agent`. `HOST`/`PORT` override the bind
(default `127.0.0.1:8000`).

### Test the two memory tiers from the dev UI

With the `grocery` domain's approved topics set to e.g. `shopping, fulfillment`, try:

| Prompt | Expected branch | Tool called |
|---|---|---|
| "I always shop at Kroger." | canonical | `save_preference("grocery.preferred_store", …)` |
| "Remember I do a big shop early Sunday mornings." | approved dynamic | `remember_dynamic_preference("shopping", …)` |
| "Remember to leave deliveries at the back door." | approved dynamic | `remember_dynamic_preference("fulfillment", …)` |
| "Remember I'm training for a marathon." | declined | none — not an approved memory type |
| "Remember my phone number is 555-123-4567." | blocked | tool returns 400 (sensitive) |
| "What are my preferences?" | read | none — answered from the injected snapshot |

Open the dev UI's **Events / trace** panel to confirm which tool fired (and to see the `403`/`400`
rejections for the unapproved/sensitive cases). Start a **new session** and ask about a saved topic
to confirm cross-session recall through `resolve`.

## Notes

- This app reuses the `reference-agent`'s runtime-API contract (`X-Agent-ID`/Bearer auth, scope
  `{userId, appName, domain}`) via a self-contained minimal client, because the image only copies
  `apps/memory-agent`.
- `DatabaseSessionService` requires the `google-adk[db]` extra (SQLAlchemy); the `asyncpg` driver
  is included for Postgres.
- Reads go through the `get_preferences` tool, which returns the cached effective snapshot;
  the same snapshot is also injected into context, so the model has it either way.
