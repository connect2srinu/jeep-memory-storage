# Household Memory — End-to-End UI Guide

Step by step, from an empty system to a tested customer journey, using only the UI:

1. An **administrator** creates the organization and project, and sets up the memory schema in the
   **admin console**.
2. A **customer** talks to the agent in the **ADK dev UI**, mentioning family members, dislikes and
   allergies.
3. The administrator checks the results and governance in the admin console.

Design background: [dynamic-household-members-design.md](dynamic-household-members-design.md).

**What this proves**
- A customer's household is created automatically the first time they use the agent.
- Mentioning someone ("my son Ryan") proposes a new member, saved only after the customer confirms.
- Dislikes are ordinary preferences. Allergies are health data: they need confirmation and leave a
  consent record.
- Name typos match the existing person; similar names with different relationships stay separate.
- Another adult's health data is refused, with a household-level alternative offered.
- Members can be merged, renamed, corrected, and have values moved or forgotten.
- Customers can't see each other's households.
- Retention limits, the retention sweep and purpose limitation work.
- A preference can be added to a live setup without a reset.

---

## 0. Before you start

**Where to run commands.** Use your WSL (Ubuntu) terminal, in the repository root:

```bash
cd ~/projects/geap/geap-memory
```

You need **two terminals**: one for the stack (section 1) and one for the agent (section 3).

**Browser tabs**
- Admin console: **http://localhost:3000** (you are signed in as `platform-admin@example.com`,
  Platform Administrator).
- ADK dev UI: **http://localhost:8000/dev-ui/?app=memory_agent** (after section 3).

**Good to know**
- The local stack uses an **in-memory** store for preference values. They are lost if the
  `control-plane-api` container restarts. Organizations, schemas, agents, household rosters and
  consent records are in Postgres and survive.
- The dev UI **User ID** is the logged-in customer. Each User ID gets its own household.

---

## 1. Start the stack (or reset it)

**Reset and start clean.** The first command deletes all data, including organizations, schemas
and households:

```bash
docker compose -f docker-compose.yml -f docker-compose.devui.yml down -v
```
```bash
docker compose -f docker-compose.yml -f docker-compose.devui.yml up -d --build --wait
```

The second command builds and starts Postgres, the API (port 8080) and the admin console (port 3000),
and waits until all are healthy (1–2 minutes). Database migrations run automatically.

**Check it's up:**

```bash
curl -s http://localhost:8080/healthz
```

Expected: `{"status":"ok","application":"control-plane-api"}`. If the admin console was already
open, refresh it.

> `down` and `up` are arguments to `docker compose`. Running `down -v` on its own gives
> "command not found".

---

## 2. Administrator setup (admin console)

### 2.1 Create the organization
1. Left panel → **Govern & manage** (expand it) → **Organizations & Projects**.
2. Click **+ Create organization** and fill in:
   - Organization ID: `retail`
   - Name: `Retail`
   - Owner contact: `retail-platform@example.com` (optional)
   - Description: `Retail line of business` (optional)
3. Click **Create organization**. The Retail workspace opens.

### 2.2 Create the project
1. In the Retail workspace, open the **Projects** tab → **+ New project**.
2. Fill in:
   - Project ID: `shopping`
   - Project name: `Shopping`
   - Owning team: `grocery-platform`
   - Description: `Grocery shopping agents` (optional)
3. Click **Create project**.

✔ Retail shows 1 project.

### 2.3 Create the memory setup (wizard)
Left panel → **Create Memory Setup** → **Start setup**. The steps are shown across the top.

#### Step: Use Case
| Field | Value |
|---|---|
| Use case name | `Family Grocery` |
| Organization | `Retail` |
| Project | `Shopping` |
| Domain | `familygrocery` (type it; it's new) |
| Description | `Household grocery preferences` |
| Owning team | `grocery-platform` |
| Environment | Development |

Click **Continue**.

#### Step: Preferences
The domain is new, so there is nothing to select; you create 7 preferences. For each one, click
**+ Create custom preference**, fill in the form, then click **Add preference**.

> **Watch out:** after **Add preference**, the form keeps the previous entry's values, including
> Sensitivity and the Health data tick. Overwrite every field each time. To avoid a Health tick
> carrying over by mistake, create **allergies last** (it's last in the table).

Data type is `string` for all of them.

| # | Attribute ID | Display name | Description (the agent reads this to choose) | Sensitivity | Health data |
|---|---|---|---|---|---|
| 1 | `familygrocery.organic_brand` | Organic Brand | The household's preferred organic brand | Non-sensitive | ☐ |
| 2 | `familygrocery.preferred_store` | Preferred Store | The store the household shops at | Non-sensitive | ☐ |
| 3 | `familygrocery.allow_substitutions` | Allow Substitutions | Whether the household accepts substitutions | Non-sensitive | ☐ |
| 4 | `familygrocery.preferred_size` | Preferred Size | The household's preferred pack size | Non-sensitive | ☐ |
| 5 | `familygrocery.excluded_products` | Excluded Products | Products to exclude from all household orders, e.g. allergens | Non-sensitive | ☐ |
| 6 | `familygrocery.dislikes` | Dislikes | Foods this person does not like (a preference, not an allergy) | Non-sensitive | ☐ |
| 7 | `familygrocery.allergies` | Allergies | This person's food allergies or intolerances | **Sensitive** | **☑** |

Why these settings matter:
- Without **dislikes**, the agent has nowhere to save "doesn't like peanuts". It won't store a dislike
  as an allergy.
- Without **excluded_products**, it can't offer the household alternative for another adult's allergy.
- **Health data** on allergies turns on confirmation, the consent record and the adult-refusal rule.
  **Sensitive** is its correct classification. Don't pick **Restricted**: restricted content can't be
  stored at all.
- Write per-person descriptions about "this person", not "the user". The person discussed is often
  not the user.

✔ Check: 7 rows are listed; only Allergies shows `sensitive` and a `health data` badge.

Click **Continue**.

#### Step: Scope
1. Choose **Household + members**.
2. In the list that appears, set each preference's tier:

| Preference | Tier |
|---|---|
| organic_brand, preferred_store, allow_substitutions, preferred_size, excluded_products | **Household (shared)** |
| dislikes, allergies | **Member (per person)** |

Click **Continue**.

#### Step: Memory
| Setting | Value |
|---|---|
| Canonical preferences | **On** |
| Preference retention (days) | `800` for now (a deliberate negative test) |
| Dynamic and inferred memory | **Off** (it's on by default — turn it off) |

Click **Continue**.

#### Step: Agents
| Setting | Value |
|---|---|
| Mode | **Register new** |
| Agent ID | `familygrocery-assistant` (pre-filled — keep it exactly) |
| Display name | `Family Grocery Assistant` |
| Owned schema access | `READ_WRITE` |
| Discover shared schemas | Off |

Click **Continue**.

#### Step: Resolution
Keep the order: household schema first, then member schema. Click **Continue**.

#### Step: Review
1. Click **Validate and generate preview**.
   ✔ **Negative test:** an error says retention of 800 days *exceeds the platform limit of 730 days
   for sensitive data*.
2. Click **Back** until you reach **Memory**, change retention to `365`, then **Continue** back to
   **Review**.
3. Click **Validate and generate preview** again. ✔ "Configuration is valid".
4. Click **Continue**.

#### Step: Activate
Click **Activate memory setup**. ✔ A success mark appears.

### 2.4 Verify the setup
| Where | Expect |
|---|---|
| Govern & manage → **Schemas** | `familygrocery-household-preferences-v1` and `familygrocery-member-preferences-v1`, both ACTIVE |
| Govern & manage → **Scopes** | `familygrocery:household-scope` (organization_id, household_id) and `familygrocery:household-member-scope` (organization_id, household_id, member_id) |
| Govern & manage → **Agents** | `familygrocery-assistant`, ACTIVE, purpose `personalization` |
| Govern & manage → **Households** (organization Retail) | No households yet — they appear when a customer first uses the agent |

---

## 3. Start the agent (ADK dev UI)

In your **second terminal**, from the repository root. The agent uses your existing Gemini settings
in `apps/memory-agent/.env`:

```bash
cd apps/memory-agent && CONTROL_PLANE_API_URL=http://localhost:8080 REFERENCE_AGENT_ID=familygrocery-assistant PREFERENCE_DOMAIN=familygrocery SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory .venv/bin/python -m memory_agent.serve
```

Leave it running. Open **http://localhost:8000/dev-ui/?app=memory_agent** and set the **User ID** to
`priya`, the logged-in customer. (If you can't find the User ID field, the default `user` works; use
it wherever this guide says `priya`.)

- Start the agent **after** section 2. Before activation the agent doesn't exist, and every call fails
  with *not mapped to an active agent*.
- After any code, instruction or schema change: stop the agent (Ctrl+C), start it again, and begin a
  **new session** in the dev UI.

Keep the admin console open in another tab on **Govern & manage → Households** (organization
**Retail**). Click the household and refresh after each step to see what changed.

---

## 4. Customer journey (ADK dev UI as `priya`)

The agent relays the platform's questions. Its wording may differ slightly from the quotes below.

### 4.1 First use creates the household
| You type | Expect | Admin console → Households |
|---|---|---|
| "What do you know about my household?" | Nobody else is in it yet. | A new household `hh_…` with one member: **(account holder)**, badges *Account holder*, *guardian*, *AUTHENTICATED*, `login priya`. |

### 4.2 Household-wide preferences
| You type | Expect |
|---|---|
| "We shop at Kroger, our organic brand is Simple Truth, substitutions are fine, and we buy family-size packs." | Saved; no question asked. |
| "What are our household preferences?" | Lists all four. |

### 4.3 A new person is proposed, then confirmed
| You type | Expect | Households |
|---|---|---|
| "My son Ryan doesn't like peanuts." | Asks: *Should I add Ryan (your son) to your household and save their dislikes as "peanuts"?* Nothing is saved yet. | **Ryan** appears with a dashed border: *Dependent*, *minor*, **awaiting confirmation**, *INFERRED*. |
| "Yes" | Saved. | Ryan: *Dependent*, *minor*, *USER_CONFIRMED*. |

✔ Saved as a **dislike**, not an allergy.

### 4.4 Health data needs confirmation and records consent
| You type | Expect | Households → consent ledger |
|---|---|---|
| "Ryan is allergic to peanuts." | Asks: *Please confirm: save allergies as "peanuts" for Ryan (your son)?* | A **PENDING** row: Ryan, `familygrocery.allergies`, with that exact question. |
| "Yes" | Saved. | The row turns **GRANTED**, with a time. |

### 4.5 A new person and a health fact in one question
| You type | Expect | Households |
|---|---|---|
| "My daughter Maya is allergic to sesame." | One question: *Should I add Maya (your daughter) to your household and save their allergies as "sesame"?* | Maya pending; a PENDING consent for Maya. |
| "Yes" | Saved. | Maya: *Dependent*, *minor*; consent **GRANTED**. |

### 4.6 A typo matches the existing person
| You type | Expect | Households |
|---|---|---|
| "Ryann doesn't like celery." | Saves for Ryan without asking. | Ryan shows **Also known as: ryann**. No second Ryan. |

> Each preference holds one value, so a new dislike replaces the previous one. The agent may combine
> them, e.g. "peanuts, celery".

### 4.7 Same name, different person — then ambiguity
| You type | Expect | Households |
|---|---|---|
| "My daughter Sam doesn't like kale." | Asks to add *Sam (your daughter)*. | — |
| "Yes" | Saved. | Sam (daughter) added. |
| "My son Sam doesn't like beets." | Asks to add *Sam (your son)*: a son is not the same person as a daughter. | — |
| "Yes" | Saved. | Two Sams. |
| "Sam doesn't like olives." | Asks **which Sam**. Nothing saved. | — |
| "My son." | Saves for Sam the son. | — |

### 4.8 Another adult's health data is refused
| You type | Expect | Households |
|---|---|---|
| "My wife Meera is allergic to shellfish." | Won't save it for Meera. Offers to exclude shellfish from household orders; says Meera can save her own allergy from her own account. | No Meera; no consent row. |
| "Yes, exclude shellfish from our orders." | Saves the household exclusion. | — |
| "Meera doesn't like cilantro." | Asks to add *Meera (your wife)*. | — |
| "Yes" | Saved. | Meera: *Other adult*, not a minor. |

### 4.9 The customer's own health data
| You type | Expect | Households |
|---|---|---|
| "I'm lactose intolerant." | Asks you to confirm saving it *for you*. | PENDING consent for the account holder. |
| "Yes" | Saved. | GRANTED. |

### 4.10 Read it back
| You type | Expect |
|---|---|
| "What is Ryan allergic to, and what doesn't he like?" | Allergy: peanuts. Dislikes: celery (or "peanuts, celery"). |
| "Who is in my household?" | You, Ryan, Maya, both Sams, Meera. |

### 4.11 Merge two entries for the same person
| You type | Expect | Households |
|---|---|---|
| "My daughter Kiki doesn't like spinach." | Asks to add *Kiki (your daughter)*. | — |
| "Yes" | Saved. | Kiki added. |
| "Kiki is just Maya's nickname — they're the same person. Keep Maya." | Asks: *Merge Kiki into Maya? …* | — |
| "Yes" | Merged. | Kiki moves to the dimmed list as **merged into Maya**; Maya shows **Also known as: kiki**. |
| "What doesn't Maya like?" | Spinach (moved from Kiki). | — |

### 4.12 Move a value saved for the wrong person
| You type | Expect |
|---|---|
| "The celery dislike I gave for Ryan is actually Maya's — please move it." | Asks: *Move dislikes from Ryan (your son) to Maya (your daughter)?* |
| "Yes" | Moved. "What doesn't Ryan like?" → nothing. "What doesn't Maya like?" → celery (replaces spinach). |

### 4.13 Forget health data (withdraws consent)
| You type | Expect | Households |
|---|---|---|
| "Please forget Ryan's peanut allergy." | Deleted. | Ryan's consent row turns **WITHDRAWN**, with a time. |

### 4.14 Correct a child who is actually an adult
| You type | Expect | Households |
|---|---|---|
| "Ryan is actually 25, he's not a child." | Updated. | Ryan loses the *minor* badge. |
| "Ryan is allergic to kiwi." | Refused (another adult's health data); offers the household exclusion. | No new consent row. |

### 4.15 Customers can't see each other
Change the dev UI **User ID** to `omar` and start a **new session**.

| You type | Expect | Households |
|---|---|---|
| "Who is in my household? What is Ryan allergic to?" | Only Omar; knows nothing about Ryan. | A second household `hh_…` (`login omar`). Priya's is unchanged. |

---

## 5. Governance checks (admin console)

### 5.1 Retention sweep
First leave one proposal unanswered: as `priya`, type "My nephew Leo doesn't like nuts." and
**don't answer**. Leo appears as *awaiting confirmation*.

On **Households → Retention** (left column):
1. Click **Preview** with no date. ✔ 0 values past retention; 0 proposed members to expire.
2. Set **Preview as of** to a date **more than a year** ahead → **Preview**.
   ✔ Values past 365 days are counted for both schemas. ✔ **Proposed members to expire: 1** (Leo;
   unconfirmed members expire after 60 days).
3. Click **Run sweep now**. ✔ Nothing is deleted today; the customer's data is intact.

### 5.2 Purpose limitation (advertising is denied)
1. **Govern & manage → Agents** → in the JSON form below the table, replace the content with the
   following, then click **Create governed record**:
   ```json
   {
     "id": "ads-agent",
     "displayName": "Ads Agent",
     "organizationId": "retail",
     "projectId": "shopping",
     "domainId": "familygrocery",
     "runtimeType": "OTHER",
     "identityType": "LOCAL_POC",
     "capabilities": { "resolve_context": true },
     "purpose": "advertising"
   }
   ```
2. **Govern & manage → Access Requests** → JSON form → **Create governed record**:
   ```json
   {
     "requestingAgentId": "ads-agent",
     "requestingTeam": "marketing",
     "targetSchemaId": "familygrocery-member-preferences-v1",
     "requestedPermission": "READ",
     "businessReason": "Targeted offers"
   }
   ```
3. **Govern & manage → Approvals** → click **Approve** on that request.
   ✔ It fails: *agent 'ads-agent' declares purpose 'advertising', which schema … does not allow
   (allowed: personalization)*.

---

## 6. Add a preference to a live setup (no reset)

Use this if a preference was missed, e.g. `dislikes`. It creates a new schema version, which takes
effect as soon as it's approved.

1. **Select the organization first:** click **Organizations** at the top of the left panel and
   choose **Retail**. The **Create new version** button only appears when an organization is selected.
2. **Govern & manage → Schemas** → click the schema to change:
   - per-person preferences → `familygrocery-member-preferences-v1`
   - household-wide preferences → `familygrocery-household-preferences-v1`
3. Click **Create new version**. Existing preferences show as *Existing mapping · protected*.
4. Click **+ Create preference** and fill in, for example:
   - Attribute name: `dislikes` (the `familygrocery.` prefix is added for you)
   - Display name: `Dislikes`
   - Description: `Foods this person does not like (a preference, not an allergy)`
   - Data type: `string`; Sensitivity: `normal`
   
   Click **Create and select**.
5. Click **Review version** → New version: `2` → **Submit version for approval**. The current version
   stays active until approval.
6. **Govern & manage → Approvals** → **Approve** the schema change.
7. In the dev UI, start a **new session**. The new preference is now writable; no restart is needed.

**Adding a health preference this way.** The version form has no Health data checkbox. Create the
preference first under **Govern & manage → Preference Catalog** (JSON form → **Create governed
record**), then select it in step 4 instead of creating it there:

```json
{
  "attributeId": "familygrocery.medical_diet",
  "displayName": "Medical Diet",
  "description": "This person's medically required diet",
  "dataType": "string",
  "sensitivityClassification": "sensitive",
  "canonicalOwnerId": "familygrocery",
  "validationRules": { "health": true }
}
```

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `down: command not found` | `down`/`up` were run without `docker compose`. | Use the full commands in section 1. |
| The agent asks for a member ID, or won't save "doesn't like …" | The setup has no `dislikes` preference, so there is nowhere to save a dislike. | Add it (section 6), or reset and redo section 2 with all 7 preferences. |
| *authenticated principal is not mapped to an active agent* | The wizard isn't activated yet, the database was reset, or the Agent ID isn't `familygrocery-assistant`. | Finish section 2.3; keep the agent id exactly. |
| *schema … is already registered differently* | An API image from before a fix on this branch. | Rebuild the API: `docker compose -f docker-compose.yml -f docker-compose.devui.yml up -d --build --wait control-plane-api` |
| Wizard preview: *exceeds the platform limit of 730 days* | Retention is above the limit for sensitive/health data. | Use 730 or less (365 in this guide). |
| No **Create new version** button on a schema | No organization is selected. | Select Retail via **Organizations** at the top of the left panel. |
| A preference unexpectedly shows `health data` | The wizard form kept the previous entry's Health tick. | Before activation: go back and recreate it. After: fix it through a new schema version. |
| *member … is not in the customer's household* | The dev UI User ID changed, so you're a different customer. | Switch back to the original User ID. |
| Saved preferences vanished but members are still listed | The API container restarted; values live in the in-memory store. | Re-enter them. (Rosters and consents are in Postgres.) |
| The agent still behaves the old way | The agent process or session predates the change. | Restart the agent (Ctrl+C, rerun) and start a new session. |
| The agent saved a new person or health fact without asking | Should not happen: the platform returns `needs_confirmation` on the first call. | Check the tool result `status` in the dev UI trace. A real bypass would show as a missing consent row. |

---

## 8. Pass criteria

- Nothing is saved for a new person or for health data until the customer says yes.
- Every health write has a GRANTED consent row showing the exact question asked.
- Typos never create a duplicate member; the two Sams are never merged.
- Another adult's allergy is never stored against them.
- Omar never sees Priya's household.
- The retention preview, the sweep and the advertising denial behave as described.
- A preference added by schema version (section 6) works without a restart.
