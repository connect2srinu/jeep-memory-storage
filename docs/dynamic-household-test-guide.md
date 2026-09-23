# Dynamic Household Members — End-to-End UI Test Guide

Tests the full flow from the UI only: an administrator sets up the memory schema in the **admin
console**, then a customer uses the agent in the **ADK dev UI**. Design:
[dynamic-household-members-design.md](dynamic-household-members-design.md).

**What you will prove**
- A customer's household is created automatically the first time they use the agent.
- Mentioning someone ("my son Ryan") proposes a new member, and saves only after the customer confirms.
- Dislikes are ordinary preferences; allergies are health data that need confirmation and leave a
  consent record.
- Name typos match the existing person; similar names with different relationships don't merge.
- Health data about another adult is refused, with a household-level alternative offered.
- Members can be merged, moved between, renamed and forgotten.
- Customers can't see each other's households.
- Retention limits, the retention sweep, and purpose limitation work.

> **Before you start:** the local stack uses the in-memory memory store. Saved preference *values*
> are lost if the `control-plane-api` container restarts (the roster and consent records are in
> Postgres and survive). Don't restart it mid-test.

---

## 0. Start clean

From the repo root, reset the database and start the stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.devui.yml down -v
```
```bash
docker compose -f docker-compose.yml -f docker-compose.devui.yml up -d --build --wait
```

Admin console: **http://localhost:3000** (you're signed in as `platform-admin@example.com`,
Platform Administrator).

---

## Part A — Set up the memory schema (admin console)

### A1. Organization and project
1. Left nav → **Govern & manage → Organizations & Projects** → **+ Create organization**:
   ID `retail`, name `Retail` → **Create organization**.
2. Open **Retail** → **Projects** tab → **+ New project**: ID `shopping`, name `Shopping`,
   owning team `grocery-platform` → **Create project**.

### A2. Create the memory setup (wizard)
Left nav → **Create Memory Setup** → **Start setup**.

**Use Case**
- Organization `Retail`, Project `Shopping`, Domain `familygrocery`
- Use case name `Family Grocery`, description `Household grocery preferences`, owning team
  `grocery-platform` → **Continue**

**Preferences** — the domain is new, so create each with **+ Create custom preference** →
**Add preference**. Use data type `string` for all.

| Attribute ID | Display name | Description (the agent reads this) | Sensitivity | Health data |
|---|---|---|---|---|
| `familygrocery.organic_brand` | Organic Brand | Preferred organic brand | Non-sensitive | ☐ |
| `familygrocery.preferred_store` | Preferred Store | Store the household shops at | Non-sensitive | ☐ |
| `familygrocery.allow_substitutions` | Allow Substitutions | Whether substitutions are allowed | Non-sensitive | ☐ |
| `familygrocery.preferred_size` | Preferred Size | Preferred pack size | Non-sensitive | ☐ |
| `familygrocery.excluded_products` | Excluded Products | Products to exclude from all household orders, e.g. allergens | Non-sensitive | ☐ |
| `familygrocery.dislikes` | Dislikes | Foods this person does not like (a preference, not an allergy) | Non-sensitive | ☐ |
| `familygrocery.allergies` | Allergies | This person's food allergies or intolerances | Sensitive | ☑ |

✔ **Check:** the Allergies row shows a `health data` badge.

**Scope** → choose **Household + members**, then set each preference's tier:
- **Household (shared):** organic_brand, preferred_store, allow_substitutions, preferred_size,
  excluded_products
- **Member (per person):** dislikes, allergies

**Memory**
- Leave **Canonical preferences** on; turn **Dynamic and inferred memory** off.
- **Preference retention (days):** first enter `800`.

**Agents** → Register new → Agent ID `familygrocery-assistant`, display name `Family Grocery
Assistant`, owned schema access `READ_WRITE`.

**Resolution** → keep the order (household schema first).

**Review** → **Validate and generate preview**.
✔ **Check (negative test):** an error says retention of 800 days *exceeds the platform limit of 730
days for sensitive data*.

Go **Back** to **Memory**, change retention to `365`, return to **Review** → **Validate and generate
preview** (succeeds) → **Continue** → **Activate memory setup**.

✔ **Check:** activation succeeds. Under **Govern & manage → Schemas** you see
`familygrocery-household-preferences-v1` and `familygrocery-member-preferences-v1`.

---

## Part B — Use the agent as a customer (ADK dev UI)

### B0. Start the agent
In a second terminal (it uses your existing Gemini settings in `apps/memory-agent/.env`):

```bash
cd apps/memory-agent && CONTROL_PLANE_API_URL=http://localhost:8080 REFERENCE_AGENT_ID=familygrocery-assistant PREFERENCE_DOMAIN=familygrocery SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory .venv/bin/python -m memory_agent.serve
```

Open **http://localhost:8000/dev-ui/?app=memory_agent**. Set the **User ID** to `priya` — this is
the logged-in customer. (If you can't find the user field, the default `user` works too; use it in
place of `priya` below.)

Keep the admin console open in another tab: **Govern & manage → Households**, organization
**Retail**. Refresh it after each step to see what changed.

### B1. First use creates the household
| You type | Expect from the agent | Check in admin console → Households |
|---|---|---|
| "What do you know about my household?" | It knows no other members yet. | A new household `hh_…` with one member: **(account holder)**, badges *Account holder*, *guardian*, *AUTHENTICATED*, `login priya`. |

### B2. Household-wide preferences
| You type | Expect | Check |
|---|---|---|
| "We shop at Kroger, our organic brand is Simple Truth, substitutions are fine, and we buy family-size packs." | Confirms it saved them. No question asked. | — |
| "What are our household preferences?" | Lists all four. | — |

### B3. A new person is proposed, then confirmed
| You type | Expect | Check |
|---|---|---|
| "My son Ryan doesn't like peanuts." | Asks: *Should I add Ryan (your son) to your household and save their dislikes as "peanuts"?* Nothing saved yet. | **Ryan** appears with a dashed border: *Dependent*, *minor*, **awaiting confirmation**, *INFERRED*. |
| "Yes" | Confirms it saved. | Ryan: *Dependent*, *minor*, *USER_CONFIRMED* (no longer pending). |

✔ The dislike is saved as a **dislike**, not an allergy.

### B4. Health data needs confirmation and records consent
| You type | Expect | Check |
|---|---|---|
| "Ryan is allergic to peanuts." | Asks: *Please confirm: save allergies as "peanuts" for Ryan (your son)?* | Consent ledger: a **PENDING** row for Ryan / `familygrocery.allergies` with that exact question. |
| "Yes" | Confirms it saved. | The row turns **GRANTED** with a granted time. |

### B5. A new person and a health fact in one question
| You type | Expect | Check |
|---|---|---|
| "My daughter Maya is allergic to sesame." | One question: *Should I add Maya (your daughter) to your household and save their allergies as "sesame"?* | Maya pending; a PENDING consent for Maya. |
| "Yes" | Saved. | Maya active (*Dependent*, *minor*); consent **GRANTED**. |

### B6. A typo matches the existing person
| You type | Expect | Check |
|---|---|---|
| "Ryann doesn't like celery." | Saves for Ryan without asking. | Ryan shows **Also known as: ryann**. No second Ryan. |

> Each preference holds one value, so a new dislike replaces the previous one (the agent may combine
> them into one value, e.g. "peanuts, celery").

### B7. Same name, different person, then ambiguity
| You type | Expect | Check |
|---|---|---|
| "My daughter Sam doesn't like kale." | Asks to add *Sam (your daughter)*. | — |
| "Yes" | Saved. | Sam (daughter) added. |
| "My son Sam doesn't like beets." | Asks to add *Sam (your son)* — a son is not the same person as a daughter. | — |
| "Yes" | Saved. | Two Sams, one daughter and one son. |
| "Sam doesn't like olives." | Asks **which Sam** you mean (daughter or son). Nothing saved. | — |
| "My son." | Saves for Sam the son. | — |

### B8. Another adult's health data is refused
| You type | Expect | Check |
|---|---|---|
| "My wife Meera is allergic to shellfish." | Won't save it for Meera. Offers to exclude shellfish from household orders, and says Meera can save her own allergy from her own account. | No Meera added; no consent row. |
| "Yes, exclude shellfish from our orders." | Saves the household exclusion. | — |
| "Meera doesn't like cilantro." | Asks to add *Meera (your wife)*. | — |
| "Yes" | Saved. | Meera: *Other adult*, not a minor. |

### B9. The customer's own health data
| You type | Expect | Check |
|---|---|---|
| "I'm lactose intolerant." | Asks: *Please confirm: save allergies as "lactose" for you?* (wording may vary slightly with the value) | PENDING consent for the account holder. |
| "Yes" | Saved. | GRANTED. |

### B10. Read it back
| You type | Expect |
|---|---|
| "What is Ryan allergic to, and what doesn't he like?" | Allergy: peanuts. Dislikes: celery (or "peanuts, celery" if the agent combined them). |
| "Who is in my household?" | You, Ryan, Maya, both Sams, Meera. |

### B11. Merge two entries that are the same person
| You type | Expect | Check |
|---|---|---|
| "My daughter Kiki doesn't like spinach." | Asks to add *Kiki (your daughter)*. | — |
| "Yes" | Saved. | Kiki added. |
| "Kiki is just Maya's nickname — they're the same person. Keep Maya." | Asks: *Merge Kiki into Maya? …* | — |
| "Yes" | Merged. | Kiki moves to the dimmed list as **merged into Maya**; Maya shows **Also known as: kiki**. |
| "What doesn't Maya like?" | Spinach (moved from Kiki). | — |

### B12. Move a value saved for the wrong person
| You type | Expect | Check |
|---|---|---|
| "The celery dislike I gave for Ryan is actually Maya's — please move it." | Asks: *Move dislikes from Ryan (your son) to Maya (your daughter)?* | — |
| "Yes" | Moved. | "What doesn't Ryan like?" → nothing saved. "What doesn't Maya like?" → celery (the moved value replaces spinach). |

### B13. Forget health data (withdraws consent)
| You type | Expect | Check |
|---|---|---|
| "Please forget Ryan's peanut allergy." | Confirms it was deleted. | Ryan's consent row turns **WITHDRAWN** with a time. |

### B14. Correct a child who is actually an adult
| You type | Expect | Check |
|---|---|---|
| "Ryan is actually 25, he's not a child." | Confirms the update. | Ryan loses the *minor* badge. |
| "Ryan is allergic to kiwi." | Refuses (health data about another adult) and offers the household exclusion. | No new consent row. |

### B15. Customers can't see each other
Change the dev UI **User ID** to `omar` and start a new session.

| You type | Expect | Check |
|---|---|---|
| "Who is in my household? What is Ryan allergic to?" | Only Omar; knows nothing about Ryan. | A second household `hh_…` with Omar's account holder (`login omar`). Priya's household is unchanged. |

---

## Part C — Governance (admin console)

### C1. Retention sweep
First leave one proposal unanswered: as `priya` in the dev UI, type "My nephew Leo doesn't like
nuts." and **don't answer** the question. Leo appears as *awaiting confirmation*.

On **Households → Retention**:
1. **Preview** (no date). ✔ 0 values past retention; 0 proposed members to expire.
2. Set **Preview as of** to a date more than a year ahead → **Preview**.
   ✔ Values past 365 days are counted for both schemas; **Proposed members to expire: 1** (Leo).
3. **Run sweep now**. ✔ Nothing is deleted today; the customer's data is still there.

### C2. Purpose limitation (advertising is denied)
1. **Govern & manage → Agents** → use the JSON create form:
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
2. **Govern & manage → Access Requests** → JSON create form:
   ```json
   {
     "requestingAgentId": "ads-agent",
     "requestingTeam": "marketing",
     "targetSchemaId": "familygrocery-member-preferences-v1",
     "requestedPermission": "READ",
     "businessReason": "Targeted offers"
   }
   ```
3. **Govern & manage → Approvals** → approve the request.
   ✔ Approval fails: *agent 'ads-agent' declares purpose 'advertising', which schema … does not
   allow (allowed: personalization)*.

---

## Pass criteria

All ✔ checks hold. In particular:
- Nothing is saved for a new person or for health data until the customer says yes.
- Every health write has a GRANTED consent row with the exact question shown.
- No duplicate members from typos. Two different Sams are never merged.
- Another adult's allergy is never stored against them.
- Omar never sees Priya's household.

## If something looks wrong
- **The agent saves without asking.** Check the answer in the ADK trace: the tool result `status`
  must be `needs_confirmation` on the first call. The platform refuses a health write without a
  pending consent, so a real bypass would show up as a missing consent row.
- **"member … is not in the customer's household".** The dev UI User ID changed between sessions,
  so you are a different customer.
- **Preferences vanished.** The `control-plane-api` container restarted (the mock store is in memory).
