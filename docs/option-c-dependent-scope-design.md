# Option C — Dependent-Scoped Memory (member + per-kid preferences)

**Status:** design proposal. **Scope:** add a first-class *dependent* (child) entity level to the
memory layer so a member can hold per-kid preferences (e.g. "child 1 has a peanut allergy") with
true partition isolation, per-kid RBAC, retention and deletion — while member-level preferences stay
unchanged.

## 1. Goal & principle

- A **member** has member-level preferences (organic, delivery type, substitution, …).
- A member has **0..N dependents** (kids); each dependent has its own preferences (allergies, snack
  preference, …), and **each kid is an independent partition**.
- **Memory Bank supports this natively** — its scope is a dict of up to **5 key-value pairs**; we use
  2 today. Adding `dependent_id` uses a 3rd slot. The work is entirely in the **control plane**, not
  Memory Bank.
- **Entity granularity drives schema design:** one schema per entity level, each bound to its own
  scope — never one combined schema (see §2).

### 1.1 Design principle — minimum agent-side configuration

**The agent stays thin. All schema, scope, and routing knowledge lives in the control plane.** An
agent should never be configured with schema ids, attribute→scope-level maps, scope-key construction,
or the list of a member's kids. The current design already embodies this (the agent gets
`writablePreferences` / `approvedTopics` from the resolve snapshot, not from config), and Option C must
**not** regress it. Concrete rules:

- **No new agent env/config for Option C.** The agent's configuration surface (`CONTROL_PLANE_API_URL`,
  `REFERENCE_AGENT_ID`, `PREFERENCE_DOMAIN`, …) does **not** grow. No per-schema or per-dependent config.
- **The platform infers scope from the attribute, not the agent.** The agent calls
  `save_preference(attribute, value, dependentId=None)`; the control plane looks up the attribute's
  owning schema, decides member vs. dependent scope, builds `scope_keys`, and routes. The agent never
  knows a schema's scope contract.
- **The snapshot is the agent's only source of truth.** Everything the agent needs at runtime comes
  from `resolve` (see §5.1) — the member prefs, the writable catalog *annotated with its level*, and
  the dependents roster `[{dependentId, displayName}]`. The agent reads the kid list from the snapshot;
  it is never hard-coded or separately configured.
- **`dependentId` is runtime context, not configuration.** The agent maps "Timmy" → `dependentId`
  using the injected roster and passes it on the call. That is inherent to the use case (you must know
  which kid), not avoidable config — and the model only ever sees display names, never bookkeeps ids.
- **Platform validates the level.** If `allergies` is dependent-scoped, a call without a `dependentId`
  is rejected with a clear error; a `dependentId` on a member-scoped attribute is rejected too. The
  agent needs no attribute→level table — the platform is authoritative.

**Justified exception (design + performance, not config):** the agent signals *which* dependent is
relevant so the platform can **resolve lazily** (member + only the referenced kid), instead of the
platform eagerly loading all kids every turn. This keeps the agent thin *and* keeps reads under the
300/min cap — it improves both axes, so it is the right place to accept a minimal runtime signal from
the agent.

## 2. Two-schema layout (do NOT combine levels)

Member-level and kid-level attributes describe **different entities at different scope granularity**.
Combining them forces one scope for both and produces the repeating-group anti-pattern
(`child1_allergy, child2_allergy, …` — breaks at the next kid, makes safety-critical recall
conditional, and mixes sensitivity tiers). Split into two schemas:

| Schema | `scope_keys` | Attributes (example) | Sensitivity |
|---|---|---|---|
| `ksa-member-preferences-v1` | `[organization_id, user_id]` | organic_pref, delivery_type, substitution, … (~7 member-level) | normal |
| `ksa-dependent-preferences-v1` | `[organization_id, user_id, dependent_id]` | allergies, snack_pref, … (kid-level) | allergies = **sensitive** |

- **Each kid = one partition** of `ksa-dependent-preferences-v1` (`dependent_id = child1 / child2 / …`).
- **"Kids have different attributes"** → keep **one** dependent schema with **optional** attributes;
  each kid instance populates only what applies (sparse instances are fine). Do **not** create a
  schema per kid.
- **Allergies are canonical** (deterministic, always-injected recall — the G3 gate), not a
  similarity-retrieved topic, and are classified **sensitive** by write screening.
- The platform already binds schemas to scope: `build_vertex_context_spec` groups
  `structured_memory_configs` by `tuple(scope.scope_keys)`
  ([`vertex_provisioning.py`](apps/control-plane-api/app/control_plane_api/services/vertex_provisioning.py)),
  so two schemas at two scope levels is a supported primitive — the gap is the runtime scope plumbing
  below.

## 3. Scope-key change (the actual code delta)

Today the runtime hard-locks every scope to `{organization_id, user_id}`. Five touch points:

1. **`MemoryScope`** — add optional `dependent_id`
   ([`domain/memory.py`](apps/control-plane-api/app/control_plane_api/domain/memory.py); today only
   `organization_id`, `user_id`). Keep `dependent_id=None` = member scope (fully backward-compatible).

2. **Scope registry** — add a contract
   ([`services/scope_registry.py`](apps/control-plane-api/app/control_plane_api/services/scope_registry.py)):
   ```python
   ScopeContract("organization-user-dependent-profile",
                 ("organization_id", "user_id", "dependent_id"))
   ```
   and have `resolve()` populate `dependent_id` when the contract carries it.

3. **Vertex scope mapping** — include the 3rd key when present
   ([`vertex_memory_store.py:504`](apps/control-plane-api/app/control_plane_api/integrations/vertex_memory_store.py)):
   ```python
   def _scope(scope):
       s = {"organization_id": scope.organization_id, "user_id": scope.user_id}
       if scope.dependent_id:
           s["dependent_id"] = scope.dependent_id
       return s
   ```
   Vertex partitions on this automatically (within its 5-KV limit).

4. **Runtime scope builders** — pick the contract from the grant's `scope_keys`
   ([`runtime_service.py` `_memory_scope` / `_owner_scope`](apps/control-plane-api/app/control_plane_api/services/runtime_service.py)).
   `_owner_scope` currently **raises** unless `scope_keys == {organization_id, user_id}` — relax it to
   also accept `{organization_id, user_id, dependent_id}` and route to the new contract. The runtime
   request must carry an optional `dependentId` in the scope payload.

5. **Grants already carry `scope_keys`** (`AgentSchemaGrantRecord.scope_keys`,
   [`persistence/models.py:182,285`](apps/control-plane-api/app/control_plane_api/persistence/models.py);
   `AccessGrant.scope_keys`,
   [`domain/control_plane.py:53`](apps/control-plane-api/app/control_plane_api/domain/control_plane.py)) —
   a dependent-scoped schema simply gets a grant whose `scope_keys` includes `dependent_id`. No schema
   change to the grant model.

**Backward compatibility:** member-scoped schemas and existing grants are untouched (`dependent_id`
absent = today's behaviour). This is additive.

## 4. Postgres roster table (system of record for the family)

Memory Bank stores per-kid *preferences*; it does **not** model the *relationship*. The roster
(member → kids) is reference data and lives in the control-plane Postgres. `dependent_id` values come
from here.

```sql
CREATE TABLE member_dependents (
    organization_id text        NOT NULL,
    member_user_id  text        NOT NULL,
    dependent_id    text        NOT NULL,          -- stable synthetic id (uuid), never PII
    display_name    text,                          -- "Timmy"
    relationship    text        NOT NULL,          -- 'child' | 'spouse' | ...
    date_of_birth   date,
    status          text        NOT NULL DEFAULT 'active',   -- active | inactive
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, member_user_id, dependent_id)
);
CREATE INDEX ix_member_dependents_active
    ON member_dependents (organization_id, member_user_id)
    WHERE status = 'active';
```

- `dependent_id` is a **synthetic, stable** id (not the child's name/DOB) — those go in columns and
  are governed like any PII.
- Deleting a dependent = mark `status='inactive'` **and** `purge` that dependent's Memory Bank scope
  (right-to-be-forgotten covers the child partition).
- A roster admin API (list/add/deactivate dependents) is a thin CRUD over this table.

## 5. Resolve / caching pattern (member vs. kid reads)

### 5.1 Thin-agent contract (snapshot + tools)

To honour §1.1, the agent interface changes only additively:

- **`resolve` snapshot gains two fields** (no agent config):
  - `writablePreferences[]` — each entry annotated with its `level` (`member` | `dependent`), so the
    agent/model knows an attribute like `allergies` needs a kid without any local map.
  - `dependents[]` — `[{dependentId, displayName}]` from the Postgres roster (§4), cheap to inject.
- **Tool signatures gain one optional argument:**
  - `save_preference(attribute, value, dependentId=None)`
  - `get_preferences(dependentId=None)` (returns the member snapshot, or a specific kid's)
  The control plane resolves attribute → schema → scope level and validates the `dependentId`
  presence/absence. The agent constructs no scope and holds no schema knowledge.
- **The model** picks `dependentId` by matching the conversation ("Timmy") against the injected
  `dependents[]` list — display names in, id out — and never persists or configures ids.

### 5.2 Read fan-out & caching

The performance risk is **read fan-out**, not schema size: member + 3 kids naively = 4 resolves per
turn, against the **300 reads/min per project/region** cap (shared across agents). Pattern:

- **Session start (once):** load the roster from Postgres (no Memory Bank read) so the agent knows the
  dependents and their `dependent_id`s.
- **Member turn:** resolve the **member** scope once; cache in session state (as today, in
  `before_agent_callback`).
- **Kid turn:** resolve **only the referenced dependent's** scope (`dependent_id = childN`); cache the
  snapshot **keyed by `dependent_id`**. Do **not** resolve all kids every turn.
- **Injection:** merge `member snapshot + active dependent snapshot` before the model call.
- **Bulk view** ("show all my kids' allergies"): resolve each active dependent once, from the roster
  list, and cache — an explicit, rate-aware fan-out, not a per-turn cost.

Net: steady-state reads stay at **1 member + 1 active kid per session**, cached across turns.

## 6. One agent, many schemas (the MSA example)

**Yes — supported today, and Option C does not change it.** Grants are per-`(agent, schema)` rows with
a per-schema permission (`AccessPermission` = READ / WRITE / READ_WRITE / NONE), and
`AuthorizationService.schema_grants` is a **map** keyed by `schema_id`
([`services/authorization.py`](apps/control-plane-api/app/control_plane_api/services/authorization.py)).
So "write 2, read 3" is just five grants:

| Schema | Grant permission | Scope level |
|---|---|---|
| `ksa-member-preferences-v1` | READ_WRITE | member |
| `ksa-dependent-preferences-v1` | READ_WRITE | dependent |
| `partner-loyalty-v1` | READ | member |
| `fulfillment-profile-v1` | READ | member |
| `health-wellness-v1` | READ | dependent |

- **Writes** are checked per schema by `require_schema_access(registration, schema_id, WRITE)` — an
  agent with only READ on a schema cannot write it.
- **Reads / resolve** aggregate every schema the agent has READ (or READ_WRITE) on within its domain;
  the resolved snapshot spans all of them.
- Option C only means **some of those grants are dependent-scoped** (their `scope_keys` include
  `dependent_id`); the multi-schema R/W mechanism is unchanged.
- Guardrail: an agent should hold WRITE only on the schemas it truly owns — read-only grants for the
  rest keep the boundary clean and auditable.

## 7. Rollout

1. Additive migration: `member_dependents` table + `dependent_id` scope contract + `MemoryScope` field.
2. Relax `_owner_scope` / scope validation to accept the 3-key contract.
3. Register `ksa-dependent-preferences-v1` (dependent scope) and grant the agent access.
4. Roster CRUD API + agent session-start roster load.
5. Resolve/caching per active dependent.
6. Verify: peanut-allergy write on `child1` → classified sensitive → resolvable only under
   `child1` scope, absent from `child2` and from the member scope.

## 8. Open items

- Confirm Memory Bank scope-key **listing** semantics for the bulk "all dependents" view (per-scope
  reads vs. prefix listing) to size fan-out precisely.
- Children's data may carry **stricter compliance** (health/minor) — confirm retention defaults and
  consent handling per dependent with the data-governance owner.
- Decide whether `dependent_id` is global-per-org or per-member namespaced (recommend per-member:
  PK already is `(org, member, dependent)`).
