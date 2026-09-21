# Memory Flow Test Guide

End-to-end test steps for the governed memory flows: **canonical (member) preferences**, **dynamic
topics**, **sensitivity classification**, **deletion**, and the new **dependent-scoped memory
(Option C — per-child preferences)**. Each case gives the **example text a user provides** and the
**expected behavior**.

Two ways to test:
- **A. Automated (fastest, deterministic)** — pytest against the mock store. Proves every flow.
- **B. Manual (dev UI + curl)** — drive the agent and the runtime API against the live stack.

---

## A. Automated tests

From `apps/control-plane-api` (with the dev deps installed):

```bash
# Dependent-scope unit + service routing (Slice 1)
python -m pytest tests/test_dependent_scope.py -q

# End-to-end HTTP: per-child isolation, lazy resolve, roster, forget (Slices 2-3)
python -m pytest tests/test_runtime_api.py -k "dependent or roster" -q

# Everything
python -m pytest -q
```

Agent-side client (from `apps/memory-agent`):

```bash
python -m pytest tests/ -q      # dependentId is forwarded through the scope
```

What the end-to-end test proves (`test_dependent_scoped_write_and_resolve_are_isolated`): a member
write takes no `dependentId`; `allergies` for `child1` vs `child2` land in **separate partitions**; a
dependent-scoped write **without** a `dependentId` is rejected (400); a **member** resolve does not
surface any child's allergies (lazy); resolving a **specific child** returns only that child's value;
**forgetting one child** leaves the other and the member intact.

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

### B3. Provision the dependent-scoped schema (one time)
The dependent schema is not created by default in the dev DB. Apply it once (mirrors what
`tests/db_seed.py` seeds for the automated tests). Assumes the `grocery` domain and `grocery-agent`
already exist:

```bash
docker exec geap-memory-postgres-1 psql -U shared_memory -d shared_memory <<'SQL'
INSERT INTO scope_definitions (id, scope_type, scope_keys, description, owner_domain_id, status)
VALUES ('grocery:dependent-scope','DOMAIN_DEPENDENT_PROFILE',
        '["organization_id","user_id","dependent_id"]'::json,
        'Per-dependent scope for grocery.','grocery','ACTIVE')
ON CONFLICT (id) DO NOTHING;

INSERT INTO preference_definitions
  (attribute_id, display_name, description, data_type, allowed_values,
   sensitivity_classification, canonical_owner_id, validation_rules,
   default_resolution_behavior, catalog_version)
VALUES ('grocery.allergies','Allergies','Per-dependent allergy list.','string','[]'::json,
        'sensitive','grocery','{"aliases":["allergies"]}'::json,'{"policy":"allergies"}'::json,'1')
ON CONFLICT (attribute_id) DO NOTHING;

INSERT INTO profile_schemas (id, domain_id, display_name, description, owner_team, status)
VALUES ('grocery-dependent-preferences-v1','grocery','Grocery Dependent Preferences',
        'Per-dependent structured profile for grocery.','grocery-platform','ACTIVE')
ON CONFLICT (id) DO NOTHING;

INSERT INTO profile_schema_versions
  (id, schema_id, version, status, scope_definition_id, vertex_schema_definition, generation_config)
VALUES ('grocery-dependent-preferences-v1:1.0','grocery-dependent-preferences-v1','1.0','ACTIVE',
        'grocery:dependent-scope',
        '{"type":"object","properties":{"allergies":{"type":"string"}},"additionalProperties":false}'::json,
        '{"enabled":false}'::json)
ON CONFLICT (id) DO NOTHING;

INSERT INTO schema_preference_mappings (id, schema_version_id, attribute_id, profile_field)
VALUES ('grocery-dependent-preferences-v1:1.0:allergies','grocery-dependent-preferences-v1:1.0',
        'grocery.allergies','allergies')
ON CONFLICT (id) DO NOTHING;

INSERT INTO agent_schema_grants (id, agent_id, schema_id, permission, status, approved_by, approved_at)
VALUES ('grocery-agent:grocery-dependent-preferences-v1','grocery-agent',
        'grocery-dependent-preferences-v1','READ_WRITE','ACTIVE','manual-setup', now())
ON CONFLICT (id) DO NOTHING;
SQL
```

### B4. Add the member's dependents (roster)
The roster is populated through the runtime API (requires `ADMINISTER_MEMORY`; `grocery-agent` has it).
The organization is taken from the agent, so you only supply `userId`:

```bash
curl -s -X PUT http://localhost:8080/api/v1/runtime/dependents/child1 \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"userId":"u1","displayName":"Timmy"}'
curl -s -X PUT http://localhost:8080/api/v1/runtime/dependents/child2 \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"userId":"u1","displayName":"Sara"}'
```

After this, a resolve for `u1` returns `dependents: [{dependentId:"child1",displayName:"Timmy"}, …]`.

---

## 1. Dev-UI prompt matrix (agent behavior)

Drive the chat as user `u1`. The **agent maps a named child to its `dependentId`** using the roster
in the snapshot — you never type an id.

| # | User says | Expected behavior |
|---|---|---|
| 1 | "I always shop at Kroger." | canonical member write → `save_preference("grocery.preferred_store", "Kroger")` (no dependentId) → 200 |
| 2 | "Remember I do a big shop early Sunday mornings." | dynamic, approved topic → `remember_dynamic_preference("shopping", …)` → 200 |
| 3 | "Remember to leave deliveries at the back door." | dynamic, approved topic → `remember_dynamic_preference("fulfillment", …)` → 200 |
| 4 | "Remember I walk daily for my wellness routine." | dynamic, **sensitive** topic → stored (user-directed), tagged sensitive |
| 5 | "Remember I love gardening tomatoes." | **unapproved** topic → declined ("not an approved memory type") |
| 6 | "Remember my phone number is 555-123-4567." | **restricted (PII)** → tool returns 400, blocked |
| 7 | "What are my preferences?" | read → answered from the injected snapshot (may call `get_preferences`); no dependent data shown |
| 8 | **"My son Timmy is allergic to peanuts."** | agent finds "Timmy" → `child1`; **dependent** write → `save_preference("grocery.allergies","peanut", dependentId="child1")` → 200 |
| 9 | **"My daughter Sara has no allergies."** | agent finds "Sara" → `child2`; `save_preference("grocery.allergies","none", dependentId="child2")` → 200 |
| 10 | **"What is Timmy allergic to?"** | `get_preferences(dependentId="child1")` → "peanut"; **only Timmy's** data |
| 11 | **"What are Sara's allergies?"** | `get_preferences(dependentId="child2")` → "none"; not Timmy's |
| 12 | **"Remember an allergy."** (no child named) | agent asks **which dependent** — it never guesses a `dependentId` |
| 13 | New session → "What do you know about my shopping habits?" | recalled from the resolved snapshot (cross-session) |

Open the dev UI **Events / trace** panel to confirm which tool fired and the scope used
(`dependentId` present or absent).

---

## 2. Canonical (member) preferences — API

```bash
# write a member-level attribute (no dependentId)
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
| Protected class inferred | `topic:"shopping"`, `source:"inference"`, value `"user is Muslim"` | **403** — inferred protected-class content refused |

```bash
# sensitive + inferred -> 403
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/dynamic \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery"},"topic":"wellness","value":"walks daily","source":"inference"}'
```

Sensitivity is `max(declared tier, content scan)`: **restricted → 400**, **sensitive + inference → 403**.

---

## 5. Dependent-scoped memory (Option C) — API

```bash
# write child1's allergy (dependent-scoped attribute REQUIRES dependentId)
curl -s -X PUT http://localhost:8080/api/v1/runtime/preferences/grocery.allergies \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery","dependentId":"child1"},"value":"peanut"}'
# write child2's allergy
curl -s -X PUT http://localhost:8080/api/v1/runtime/preferences/grocery.allergies \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery","dependentId":"child2"},"value":"none"}'
```
**Expected:** both 200, stored in **separate** partitions.

| Case | Request | Expected |
|---|---|---|
| Dependent write **without** `dependentId` | `PUT grocery.allergies` scope has no `dependentId` | **400** — "attribute is dependent-scoped; a dependentId is required" |
| Member write **with** `dependentId` | `PUT grocery.preferred_store` scope has `dependentId` | **400** — "attribute is member-scoped; a dependentId must not be supplied" |
| Member resolve (no `dependentId`) | `POST /preferences/resolve` scope has no `dependentId` | 200; **`allergies` absent** (lazy — dependent schemas skipped); member prefs present; snapshot has `dependents[]` + `writablePreferenceDetails` (allergies → `level:"dependent"`) |
| Resolve `child1` | resolve scope `dependentId:"child1"` | `preferences.allergies.value == "peanut"`; member prefs also present; **not** child2's |
| Resolve `child2` | resolve scope `dependentId:"child2"` | `preferences.allergies.value == "none"` |

```bash
# resolve a specific child
curl -s -X POST http://localhost:8080/api/v1/runtime/preferences/resolve \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery","dependentId":"child1"},"sessionId":"s","agentId":"grocery-agent"}'
```

---

## 6. Deletion — forget / purge

| Case | Request | Expected |
|---|---|---|
| Forget one dependent | `POST /memory/forget` scope `dependentId:"child1"` | deletes **only** child1; child2 and member intact |
| Forget the member | `POST /memory/forget` scope **no** `dependentId` | cascades — deletes the member **and every dependent** |
| Purge by attribute (preview) | `POST /memory/purge {"attribute":"grocery.allergies","dryRun":true}` | lists matches, deletes nothing |
| Purge by attribute | same with `"dryRun":false` | deletes matches (requires `ADMINISTER_MEMORY`) |

```bash
# forget just child1
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/forget \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery","dependentId":"child1"}}'
```

> Memory Bank reads are eventually consistent, so an immediate resolve after a write or delete can
> lag; the end state is correct.

---

## 7. Roster management — API

| Case | Request | Expected |
|---|---|---|
| Add / update a dependent | `PUT /dependents/child3 {"userId":"u1","displayName":"Alex"}` | 200 `{"status":"upserted"}`; appears in the next resolve's `dependents[]` |
| Deactivate a dependent | `DELETE /dependents/child3 {"userId":"u1"}` | 200 `{"status":"deactivated"}`; gone from `dependents[]` (its memories still exist — clear them with forget) |
| Manage without `ADMINISTER_MEMORY` | same as a read-only agent (e.g. `grocery-readonly-agent`) | **403** — regular agents can only read the roster |

---

## 8. Observe and clean up

Watch the audit log while testing:
```bash
docker logs -f geap-memory-control-plane-api-1 2>&1 | grep -E "memory_write|memory_deletion"
```
`memory_write` carries `{tier, op, sensitivity, source, version, correlation_id}`; `memory_deletion`
carries the forget/purge details (including `dependent_id`). Values are never logged.

Remove all of the test user's memories (member + every dependent):
```bash
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/forget \
  -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"u1","appName":"a","domain":"grocery"}}'
```
