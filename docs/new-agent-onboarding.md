# New Agent Onboarding — Consuming Governed Memory via the Control Plane

How to give a **new agent** long-term memory. The agent never talks to Vertex Memory Bank directly:
it calls the **Control Plane runtime API**, and the platform brokers Memory Bank (storage, governance,
resolution) behind it. The [`memory-agent`](../apps/memory-agent) is the reference implementation —
copy it.

**Guiding principle:** the agent holds **zero** schema/scope knowledge. It learns what it may
read/write, the approved topics, and the household roster entirely from the **resolve snapshot** at
runtime. Onboarding a new agent is mostly *registration* in the control plane + pointing the same thin
client/callbacks/tools at your domain.

---

## Checklist

### Part A — Control-plane registration (prerequisite; not agent code)
Without this the agent gets `403 "not mapped to an active agent"`. Do it via the Admin console/API or,
for tests, `tests/db_seed.py`.

- [ ] **Domain** exists with schemas, scope definition(s), and a resolution policy.
- [ ] **Register the agent** (`RegisteredAgentRecord`): id, organization, project, `domain_id`, and
      **capabilities**:
  - `resolve_context` — required to read the snapshot.
  - `submit_candidates` — required to write (canonical or dynamic).
  - `inspect_provenance` — optional; returns provenance in the snapshot.
  - `administer_memory` — only for admin actions (purge, roster management).
- [ ] **Schema grants** (`AgentSchemaGrantRecord`): one per schema the agent uses, with
      `READ` / `WRITE` / `READ_WRITE`. Grant **WRITE only on schemas the agent owns**; `READ` for the rest.
- [ ] (If using topic memory) the domain has an **enabled dynamic-memory policy** with approved topics.
- [ ] (If using household memory) a **household-shared** schema (scope keys
      `[organization_id, household_id]`) and/or a **per-member** schema (scope keys
      `[organization_id, household_id, member_id]`) exist, plus a `household_members` roster — see
      [household-scope-design.md](household-scope-design.md).

### Part B — Agent-side code (the whole integration)
- [ ] **Runtime-API client** — copy [`client.py`](../apps/memory-agent/app/memory_agent/client.py)
      (self-contained: `resolve_preferences`, `update_preference`, `write_dynamic_memory`, roster calls).
- [ ] **Auth** — dev sends `X-Agent-ID`; prod sends a `Bearer` token (static or minted Google ID token).
      The client's `TokenProvider` handles both; no agent code needed beyond wiring the env.
- [ ] **Config / env** (see table below).
- [ ] **`before_agent_callback`** — resolve the snapshot once per session, cache it in session state.
- [ ] **`before_model_callback`** — inject the cached snapshot into the model context.
- [ ] **Tools** — `get_preferences` (read), `save_preference` (canonical write),
      `remember_dynamic_preference` (dynamic write). Add optional `member_id` for per-member memory.
- [ ] **Instruction** — the write decision order + how to use `householdMembers[]` (below).
- [ ] **Short-term sessions** — `DatabaseSessionService` on Postgres (async driver URL).

### Environment variables
| Var | Purpose | Default |
|---|---|---|
| `CONTROL_PLANE_API_URL` | Runtime API base URL | `http://localhost:8080` |
| `REFERENCE_AGENT_ID` | Registered agent id (sent as `X-Agent-ID` in dev) | `grocery-agent` |
| `PREFERENCE_DOMAIN` | Consumer domain — **must** equal the agent's `domain_id` | `grocery` |
| `CONTROL_PLANE_API_TOKEN` | Prod: static bearer token | — |
| `CONTROL_PLANE_API_AUDIENCE` | Prod: audience for minting Google ID tokens | — |
| `SESSIONS_DATABASE_URL` | Short-term sessions (Postgres, `postgresql+asyncpg://…`) | local compose Postgres |
| `GEMINI_MODEL` | Chat model | `gemini-3.5-flash` |
| `ADK_APP_NAME` | ADK app name | `dual_memory_agent` |

---

## What the snapshot gives you (so the agent needs no config)
`resolve_preferences` returns, for the `{userId, appName, domain}` scope:
- `preferences` — current effective values (each with `sensitivity`, `memorySource`).
- `writablePreferences` — canonical attributes the agent may write.
- `writablePreferenceDetails` — each writable attribute annotated with `level`
  (`member` | `household` | `household_member`).
- `approvedTopics` / `approvedTopicDetails` — non-canonical categories (with meaning + sensitivity).
- `householdId` / `householdMembers` — the household and its members `[{memberId, displayName, …}]`.

The agent reads all of this at runtime; it never hard-codes schema ids, attributes, topics, or members.

---

## Minimal agent skeleton

```python
# agent.py — the entire long-term-memory integration for a new agent.
from __future__ import annotations
import json
from typing import Any

from google.adk import Runner
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini, LlmRequest
from google.adk.sessions import DatabaseSessionService
from google.adk.tools import ToolContext

from .client import ControlPlaneApiClient, GoogleIdTokenProvider, StaticTokenProvider
from .settings import settings

SNAPSHOT_KEY = "shared_memory:effective_snapshot"

INSTRUCTION = f"""
You are an assistant for the {settings.consumer_domain} domain. The user's long-term preferences are
resolved from the Control Plane and injected as an "Effective user preference snapshot" JSON. It holds
current values ("preferences"), the attributes you may write ("writablePreferences" /
"writablePreferenceDetails" — each with a "level" of member, household, or household_member), the
approved topics ("approvedTopics"), and the household roster ("householdId" / "householdMembers":
[{{memberId, displayName}}]).

Answer preference questions from the snapshot (or call get_preferences). To remember something:
1. If it maps to a writablePreferences attribute, call save_preference. If that attribute's level is
   "household_member", map the named person to its memberId from "householdMembers" and pass it.
2. Else if it fits an approvedTopics entry, call remember_dynamic_preference with that exact topic.
3. Else decline. Never invent an attribute, topic, or memberId.
"""

def _client() -> ControlPlaneApiClient:
    if settings.control_plane_api_token:
        provider = StaticTokenProvider(settings.control_plane_api_token)
    elif settings.control_plane_api_audience:
        provider = GoogleIdTokenProvider(settings.control_plane_api_audience)
    else:
        provider = StaticTokenProvider(None)  # dev: X-Agent-ID
    return ControlPlaneApiClient(base_url=settings.control_plane_api_url, token_provider=provider)

def _identity(ctx: Any) -> tuple[str, str]:
    session = getattr(ctx, "session", None)
    user_id = getattr(ctx, "user_id", None) or getattr(session, "user_id", None)
    session_id = getattr(session, "id", None)
    if not user_id or not session_id:
        raise ValueError("ADK context missing user/session id")
    return str(user_id), str(session_id)

def _key(member_id: str | None) -> str:
    return SNAPSHOT_KEY if not member_id else f"{SNAPSHOT_KEY}:{member_id}"

async def _resolve(ctx: Any, member_id: str | None = None) -> dict[str, Any]:
    user_id, session_id = _identity(ctx)
    snap = await _client().resolve_preferences(
        user_id=user_id, session_id=session_id, app_name=settings.app_name,
        consumer_domain=settings.consumer_domain, agent_id=settings.agent_id,
        include_provenance=True, member_id=member_id,
    )
    payload = snap.model_dump(by_alias=True, mode="json")
    ctx.state[_key(member_id)] = payload
    return payload

async def initialize_snapshot(cb: CallbackContext) -> None:
    if not isinstance(cb.state.get(SNAPSHOT_KEY), dict):
        await _resolve(cb)

async def inject_snapshot(cb: CallbackContext, req: LlmRequest) -> None:
    snap = cb.state.get(SNAPSHOT_KEY)
    if isinstance(snap, dict):
        req.append_instructions(
            ["Effective user preference snapshot (JSON):\n" + json.dumps(snap, sort_keys=True)]
        )

async def get_preferences(tool_context: ToolContext, member_id: str | None = None) -> dict[str, Any]:
    """Return the current preferences snapshot (member, or a specific household member)."""
    cached = tool_context.state.get(_key(member_id))
    return cached if isinstance(cached, dict) else await _resolve(tool_context, member_id)

async def save_preference(attribute: str, value: str, tool_context: ToolContext,
                          member_id: str | None = None) -> dict[str, Any]:
    """Persist a canonical preference; the platform resolves the owning schema and scope level."""
    user_id, _ = _identity(tool_context)
    mutation = await _client().update_preference(
        user_id=user_id, app_name=settings.app_name, consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id, attribute=attribute, value=value, member_id=member_id,
    )
    return {"mutation": mutation.model_dump(by_alias=True, mode="json"),
            "snapshot": await _resolve(tool_context, member_id)}

async def remember_dynamic_preference(topic: str, value: str, tool_context: ToolContext) -> dict[str, Any]:
    """Persist a non-canonical fact within an approved topic (rejected otherwise)."""
    user_id, _ = _identity(tool_context)
    mutation = await _client().write_dynamic_memory(
        user_id=user_id, app_name=settings.app_name, consumer_domain=settings.consumer_domain,
        agent_id=settings.agent_id, topic=topic, value=value,
    )
    return {"mutation": mutation.model_dump(by_alias=True, mode="json"),
            "snapshot": await _resolve(tool_context)}

root_agent = Agent(
    name=settings.app_name,
    model=Gemini(model=settings.model),
    instruction=INSTRUCTION,
    tools=[get_preferences, save_preference, remember_dynamic_preference],
    before_agent_callback=initialize_snapshot,
    before_model_callback=inject_snapshot,
)
app = App(name=settings.app_name, root_agent=root_agent)

def build_runner() -> Runner:
    return Runner(
        agent=root_agent, app_name=settings.app_name,
        session_service=DatabaseSessionService(db_url=settings.sessions_database_url),
        memory_service=None,  # long-term memory is the Control Plane, not ADK Memory Bank
    )
```

The only per-agent code beyond this is your **prompt, domain tools, and business logic** — not memory
plumbing. Add domain tools to `tools=[…]`; leave the four memory pieces (client, two callbacks, three
tools) unchanged.

---

## What the platform enforces for you (so the agent stays simple)
- Writes to an **unregistered attribute** or an **unapproved topic** are rejected.
- **Sensitivity**: restricted content (phone/SSN/card/email/secret) → blocked; sensitive + inferred → refused.
- **Scope routing**: the scope level is inferred from the schema — a `household_member`-level
  attribute requires a `memberId`, and `household_id` is derived from the acting member. A guardian
  check gates writing another member's data.
- **Deletion / retention, RBAC, audit** — all central; the agent just calls the interface.

---

## Verify a new agent works
1. **Resolve** returns 200 with the expected `writablePreferences` / `approvedTopics` for your domain
   (a 403 means the agent isn't registered or the domain doesn't match).
2. **Write** a preference → resolve again → the value appears.
3. Run the flows in [memory-flow-test-guide.md](memory-flow-test-guide.md) against your domain.
