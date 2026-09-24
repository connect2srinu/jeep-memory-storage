# New Agent Onboarding — Consuming Governed Memory via the Control Plane

How to give a new ADK agent long-term memory. The agent never talks to Vertex Memory Bank directly: it
calls the Control Plane runtime API, which brokers Memory Bank behind it. The
[`memory-agent`](../apps/memory-agent) is the reference implementation — copy it.

**Guiding principle:** the agent holds no schema, scope, or member knowledge. It learns what it may
write, the approved topics, and the household roster from the **resolve snapshot** at runtime.
Onboarding is mostly *registration* in the control plane plus reusing the same client, callbacks,
and tools.

## Part A — Control-plane registration (not agent code)

Without this the agent gets `403 "not mapped to an active agent"`. Use the Admin Console's
**Create Memory Setup** wizard ([Guided Memory Setup](guided-memory-setup.md)) or the Admin API.

- [ ] A **domain** with schema(s), scope definition(s), and (for several readable schemas) a resolution
      policy.
- [ ] A **registered agent**: ID, organization, project, `domain_id`, `purpose` (default
      `personalization`), and capabilities:
  - `resolve_context` — read the snapshot;
  - `submit_candidates` — save, forget, and move values; manage household members in conversation;
  - `inspect_provenance` — optional; provenance in the snapshot;
  - `administer_memory` — only for organization-wide purge and the administrative roster endpoints.
- [ ] **Schema grants**: `WRITE` / `READ_WRITE` only on schemas the agent's domain owns; `READ` on
      others (requested and approved per schema).
- [ ] For topic memory, an enabled **dynamic-memory policy** with approved topics.
- [ ] For family memory, the **Household + members** scope (a household-shared schema and a per-member
      schema). The household itself is created at runtime — no roster setup is needed.

## Part B — Agent-side code

Copy these from [`apps/memory-agent/app/memory_agent`](../apps/memory-agent/app/memory_agent):

- [ ] **`client.py`** — self-contained runtime API client: resolve, update/forget/move preference,
      dynamic memory, add/update/merge household members.
- [ ] **Auth** — dev sends `X-Agent-ID`; production sends a bearer token (static, or a Google ID token
      minted for `CONTROL_PLANE_API_AUDIENCE`).
- [ ] **`before_agent_callback`** (`initialize_preference_snapshot`) — resolve once per session and
      cache in session state.
- [ ] **`before_model_callback`** (`inject_preference_snapshot`) — append the cached snapshot to the
      model request. No API call per turn.
- [ ] **Tools** — `get_preferences`, `save_preference`, `remember_dynamic_preference`,
      `record_memory_decision` (logs what the model decided not to save), and for households
      `forget_preference`, `add_household_member`, `update_household_member`,
      `merge_household_members`, `move_preference`. Each write tool refreshes the cached snapshot and
      logs an `agent_memory_decision` event (values masked for health, sensitive, and rejected items).
- [ ] **Instruction** — the write decision order and the confirmation contract (below). Start from the
      memory agent's `INSTRUCTION`.
- [ ] **Short-term sessions** — `DatabaseSessionService` on PostgreSQL with an async driver URL.

Your own prompt, domain tools, and business logic sit alongside these; the memory pieces stay
unchanged.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `CONTROL_PLANE_API_URL` | Runtime API base URL | `http://localhost:8080` |
| `REFERENCE_AGENT_ID` | Registered agent ID (sent as `X-Agent-ID` in dev) | `grocery-agent` |
| `PREFERENCE_DOMAIN` | Consumer domain — must equal the agent's `domain_id` | `grocery` |
| `CONTROL_PLANE_API_TOKEN` | Production: static bearer token | — |
| `CONTROL_PLANE_API_AUDIENCE` | Production: audience for Google ID tokens | — |
| `SESSIONS_DATABASE_URL` | Short-term sessions (`postgresql+asyncpg://…`) | local Compose PostgreSQL |
| `GEMINI_MODEL` | Chat model | `gemini-3.5-flash` |
| `ADK_APP_NAME` | ADK app name | `dual_memory_agent` |

## What the snapshot gives the agent

- `preferences` — effective values, each with `sensitivity` and `memorySource`.
- `writablePreferences` / `writablePreferenceDetails` — attributes the agent may write, each with
  `level` (`member`, `household`, or `household_member`), `description`, and `health`.
- `approvedTopics` / `approvedTopicDetails` — dynamic-memory topics with meaning and sensitivity.
- `householdId`, `householdMembers` (`memberId`, `displayName`, `relationship`, `memberKind`, `minor`,
  `status`, `aliases`, `isSelf`), `actingMemberId`, `resolvedMemberId`.

## The write contract

1. If a statement maps to a `writablePreferences` attribute, call `save_preference`. For a
   `household_member` attribute about someone else, pass their `member_id` if they are in
   `householdMembers`, otherwise their name and relationship. Never invent a member ID and never ask the
   customer for one.
2. Else if it fits an approved topic, call `remember_dynamic_preference` with that exact topic.
3. Else tell the customer it can't be saved. Never invent an attribute or topic.

A write can come back without saving anything:

| `status` | Meaning | Agent action |
|---|---|---|
| `needs_confirmation` | New person or health data | Ask `confirmationPrompt` verbatim; on yes, repeat with the returned `memberId` and `confirmed=true` |
| `ambiguous` | Several members match | Ask which of `candidates` |
| `not_allowed` | E.g. health data about another adult | Relay `message` |

## What the platform enforces

- Writes to an unregistered attribute or an unapproved topic are rejected.
- Restricted content (phone, SSN, card, email, secrets, weapons, discriminatory targeting) is blocked;
  sensitive content must be user-directed.
- The scope level comes from the schema; `household_id` comes from the login. A household ID naming
  another household is refused.
- Health data needs confirmation and consent for a minor, and is refused for another adult.
- The agent's purpose must be allowed by each schema it reads.
- Deletion, retention, RBAC, and audit are central.

## Verify a new agent

1. **Resolve** returns 200 with the expected `writablePreferences` / `approvedTopics` (a 403 means the
   agent isn't registered or the domain doesn't match).
2. **Write** a preference, then resolve again: the value appears.
3. Run the customer journey in the [end-to-end UI guide](dynamic-household-test-guide.md) and the API
   checks in the [Memory Flow Test Guide](memory-flow-test-guide.md) against your domain.
