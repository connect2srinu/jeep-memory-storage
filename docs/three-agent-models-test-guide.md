# Three Agent Memory Models — UI Test Guide

Set up three agents from the admin console and test them in the ADK dev UI. All values are ready to
copy and paste.

| Agent | Model | Keeps its own preferences | Reads from KSA | Writes to KSA |
|---|---|---|---|---|
| **KSA** | Private | Yes | — | — |
| **Cooklist** | Hybrid | Yes | Organic brand, dietary restriction (preferred milk requested, then denied) | Organic brand, dietary restriction |
| **Meal Planner** | Consumer only | No | Dietary restriction, allergies (preferred store requested, then denied) | No |

**What this proves**
- KSA's preferences are private. No other agent sees them until KSA's owner approves specific
  preferences.
- The owner can approve some of the requested preferences and deny the rest.
- Cooklist keeps its own preferences and reads only the approved KSA ones.
- Cooklist can update KSA's organic brand, and KSA then sees the new value. There is one value, not a
  copy.
- Meal Planner keeps nothing of its own and can't save anything.
- Health data (allergies) can be shared for reading but never written from another agent.

All three agents use **Per User** memory, keyed by the customer's ID (the GUID), as Phase 1 assumes.

---

## 0. Before you start

- **Stack:** Postgres, the API (port 8080) and the admin console (port 3000) are running. Postgres
  must be reachable on `127.0.0.1:15432` for the agents' sessions, which the `devui` or `pgadmin`
  compose overlay provides. Check with `curl -s http://localhost:8080/healthz`.
- **Organization and project:** `retail` / `shopping` must exist. On a fresh stack, create them
  first (sections 2.1 and 2.2 of the [household UI guide](dynamic-household-test-guide.md)).
- **Admin console:** http://localhost:3000, signed in as `platform-admin@example.com`.
- **Model:** the agents call Gemini. Use the same model settings you already use for the memory agent.
- **Customer:** every conversation below uses the same dev UI **User ID**: `guid-1001`.
- **Running again later:** domain and agent IDs must be new. Add a suffix everywhere, for example
  `ksa2`, `cooklist-demo2`, `mealplanner-demo2`.

> **Refresh the admin console between setups** (F5 after each Activate). The wizard loads the
> preference catalog when it opens. KSA's preferences only appear in later setups after a refresh.

---

## 1. KSA — private preferences

Left panel → **Create Memory Setup** → **Start setup**.

### Step: Use Case
| Field | Value |
|---|---|
| Use case name | `KSA` |
| Organization | `Retail` |
| Project | `Shopping` |
| Domain | Pick **+ New domain…** in the dropdown, then type `ksa` |
| Description | `Kroger shopping assistant preferences` |
| Owning team | `ksa-team` |
| Environment | Development |

Click **Continue**.

### Step: Preferences
Nothing is preselected for a new domain. For each row, click **+ Create custom preference**, fill in
the form, then click **Add preference**. Datatype is `string` for all of them. Leave **Allowed
values** empty.

> **Watch out:** the form keeps the previous entry's Sensitivity and Health tick. Overwrite every
> field each time, and create **allergies last**.

| # | Attribute ID | Display name | Description | Sensitivity | Health data |
|---|---|---|---|---|---|
| 1 | `ksa.preferred_store` | Preferred Store | The store the customer usually shops at | Non-sensitive | ☐ |
| 2 | `ksa.organic_brand` | Organic Brand | The brand the customer prefers for organic products | Non-sensitive | ☐ |
| 3 | `ksa.preferred_milk` | Preferred Milk | The kind of milk the customer buys, e.g. oat, 2%, almond | Non-sensitive | ☐ |
| 4 | `ksa.delivery_window` | Delivery Window | When the customer wants grocery deliveries, e.g. evenings | Non-sensitive | ☐ |
| 5 | `ksa.dietary_restriction` | Dietary Restriction | The customer's diet by choice, e.g. vegetarian, vegan, keto (not an allergy) | Non-sensitive | ☐ |
| 6 | `ksa.allergies` | Allergies | The customer's food allergies or intolerances | **Sensitive** | **☑** |

✔ 6 rows are listed. Only Allergies shows `sensitive` and `health data`.

Click **Continue**.

### Step: Scope
Choose **Per User**. Click **Continue**.

### Step: Memory
| Setting | Value |
|---|---|
| Canonical preferences | On |
| Preference retention (days) | `365` |
| Dynamic and inferred memory | **Off** (it's on by default — turn it off) |

Click **Continue**.

### Step: Agents
| Setting | Value |
|---|---|
| Mode | Register new |
| Agent ID | `ksa-assistant` (pre-filled — keep it) |
| Display name | `KSA Assistant` |
| Owned schema access | `READ_WRITE` |
| Discover shared schemas | **Off** (private: it reads nothing from others) |

Click **Continue**.

### Step: Review → Activate
1. **Validate and generate preview** → ✔ valid. The schema is `ksa-preferences-v1`.
2. **Continue** → **Activate memory setup** → ✔ status **ACTIVE** (no pending approvals).
3. Refresh the page (F5).

---

## 2. Cooklist — hybrid (own preferences + selected KSA preferences)

Left panel → **Create Memory Setup** → **Start setup**.

### Step: Use Case
| Field | Value |
|---|---|
| Use case name | `Cooklist` |
| Organization | `Retail` |
| Project | `Shopping` |
| Domain | **+ New domain…**, then type `cooklist-demo` |
| Description | `Recipe and cook list assistant` |
| Owning team | `cooklist-team` |
| Environment | Development |

Click **Continue**.

### Step: Preferences
**a) Tick these three KSA preferences** in the catalog. Their cards show `ksa.… · ksa`:
- `ksa.organic_brand`
- `ksa.dietary_restriction`
- `ksa.preferred_milk`

Do **not** tick `ksa.allergies`. Cooklist will ask to write the ticked preferences, and health data
can never be written from another agent.

**b) Create Cooklist's own preferences** with **+ Create custom preference**. All are `string`,
Non-sensitive, no Health tick, and Allowed values empty:

| # | Attribute ID | Display name | Description |
|---|---|---|---|
| 1 | `cooklist-demo.max_prep_time` | Max Prep Time | The longest the customer wants to spend cooking a meal, e.g. 30 minutes |
| 2 | `cooklist-demo.favorite_cuisine` | Favorite Cuisine | The cuisine the customer likes to cook, e.g. Thai, Italian |
| 3 | `cooklist-demo.skill_level` | Cooking Skill | How experienced a cook the customer is: beginner, intermediate or advanced |

✔ There are 3 ticked KSA cards plus 3 custom rows. There's no "Consumer only" note, because Cooklist
owns preferences.

Click **Continue**.

### Step: Scope
**Per User** → **Continue**.

### Step: Memory
Retention `365`. Dynamic and inferred memory **Off**. Click **Continue**.

### Step: Agents
| Setting | Value |
|---|---|
| Mode | Register new |
| Agent ID | `cooklist-demo-assistant` |
| Display name | `Cooklist Assistant` |
| Owned schema access | `READ_WRITE` |
| Discover shared schemas | **On** (already on, because KSA preferences are ticked) |

Click **Continue**.

### Step: Sharing
1. ✔ `ksa-preferences-v1` (owner `ksa`) is ticked.
2. Under it, turn on **Also write the ticked preferences**. This requests `READ_WRITE`, so Cooklist
   can update the brand in KSA's schema.

Click **Continue**.

### Step: Resolution
Keep the order `cooklist-demo-preferences-v1`, then `ksa-preferences-v1`. Click **Continue**.

### Step: Review → Activate
1. **Validate and generate preview** → ✔ valid.
2. **Continue** → **Activate memory setup** → ✔ status **ACTIVE_WITH_PENDING_ACCESS**, with one
   pending approval.
3. Refresh the page (F5).

---

## 3. Meal Planner — consumer only

Left panel → **Create Memory Setup** → **Start setup**.

### Step: Use Case
| Field | Value |
|---|---|
| Use case name | `Meal Planner` |
| Organization | `Retail` |
| Project | `Shopping` |
| Domain | **+ New domain…**, then type `mealplanner-demo` |
| Description | `Weekly meal planner that reads the customer's food preferences` |
| Owning team | `mealplanner-team` |
| Environment | Development |

Click **Continue**.

### Step: Preferences
Tick only these KSA preferences, and create **no** custom preferences:
- `ksa.dietary_restriction`
- `ksa.allergies`
- `ksa.preferred_store`

✔ A **Consumer only** note appears: "Every selected preference is owned by another team…"

Click **Continue**. The wizard skips Scope and Memory for a consumer-only agent.

### Step: Agents
| Setting | Value |
|---|---|
| Mode | Register new |
| Agent ID | `mealplanner-demo-assistant` |
| Display name | `Meal Planner Assistant` |
| Owned schema access | *(not shown for consumer only)* |
| Discover shared schemas | **On** |

Click **Continue**.

### Step: Sharing
✔ `ksa-preferences-v1` is ticked. Leave **Also write the ticked preferences** **off**. Click
**Continue**.

### Step: Review → Activate
1. ✔ The summary shows **Preferences: 3 (consumer only)**.
2. **Validate and generate preview** → ✔ valid, with no schema of its own.
3. **Continue** → **Activate memory setup** → ✔ **ACTIVE_WITH_PENDING_ACCESS**.

---

## 4. KSA's owner approves some preferences and denies the rest

Left panel → **Govern & manage** → **Approvals**, with the Retail organization selected. There are
two incoming **PENDING** requests for `ksa-preferences-v1`. Each lists the requested preferences as
tickboxes.

| Request from | Permission | Keep ticked | Untick (deny) | Button |
|---|---|---|---|---|
| Cooklist Assistant | `READ_WRITE` | `ksa.organic_brand`, `ksa.dietary_restriction` | `ksa.preferred_milk` | **Approve 2 of 3** |
| Meal Planner Assistant | `READ` | `ksa.dietary_restriction`, `ksa.allergies` | `ksa.preferred_store` | **Approve 2 of 3** |

✔ Both rows move to APPROVED and show "Approved: …" with the two preferences.

> **Known limitation:** read and write cover the same approved preferences. Cooklist can therefore
> also write `dietary_restriction`, not just the brand.

---

## 5. Start the three agents

Open **three WSL terminals** in the repository root (`cd ~/projects/geap/geap-memory`). Each agent
runs on its own port.

**Terminal 1 — KSA (port 8000)**
```bash
cd apps/memory-agent && CONTROL_PLANE_API_URL=http://localhost:8080 REFERENCE_AGENT_ID=ksa-assistant PREFERENCE_DOMAIN=ksa ADK_APP_NAME=ksa_app PORT=8000 SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory .venv/bin/python -m memory_agent.serve
```

**Terminal 2 — Cooklist (port 8001)**
```bash
cd apps/memory-agent && CONTROL_PLANE_API_URL=http://localhost:8080 REFERENCE_AGENT_ID=cooklist-demo-assistant PREFERENCE_DOMAIN=cooklist-demo ADK_APP_NAME=cooklist_app PORT=8001 SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory .venv/bin/python -m memory_agent.serve
```

**Terminal 3 — Meal Planner (port 8002)**
```bash
cd apps/memory-agent && CONTROL_PLANE_API_URL=http://localhost:8080 REFERENCE_AGENT_ID=mealplanner-demo-assistant PREFERENCE_DOMAIN=mealplanner-demo ADK_APP_NAME=mealplanner_app PORT=8002 SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory .venv/bin/python -m memory_agent.serve
```

Dev UIs, each with **User ID** `guid-1001`:
- KSA: http://localhost:8000/dev-ui/?app=memory_agent
- Cooklist: http://localhost:8001/dev-ui/?app=memory_agent
- Meal Planner: http://localhost:8002/dev-ui/?app=memory_agent

> An agent reads the customer's preferences once, at the start of a session. After changing
> something in another agent, start a **new session** before checking.

The terminals print each memory decision as `agent_memory_decision` lines. Watch them while you chat.

---

## 6. Test conversations

### 6.1 KSA saves the customer's preferences (port 8000)
New session, User ID `guid-1001`:

| You type | Expect |
|---|---|
| `I usually shop at the Kroger on Main Street.` | Saved: `ksa.preferred_store` |
| `For organic stuff I always buy Simple Truth.` | Saved: `ksa.organic_brand` = Simple Truth |
| `I buy oat milk.` | Saved: `ksa.preferred_milk` |
| `Please deliver my groceries in the evening.` | Saved: `ksa.delivery_window` |
| `I'm vegetarian.` | Saved: `ksa.dietary_restriction` |
| `I'm allergic to peanuts.` | The agent asks you to confirm (health data). Nothing is saved yet. |
| `Yes.` | Saved: `ksa.allergies` = peanuts |
| `What do you know about me?` | All 6 preferences |

### 6.2 Cooklist: its own preferences plus the approved KSA ones (port 8001)
New session, User ID `guid-1001`:

| You type | Expect |
|---|---|
| `What do you know about my preferences?` | Only **organic brand = Simple Truth** and **vegetarian** from KSA. **Not** the store, milk (denied), delivery window, or allergies. |
| `I only have about 30 minutes to cook on weeknights.` | Saved: `cooklist-demo.max_prep_time` |
| `I love cooking Thai food.` | Saved: `cooklist-demo.favorite_cuisine` |
| `I'm a beginner cook.` | Saved: `cooklist-demo.skill_level` |
| `Actually, switch my organic brand to Private Selection.` | Saved: `ksa.organic_brand` = Private Selection, **into KSA's schema** (cross-domain write) |
| `Remember that I've switched to almond milk.` | **Not saved.** Milk was denied, so the agent says it can't save it (the terminal logs a `declined` decision). |

### 6.3 KSA sees Cooklist's brand change, and nothing else of Cooklist's (port 8000)
**New session**, User ID `guid-1001`:

| You type | Expect |
|---|---|
| `What organic brand do I usually buy?` | **Private Selection**: the value Cooklist saved |
| `How long do I like to spend cooking?` | KSA doesn't know. Cooklist's own preferences are private to Cooklist. |

### 6.4 Meal Planner reads only what was approved and saves nothing (port 8002)
New session, User ID `guid-1001`:

| You type | Expect |
|---|---|
| `Plan three dinners for me this week.` | Vegetarian meals that avoid peanuts |
| `Which store do I shop at?` | It doesn't know: preferred store was denied |
| `How long do I like to cook?` | It doesn't know: Cooklist's preferences aren't shared |
| `Remember that I want to cook five dinners a week.` | **Not saved.** It has nothing it can write. |
| `Change my organic brand to Simple Truth.` | **Not saved.** It has read-only access. |

### 6.5 Another customer sees nothing (any agent)
Change the User ID to `guid-2002`, start a new session, and ask `What do you know about me?`
✔ Nothing is known.

---

## 7. Verify with the API (optional)

Run these in WSL. Each resolve returns what that agent sees for `guid-1001`:

```bash
for a in ksa:ksa-assistant cooklist-demo:cooklist-demo-assistant mealplanner-demo:mealplanner-demo-assistant; do d=${a%%:*}; id=${a#*:}; echo "== $id"; curl -s -H "X-Agent-ID: $id" -H 'Content-Type: application/json' -d "{\"scope\":{\"userId\":\"guid-1001\",\"domain\":\"$d\"},\"sessionId\":\"verify\"}" http://localhost:8080/api/v1/runtime/preferences/resolve | python3 -c "import sys,json; d=json.load(sys.stdin); print(' reads:', {k:v['value'] for k,v in d['preferences'].items()}); print(' can save:', d['writablePreferences'])"; done
```

Expected:
- **ksa-assistant:** all 6 values, and it can save its 6 `ksa.*` preferences.
- **cooklist-demo-assistant:** its 3 values plus `organic_brand` and `dietary_restriction`. It can
  save its 3 plus `ksa.organic_brand` and `ksa.dietary_restriction`.
- **mealplanner-demo-assistant:** `dietary_restriction` and `allergies`. It can save nothing (`[]`).

**Negative checks:**
```bash
# Health data can't be written from another domain (expect 400 "health data cannot be written").
curl -s -H 'X-Admin-User: platform-admin@example.com' -H 'X-Admin-Roles: PLATFORM_ADMIN' -H 'Content-Type: application/json' -d '{"requestingAgentId":"mealplanner-demo-assistant","requestingTeam":"mealplanner-team","targetSchemaId":"ksa-preferences-v1","requestedPermission":"READ_WRITE","attributes":["ksa.allergies"],"businessReason":"negative test"}' http://localhost:8080/api/v1/admin/access-requests; echo
```
```bash
# An inferred value can't be written cross-domain (expect 403 "only values the customer stated").
curl -s -X PUT -H 'X-Agent-ID: cooklist-demo-assistant' -H 'Content-Type: application/json' -d '{"scope":{"userId":"guid-1001","domain":"cooklist-demo"},"value":"Organic Girl","source":"inference"}' http://localhost:8080/api/v1/runtime/preferences/ksa.organic_brand; echo
```

**Control plane decision log for Cooklist's brand change.** Expect `delegated: true`,
`owner_domain: ksa`, and the value. Add the compose files your stack uses:
```bash
docker compose logs control-plane-api | grep memory_decision | grep '"delegated": true' | tail -3
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| KSA preferences don't appear in the Cooklist or Meal Planner catalog | The wizard loaded the catalog before KSA existed | Refresh the page (F5) and start the setup again |
| Activate: *health data cannot be written from another domain* | `ksa.allergies` ticked with **Also write** on | Back to Preferences, untick allergies |
| Preview: *write access … needs at least one of its preferences ticked* | **Also write** is on, but no KSA preference is ticked | Tick the KSA preferences, or turn write off |
| Preview: *a consumer-only agent keeps no memory of its own* | An old request body with dynamic memory on | Start the wizard again; the consumer-only flow turns it off |
| Cooklist still shows the old brand, or KSA doesn't see the new one | The session read the customer's preferences before the change | Start a new session |
| *agent … is already registered* / domain exists | Running the guide a second time | Use new IDs with a suffix (section 0) |
| The agent saves to the wrong preference | The model chose the attribute from its description | Check the `agent_memory_decision` line; improve the preference description in a new schema version |
