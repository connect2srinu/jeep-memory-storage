# Memory Flow Test Guide

End-to-end test steps for the governed memory flows: **canonical (member) preferences**, **dynamic
topics**, **sensitivity classification**, **deletion**, and **household memory** (household-shared +
per-member preferences, where children are members of a household). Each case gives the **example text
a user provides** and the **expected behavior**.

Two ways to test:
- **A. Automated (fastest, deterministic)** — pytest against the mock store. Proves every flow.
- **B. Manual (dev UI + curl)** — drive the agent and the runtime API against the live stack.

---

## A. Automated tests

From `apps/control-plane-api` (with the dev deps installed):

```bash
# Scope plumbing + service routing (unit)
python -m pytest tests/test_household_scope.py -q

# End-to-end HTTP: household-shared + per-member isolation, guardian auth, lazy resolve, forget
python -m pytest tests/test_runtime_api.py -k "household or member or guardian" -q

# Everything
python -m pytest -q
```

Agent-side client (from `apps/memory-agent`):

```bash
python -m pytest tests/ -q      # memberId is forwarded through the scope
```

What the end-to-end test proves (`test_household_shared_and_member_scopes`): a household-shared write
takes no `memberId`; a guardian writes a child's `member_allergies` with `memberId`; a **member**
resolve (no `memberId`) surfaces household-shared but **not** any member's per-member data (lazy);
resolving a **specific member** returns only that member's value; **forgetting one member** leaves the
other members and the shared household data intact. `test_non_guardian_cannot_write_another_member`
proves the guardian check.

---

## B. Manual setup

### B1. Start the stack
Control plane on `:8080`, Postgres, admin console. For the dev UI:

```bash
cd apps/memory-agent && source .venv/bin/activate && \
CONTROL_PLANE_API_URL=http://localhost:8080 REFERENCE_AGENT_ID=grocery-agent PREFERENCE_DOMAIN=grocery \
SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory \
python -m memory_agent.serve
# open http://localhost:8000/dev-ui/?app=memory_agent
```

### B2. Approve the grocery dynamic-memory topics
```bash
docker exec geap-memory-postgres-1 psql -U shared_memory -d shared_memory -c \
"UPDATE dynamic_memory_policies SET memory_topics='[\"shopping\",\"fulfillment\",\"wellness:sensitive\"]'::json WHERE domain_id='grocery';"
```

### B3. Provision the household schemas (one time)
The household schemas are not created by default in the dev DB. Apply them once (mirrors what
`tests/db_seed.py` seeds). Assumes the `grocery` domain and `grocery-agent` already exist:

```bash
docker exec geap-memory-postgres-1 psql -U shared_memory -d shared_memory <<'SQL'
-- Scope definitions: household-shared (org + household) and per-member (org + household + member)
INSERT INTO scope_definitions (id, scope_type, scope_keys, description, owner_domain_id, status) VALUES
 ('grocery:household-scope','DOMAIN_HOUSEHOLD_PROFILE','["organization_id","household_id"]'::json,
  'Household-shared scope for grocery.','grocery','ACTIVE'),
 ('grocery:household-member-scope','DOMAIN_HOUSEHOLD_PROFILE',
  '["organization_id","household_id","member_id"]'::json,'Per-member scope for grocery.','grocery','ACTIVE')
ON CONFLICT (id) DO NOTHING;

-- Attributes: a shared delivery note (normal) and a per-member allergy list (sensitive)
INSERT INTO preference_definitions
 (attribute_id, display_name, description, data_type, allowed_values, sensitivity_classification,
  canonical_owner_id, validation_rules, default_resolution_behavior, catalog_version) VALUES
 ('grocery.household_delivery_note','Household Delivery Note','Shared delivery instructions.','string',
  '[]'::json,'normal','grocery','{"aliases":["household_delivery_note"]}'::json,
  '{"policy":"household_delivery_note"}'::json,'1'),
 ('grocery.member_allergies','Member Allergies','Per-member allergy list.','string','[]'::json,
  'sensitive','grocery','{"aliases":["member_allergies"]}'::json,'{"policy":"member_allergies"}'::json,'1')
ON CONFLICT (attribute_id) DO NOTHING;

-- Schemas + versions + mappings
INSERT INTO profile_schemas (id, domain_id, display_name, description, owner_team, status) VALUES
 ('grocery-household-preferences-v1','grocery','Grocery Household Preferences','Shared household profile.','grocery-platform','ACTIVE'),
 ('grocery-member-preferences-v1','grocery','Grocery Member Preferences','Per-member profile.','grocery-platform','ACTIVE')
ON CONFLICT (id) DO NOTHING;

INSERT INTO profile_schema_versions
 (id, schema_id, version, status, scope_definition_id, vertex_schema_definition, generation_config) VALUES
 ('grocery-household-preferences-v1:1.0','grocery-household-preferences-v1','1.0','ACTIVE','grocery:household-scope',
  '{"type":"object","properties":{"household_delivery_note":{"type":"string"}},"additionalProperties":false}'::json,'{"enabled":false}'::json),
 ('grocery-member-preferences-v1:1.0','grocery-member-preferences-v1','1.0','ACTIVE','grocery:household-member-scope',
  '{"type":"object","properties":{"member_allergies":{"type":"string"}},"additionalProperties":false}'::json,'{"enabled":false}'::json)
ON CONFLICT (id) DO NOTHING;

INSERT INTO schema_preference_mappings (id, schema_version_id, attribute_id, profile_field) VALUES
 ('grocery-household-preferences-v1:1.0:household_delivery_note','grocery-household-preferences-v1:1.0','grocery.household_delivery_note','household_delivery_note'),
 ('grocery-member-preferences-v1:1.0:member_allergies','grocery-member-preferences-v1:1.0','grocery.member_allergies','member_allergies')
ON CONFLICT (id) DO NOTHING;

-- Grants for grocery-agent
INSERT INTO agent_schema_grants (id, agent_id, schema_id, permission, status, approved_by, approved_at) VALUES
 ('grocery-agent:grocery-household-preferences-v1','grocery-agent','grocery-household-preferences-v1','READ_WRITE','ACTIVE','manual-setup', now()),
 ('grocery-agent:grocery-member-preferences-v1','grocery-agent','grocery-member-preferences-v1','READ_WRITE','ACTIVE','manual-setup', now())
ON CONFLICT (id) DO NOTHING;
SQL
```

### B4. Enrol the household members (roster)
Members are added through the runtime API (requires `ADMINISTER_MEMORY`; `grocery-agent` has it). The
organization is taken from the agent. `u1` is the account holder (a guardian, with a login); `kid1` is
a no-login child. The platform **derives** `household_id` from the acting member, so once `u1` is a
member of `hh1`, requests for `u1` resolve household `hh1` automatically.

```bash
curl -s -X PUT http://localhost:8080/api/v1/runtime/households/hh1/members/u1 \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"displayName":"Parent","relationship":"account_holder","hasLogin":true,"isGuardian":true}'
curl -s -X PUT http://localhost:8080/api/v1/runtime/households/hh1/members/kid1 \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"displayName":"Timmy","relationship":"child"}'
```

After this, a resolve for `u1` returns `householdId:"hh1"` and
`householdMembers:[{memberId:"u1",…},{memberId:"kid1",displayName:"Timmy",…}]`.

---

## 1. Dev-UI prompt matrix (agent behavior)

Drive the chat as user `u1`. The **agent maps a named person to its `memberId`** using the
`householdMembers` roster in the snapshot — you never type an id.

| # | User says | Expected behavior |
|---|---|---|
| 1 | "I always shop at Kroger." | canonical member write → `save_preference("grocery.preferred_store", "Kroger")` (no memberId) → 200 |
| 2 | "Remember I do a big shop early Sunday mornings." | dynamic, approved topic → `remember_dynamic_preference("shopping", …)` → 200 |
| 3 | "Remember to leave deliveries at the back door." | **household-shared** → `save_preference("grocery.household_delivery_note", …)` (level `household`, no id) → 200 |
| 4 | "Remember I walk daily for my wellness routine." | dynamic, **sensitive** topic → stored (user-directed), tagged sensitive |
| 5 | "Remember I love gardening tomatoes." | **unapproved** topic → declined ("not an approved memory type") |
| 6 | "Remember my phone number is 555-123-4567." | **restricted (PII)** → tool returns 400, blocked |
| 7 | "What are my preferences?" | read → answered from the injected snapshot; no per-member data shown |
| 8 | **"My son Timmy is allergic to peanuts."** | agent finds "Timmy" → `kid1`; **household_member** write → `save_preference("grocery.member_allergies","peanut", memberId="kid1")` → 200 (u1 is a guardian) |
| 9 | **"What is Timmy allergic to?"** | `get_preferences(memberId="kid1")` → "peanut"; **only Timmy's** data |
| 10 | **"Remember an allergy."** (no member named) | agent asks **which member** — it never guesses a `memberId` |
| 11 | New session → "What do you know about my shopping habits?" | recalled from the resolved snapshot (cross-session) |

Open the dev UI **Events / trace** panel to confirm which tool fired and the scope used
(`memberId` present or absent).

---

## 2. Canonical (member) preferences — API

```bash
# write a member-level attribute (no memberId)
curl -s -X PUT http://localhost:8080/api/v1/runtime/preferences/grocery.preferred_store \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery"},"value":"Kroger"}'
```
**Expected:** `{"status":"updated","reference":"grocery-preferences-v1:grocery.preferred_store","profileVersion":1}`.

---

## 3. Dynamic topics — API

```bash
# approved topic
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/dynamic \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery"},"topic":"shopping","value":"big shop Sunday mornings","source":"user_directed"}'
```
**Expected:** 200, stored under topic `shopping`.

```bash
# unapproved topic
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/dynamic \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery"},"topic":"gardening","value":"loves tomatoes","source":"user_directed"}'
```
**Expected:** 403 — topic is not approved for the domain.

---

## 4. Sensitivity classification — API

| Case | Request (`source`, content) | Expected |
|---|---|---|
| Restricted content (PII) | `topic:"shopping"`, value `"my SSN is 123-45-6789"` | **400** — restricted content blocked |
| Sensitive + **inferred** | `topic:"wellness"`, `source:"inference"`, value `"walks daily"` | **403** — only user-directed sensitive memories may be stored |
| Sensitive + **user-directed** | `topic:"wellness"`, `source:"user_directed"`, value `"walks daily"` | **200** — stored, tagged sensitive |

```bash
# sensitive + inferred -> 403
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/dynamic \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery"},"topic":"wellness","value":"walks daily","source":"inference"}'
```

Sensitivity is `max(declared tier, content scan)`: **restricted → 400**, **sensitive + inference → 403**.

---

## 5. Household memory — API

`householdId` is **derived** from the acting member (`u1` → `hh1`), so you don't pass it for writes.

```bash
# household-shared write (level "household" — no memberId)
curl -s -X PUT http://localhost:8080/api/v1/runtime/preferences/grocery.household_delivery_note \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery"},"value":"leave at back door"}'

# per-member write for a child (guardian u1 writes memberId=kid1)
curl -s -X PUT http://localhost:8080/api/v1/runtime/preferences/grocery.member_allergies \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery","memberId":"kid1"},"value":"peanut"}'
```
**Expected:** both 200; the per-member write is stored in `{org, hh1, kid1}`.

| Case | Request | Expected |
|---|---|---|
| Per-member write **without** `memberId` where the schema needs one | resolve/write member schema with no `memberId` | **400** — "scope key 'member_id' is required" |
| Household-shared write **with** `memberId` | `PUT grocery.household_delivery_note` scope has `memberId` | **400** — "scope keys ['member_id'] are not valid for this attribute's schema" |
| Non-guardian writes another member | acting `u2` (not a guardian) writes `memberId:"kid2"` | **403** — caller is not a guardian |
| Member resolve (no `memberId`) | `POST /preferences/resolve` scope has no `memberId` | 200; household-shared present, **`member_allergies` absent** (lazy); snapshot has `householdId` + `householdMembers` + `writablePreferenceDetails` (member_allergies → `level:"household_member"`) |
| Resolve `kid1` | resolve scope `memberId:"kid1"` | `preferences.member_allergies.value == "peanut"`; household-shared also present |

```bash
# resolve a specific member
curl -s -X POST http://localhost:8080/api/v1/runtime/preferences/resolve \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery","memberId":"kid1"},"sessionId":"s","agentId":"grocery-agent"}'
```

---

## 6. Deletion — forget / purge

| Case | Request | Expected |
|---|---|---|
| Forget one member | `POST /memory/forget` scope `householdId:"hh1"`, `memberId:"kid1"` | deletes **only** that member; other members + household-shared intact |
| Forget the whole household | `POST /memory/forget` scope `householdId:"hh1"` (no `memberId`) | cascades — deletes the household-shared data **and every member** |
| Forget the member (classic) | `POST /memory/forget` scope only `userId` | deletes the `{org, user}` member profile |
| Purge by attribute | `POST /memory/purge {"attribute":"grocery.member_allergies","dryRun":true}` | lists matches, deletes nothing (drop `dryRun` to delete; needs `ADMINISTER_MEMORY`) |

```bash
# forget just one member
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/forget \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery","householdId":"hh1","memberId":"kid1"}}'
```

> Memory Bank reads are eventually consistent, so an immediate resolve after a write or delete can
> lag; the end state is correct.

---

## 7. Household roster management — API

| Case | Request | Expected |
|---|---|---|
| Add / update a member | `PUT /households/hh1/members/kid2 {"displayName":"Sara","relationship":"child"}` | 200 `{"status":"upserted"}`; appears in the next resolve's `householdMembers` |
| Deactivate a member | `DELETE /households/hh1/members/kid2` | 200 `{"status":"deactivated"}`; gone from `householdMembers` (its memories still exist — clear them with forget) |
| Manage without `ADMINISTER_MEMORY` | same as a read-only agent (e.g. `grocery-readonly-agent`) | **403** — regular agents can only read the roster |

---

## 8. Observe and clean up

Watch the audit log while testing:
```bash
docker logs -f geap-memory-control-plane-api-1 2>&1 | grep -E "memory_write|memory_deletion"
```
`memory_write` carries `{tier, op, sensitivity, source, version, correlation_id}`; `memory_deletion`
carries the forget/purge details (including `household_id` / `member_id`). Values are never logged.

Remove all of a household's memories (household-shared + every member):
```bash
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/forget \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery","householdId":"hh1"}}'
```
