# Agent Memory Setup and Preference Flows

| Document field | Value |
|---|---|
| System | Grocery shared-preference agent |
| Platform | Google ADK, Gemini on Vertex AI, Gemini Enterprise Agent Platform |
| Persistence | Agent Platform Sessions and Memory Bank |
| Audience | Application engineers, platform engineers, security reviewers, support teams |
| Status | Implemented proof of concept |

> **Confluence attachment:** Upload `agent-memory-flows.drawio` to this page and insert it with the draw.io/diagrams.net Confluence macro. The file contains four pages: **Read and Resolve**, **Session Override**, **Long-Term Memory**, and **Failure and Isolation**.

## 1. Purpose

This design gives the grocery agent a deterministic view of user preferences while keeping temporary instructions, explicit profile data, learned long-term preferences, and defaults separate. Gemini does not decide which source wins. A pure Python resolver applies the precedence policy and sends only the effective context to the model.

The central precedence rule is:

```text
SESSION_OVERRIDE > EXPLICIT_PROFILE > LONG_TERM_MEMORY > DEFAULT
```

Resolution is performed independently for every preference key. For example, a session-level substitution choice can coexist with a profile-level vegetarian diet and a Memory Bank preference for organic products.

## 2. Design goals

- Produce the same result for the same normalized inputs.
- Keep session-only data out of long-term memory unless the user expresses durable intent.
- Preserve explicit profile authority over inferred or learned memory.
- Isolate memories by user, application, and business domain.
- Continue with safe fallbacks when an external preference source is unavailable.
- Expose source and provenance in preference diagnostics without exposing credentials or internal prompts.

## 3. Component model

| Component | Responsibility | Implementation |
|---|---|---|
| ADK agent | Orchestrates tool calls and generates the final answer | `app/agent.py` |
| Preference tools | Retrieve effective preferences and route new statements by scope | `app/tools/preference_tools.py` |
| Context service | Loads profile, memory, and session sources concurrently | `app/services/preference_context_service.py` |
| Session adapter | Normalizes structured ADK session state | `app/preferences/session_preferences.py` |
| Profile service | Supplies user-confirmed preferences | `app/preferences/profile_service.py` |
| Memory Bank service | Retrieves and creates durable facts using `agentplatform.Client` | `app/preferences/memory_service.py` |
| Memory adapter | Converts Memory Bank facts to normalized preferences | `app/preferences/memory_adapter.py` |
| Candidate extractor | Classifies explicit temporary or durable language | `app/preferences/candidate_extractor.py` |
| Resolver | Applies domain, expiration, confidence, recency, and precedence rules | `app/preferences/resolver.py` |
| Effective context | Safe, source-labelled preference map supplied to Gemini | `app/preferences/models.py` |

## 4. Cloud and application setup

### 4.1 Required configuration

Create `.env` from `.env.example` and set the following values. Do not commit `.env`.

| Variable | Purpose |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | Google Cloud project containing Agent Runtime |
| `GOOGLE_CLOUD_LOCATION` | Co-located Agent Runtime, Sessions, and Memory Bank region |
| `GOOGLE_GENAI_USE_VERTEXAI=true` | Routes Gemini calls through Vertex AI |
| `GOOGLE_GENAI_USE_ENTERPRISE=true` | Enables Gemini Enterprise Agent Platform behavior |
| `GEMINI_MODEL` | Gemini model used by the ADK agent |
| `GOOGLE_CLOUD_AGENT_ENGINE_ID` | Agent Runtime resource ID and fallback state-service ID |
| `AGENT_PLATFORM_SESSIONS_ID` | Optional explicit managed Sessions resource ID |
| `AGENT_PLATFORM_MEMORY_BANK_ID` | Optional explicit Memory Bank resource ID |
| `AGENT_PLATFORM_STAGING_BUCKET` | Cloud Storage bucket used for deployment artifacts |
| `ADK_APP_NAME` | Application scope; defaults to `grocery_shared_preferences` |
| `PREFERENCE_DOMAIN` | Business-domain scope; defaults to `customer.grocery` |
| `MINIMUM_MEMORY_CONFIDENCE` | Minimum accepted long-term-memory confidence |

`AGENT_PLATFORM_SESSIONS_ID` and `AGENT_PLATFORM_MEMORY_BANK_ID` fall back to `GOOGLE_CLOUD_AGENT_ENGINE_ID`, allowing one Agent Runtime resource to own the agent, sessions, and memories.

### 4.2 Local installation

Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp -n .env.example .env
gcloud auth application-default login
```

### 4.3 Deploy or update Agent Runtime

```bash
source .venv/bin/activate
set -a
source .env
set +a
python scripts/deploy.py
```

The deployment script:

1. Validates or creates the staging bucket.
2. Wraps the ADK application in `AdkApp`.
3. Deploys with agent identity.
4. Uploads the local `app` package with the serialized agent.
5. Updates the configured runtime or creates a new one.
6. Prints the resource IDs that must be recorded in `.env`.

### 4.4 Run ADK Web with managed state

```bash
source .venv/bin/activate
set -a
source .env
set +a
adk web \
  --session_service_uri="agentengine://${AGENT_PLATFORM_SESSIONS_ID:-$GOOGLE_CLOUD_AGENT_ENGINE_ID}" \
  --memory_service_uri="agentengine://${AGENT_PLATFORM_MEMORY_BANK_ID:-$GOOGLE_CLOUD_AGENT_ENGINE_ID}"
```

Use `?userId=user-123` in the ADK Web URL when validating the supplied demo profile.

## 5. Preference data model

Every normalized preference contains:

| Field | Meaning |
|---|---|
| `key`, `value` | Typed preference name and value |
| `source` | Session override, explicit profile, long-term memory, or default |
| `scope` | Current session or user |
| `domain` | Business boundary such as `customer.grocery` |
| `confidence` | Confidence score where applicable |
| `updated_at`, `expires_at` | Recency and expiration controls |
| `provenance` | Source service and record/memory identifier |

Memory Bank facts use a versioned JSON envelope:

```json
{
  "schema": "shared-preference/v1",
  "domain": "customer.grocery",
  "key": "organic",
  "value": true,
  "confidence": 0.93
}
```

The exact Memory Bank scope is:

```json
{
  "user_id": "user-123",
  "app_name": "grocery_shared_preferences",
  "domain": "customer.grocery"
}
```

All three scope fields must match. A memory written for one user, application, or domain is not eligible for another.

## 6. Flow A — Read and resolve effective preferences

1. The user asks for a recommendation or asks which preferences are active.
2. The ADK agent calls `get_effective_preferences` before answering.
3. The tool reads the native `user_id` and managed session ID from `ToolContext`. Older callers may supply the identity through state as a compatibility fallback.
4. The context service normalizes current ADK session state and concurrently retrieves:
   - explicit profile preferences;
   - exact-scope Memory Bank preferences.
5. Defaults are added locally.
6. The resolver rejects wrong-domain and expired values and filters low-confidence long-term memories.
7. For duplicate keys, newer values win within a source, followed by source precedence.
8. The tool returns an `EffectivePreferenceContext` with source labels and warnings.
9. Gemini formats the answer but does not re-resolve or override source precedence.

Example outcome:

| Key | Effective value | Source | Why |
|---|---|---|---|
| `diet` | `vegetarian` | Explicit Profile | Profile supplies a confirmed value |
| `organic` | `true` | Long-term Memory | No profile or session value overrides it |
| `allow_substitutions` | `true` | Current Session | Temporary session value has highest priority |

## 7. Flow B — Temporary session override

Example user statement: `For today's order, substitutions are okay.`

1. The agent calls `process_preference_statement` with the exact user message.
2. The controlled extractor recognizes the temporal phrase and creates a `SESSION` candidate.
3. The key must be in the closed allowlist.
4. `set_session_preference` writes the value under `preferences:<domain>` in `tool_context.state`.
5. Assignment creates an ADK event `state_delta`, allowing managed Sessions to persist the update.
6. No Memory Bank write occurs.
7. The agent reloads effective preferences; `SESSION_OVERRIDE` wins for that key.
8. A different or new session does not inherit the override.

Session-state shape:

```json
{
  "preferences:customer.grocery": {
    "allow_substitutions": {
      "value": true,
      "updated_at": "<ISO-8601 timestamp>"
    }
  }
}
```

## 8. Flow C — Durable Memory Bank promotion and recall

Example user statement: `I always prefer organic produce.`

1. The agent calls `process_preference_statement`.
2. The extractor recognizes durable language and creates a `USER` candidate.
3. The tool checks the key allowlist and candidate scope.
4. The memory adapter encodes the candidate in the `shared-preference/v1` envelope.
5. `agentplatform.Client` creates a Memory Bank fact with the exact user/application/domain scope.
6. The current request reloads effective preferences.
7. A new managed session for the same user retrieves the fact from Memory Bank.
8. The resolver labels it `LONG_TERM_MEMORY` unless an explicit profile or current-session value supersedes it.

Important: explicit profile data remains authoritative. If Memory Bank contains `preferred_milk=oat milk` but the profile contains `preferred_milk=whole milk`, the effective value remains `whole milk (Explicit Profile)`.

For deterministic test seeding:

```bash
python scripts/seed_memory.py --user-id user-123 --key organic --value true
python scripts/inspect_memory.py
```

## 9. Flow D — Source failure and safe degradation

Profile and Memory Bank calls cross remote boundaries. The context service times each call and handles a source failure as follows:

1. Log source name, user/session/agent identifiers, duration, and exception type.
2. Do not log raw preference values.
3. Add `<source> unavailable` to context warnings.
4. Replace only that source with an empty list.
5. Continue resolution with the remaining sources and defaults.

If Memory Bank is not configured during durable promotion, the tool returns `not_persisted` with `memory_bank_written=false`; it does not claim that the preference was saved. Resolver validation errors are not silently degraded.

## 10. Resolution rules

| Priority | Source | Intended authority | Lifetime |
|---:|---|---|---|
| 1 | Session Override | Explicit instruction for this trip/order/session | Current session |
| 2 | Explicit Profile | User-confirmed system-of-record preference | Until profile changes |
| 3 | Long-term Memory | Durable learned or explicitly promoted preference | Cross-session |
| 4 | Default | Application fallback | Configuration lifetime |

Additional eligibility rules:

- Domain must equal the requested domain.
- Expired preferences are ignored.
- Long-term memory below `MINIMUM_MEMORY_CONFIDENCE` is ignored.
- Within one source, the most recently updated record wins.
- Precedence is evaluated per key, not per source collection.

## 11. Identity, isolation, and security

- Native ADK `ToolContext` identity is authoritative; callers do not need to duplicate identity in session state.
- Memory lookup and creation use the exact tuple `(user_id, app_name, domain)`.
- Agent identity is selected during deployment.
- Treat retrieved memories as untrusted input and validate them before model use.
- Use opaque tenant-scoped user IDs in production.
- Add consent, retention, deletion/right-to-forget, audit, and promotion approval workflows before production use.
- Keep raw preference values out of standard logs and traces.
- Enforce authorization independently of prompt instructions.

## 12. Operations and validation

### Inspect managed sessions

```bash
python scripts/inspect_state.py --user-id user-123 --list
python scripts/inspect_state.py --user-id user-123 --session-id SESSION_ID
```

An existing session may legitimately contain an empty state. Identity is stored in managed-session metadata, profile preferences remain in the profile system, and durable preferences remain in Memory Bank.

### Inspect Memory Bank

```bash
python scripts/inspect_memory.py
```

### Run automated checks

```bash
python -m ruff check app scripts tests
python -m pytest -q
```

Run the opt-in cloud integration test only with valid application-default credentials and configured cloud variables:

```bash
set -a
source .env
set +a
RUN_GCP_INTEGRATION_TESTS=1 \
  python -m pytest -q tests/integration/test_agent_platform.py
```

## 13. Troubleshooting

| Symptom | Meaning | Resolution |
|---|---|---|
| `session initial state must include ...` | Older code expected identity duplicated in state | Use native `ToolContext` identity and the current tool implementation |
| `Memory Bank is not configured` | Project or resource ID is absent at runtime | Set the project and Memory Bank/Agent Runtime ID, then restart or redeploy |
| `null` from session inspection | A placeholder/nonexistent session ID was used by the older script | Run `inspect_state.py --list`, then supply a real numeric ID |
| Empty session `state` | Session exists but has no explicit overrides | This is valid; inspect profile and Memory Bank separately |
| Memory exists but is not selected | Profile/session precedence, domain mismatch, expiration, or confidence filtering | Compare normalized records and resolver rules |
| Durable statement is not saved | Extractor did not recognize it, key is unsupported, or Memory Bank is unavailable | Review tool result and candidate status; do not infer persistence from the model response |

## 14. Diagram page guide

The attached draw.io file contains:

1. **Read and Resolve** — end-to-end retrieval, normalization, deterministic resolution, and model response.
2. **Session Override** — temporal language, ADK state delta, same-session precedence, and no Memory Bank write.
3. **Long-Term Memory** — durable language, scoped Memory Bank creation, new-session recall, and profile authority.
4. **Failure and Isolation** — source degradation, warnings, safe defaults, and the user/application/domain boundary.

## 15. References

- [Agent Platform Sessions overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions)
- [Manage Sessions with ADK](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions/manage-with-adk)
- [Memory Bank ADK quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/adk-quickstart)
- [Memory Bank API quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/api-quickstart)
- [Agent Runtime ADK quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk)
