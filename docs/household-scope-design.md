# Household Scope — Design & Implementation

**Status: implemented** on `feature/household-scope` (control plane, DB, and memory-agent). This is
the design of record for household memory.

**Context:** the Memory Bank scope key was `organization_id + user_id`, where `user_id` **is** the
member id (1 household = 1 member for ~95% of users). A minority (~5%, growing) are households with
**multiple member ids**. This documents how we model households.

**POC note:** with **no production data yet**, we changed schemas freely with **no migration**. That
removed the only reason to prefer a "parallel/additive" scheme, so this adopts the cleaner **nested**
model: every person is a `member_id` under a `household_id`.

**Recommended model:** a **household** groups people who share an account/roof. Everyone in it — the
account holder (has a login) and dependents like children (no login) — is a **member** with a stable
`member_id`. Scope becomes `organization_id + household_id + member_id`. Attributes shared by the whole
household live in a household-scoped schema (`organization_id + household_id`). This unifies "member"
and "dependent" into one concept and naturally handles **multi-adult** households.

---

## Layer-by-layer analysis

| Layer | Current (today) | Proposed (with household) | Memory Bank change |
|---|---|---|---|
| **Organization** | Top-level owner (e.g. "Kroger") | Unchanged | None |
| **Project** | Business unit under org | Unchanged | None |
| **Domain** | Business area under project (e.g. "grocery") | Unchanged | None |
| **Household** *(new)* | Not modeled | New top grouping: a `household_id` groups the people who share an account/roof | None on the engine — `household_id` is a scope key + a Postgres roster |
| **Schema** | Governed attribute set (e.g. `grocery-preferences-v1`) | New schemas for household-shared and member-level data (e.g. `child-health-profile-v1`, `household-fulfillment-v1`); one schema per scope level | New schema(s) registered the same way as today — no new mechanism |
| **Member** *(was "User account")* | Scope = `organization_id + user_id`; one profile per schema | Every person is a `member_id` under a household; scope = `organization_id + household_id + member_id` | Scope dict shape changes `{org, user}` → `{org, household, member}` — app-side contract change (our pluggable scope registry), **not** a Memory Bank gap. POC ⇒ no migration |
| **Household-shared data** *(new)* | N/A — all data is the single user's | Attributes shared by the whole household (address, delivery window, household diet) live in a household-scoped schema; scope = `organization_id + household_id` | A distinct 2-key scope shape `{org, household}`; merged under each member on resolve (member overrides household) |
| **Dependents** | Not modeled | Kids are **members** with a stable `member_id` and **no login**; there is no separate "dependent" dimension | Each is an ordinary member profile addressed by `member_id` — folds the earlier `dependent_id` into `member_id` |
| **Agent** | Registered separately; grants on schemas (e.g. `READ_WRITE`) | Unchanged registration; grants reach members through the schema | None — agent identity/grants live in Postgres, never touch Memory Bank |
| **Write authorization** | User writes own attributes directly | Account holder writes on behalf of a no-login member — needs a **guardian→member** check | None — the check runs in the control plane **before** Memory Bank is called |
| **Resolve / read** | Resolves one profile: the caller's own data | **Default:** resolve the member in context (+ household-shared), cached. **On demand:** resolve the whole household — one snapshot, tagged per member | `retrieve_profiles` per member scope; a whole-household view fans out (one call per member) — the control plane aggregates and caches; **lazy by default** to bound fan-out |
| **Deletion / retention** | "Forget user" wipes everything under `user_id` | Targeted: **forget member** (one `member_id`), **forget household** (all under `household_id`), **forget household-shared** | forget/purge filters match on `household_id` / `member_id`, so deleting one child doesn't wipe the whole household |

---

## Semantics (the refinements beyond the table)

### Scope shapes (all within Memory Bank's 5-key limit)
- **Member profile:** `{organization_id, household_id, member_id}` (3 keys).
- **Household-shared profile:** `{organization_id, household_id}` (2 keys).
- Each **schema** is bound to exactly one scope shape (its scope definition), so a schema is either
  household-shared or member-level — never both. The modeling discipline is **one schema per scope
  level; don't combine.**

### Resolve — bound the fan-out
Vyas's table correctly flags that resolving the whole household is **one `retrieve_profiles` per
member** (fan-out). To keep this scalable:
- **Default = the member in context** (+ the household-shared profile), resolved once per session and
  **cached** — the lazy per-member read pattern.
- **Whole-household view** (e.g. an account-holder asking "what are my kids allergic to?") is an
  **explicit** aggregate: fan out per member, aggregate, cache. Not paid on every turn.
- Merge order in the snapshot: **household-shared → member** (member overrides household defaults).

### Write authorization — guardian → member
- A member with a login (the account holder) may write **their own** member profile and, if they are a
  **guardian** of a no-login member, that member's profile and the household-shared profile.
- The **guardian→member relationship** lives in the household roster (Postgres) and is checked in the
  control plane **before** the Memory Bank write — the engine never sees an unauthorized write.

### Deletion / retention
- **forget member** — deletes one `member_id`'s profiles (a child leaves / is removed).
- **forget household** — deletes everything under `household_id` (household closes) — cascades to all
  members + household-shared.
- Retention/TTL is per scope, so a member or the household can expire independently.

### The household roster (Postgres, system of record)
The `household_members` table (`organization_id, household_id, member_id, display_name, relationship,
has_login, is_guardian, status`) answers "who is in this household," "who may write for whom"
(`is_guardian`), and supplies `member_id` values, plus the member→household lookup that derives
`household_id` from the acting member. Memory Bank stores *profiles*; Postgres stores the
*relationships*.

---

## How it is built

The memory scope is `organization_id` + an ordered set of optional keys, so a schema is bound to one
of three scope shapes via its scope contract:

| Scope level | `scope_keys` | Holds |
|---|---|---|
| Member (classic) | `[organization_id, user_id]` | the acting person's base preferences |
| Household-shared | `[organization_id, household_id]` | attributes shared by the whole household |
| Household-member | `[organization_id, household_id, member_id]` | a specific member's per-person attributes |

- **Roster:** the `household_members` table + the member→household lookup that **derives**
  `household_id` from the acting member (defaulting to the member id for the single-member 95% case).
- **Guardian auth:** the control plane checks `is_guardian` before a cross-member write.
- **Resolve:** household-shared is always read; per-member is **lazy** (only when the turn names a
  `member_id`); the snapshot carries `householdId` + `householdMembers`.
- **Deletion:** `forget` with `householdId` (+ optional `memberId`) targets or cascades; `purge`
  filters by tier/attribute/topic.
- **Agent:** one optional `member_id` argument on the tools; `household_id` is derived server-side, so
  the agent passes nothing for member/household-level attributes.

No new Memory Bank mechanism is introduced at any layer — every "Memory Bank change" in the table
above is either **None** or **a scope-key shape change**, an app-side contract rather than an engine gap.

> **History:** an earlier iteration modeled children as a separate `dependent` scope
> (`{org, user_id, dependent_id}`). That handled kids under one member but not the multi-adult
> household, so it was **folded into "members of a household"** and removed. The pluggable
> scope-plumbing it introduced was reused, not rewritten.

---

## Open decisions
- **`household_id` for the 95%:** generate a household per account (recommended, uniform), or set
  `household_id = member_id` until a second member joins. Recommend a real `household_id` from day one.
- **Whole-household resolve as default vs on-demand:** recommend **on-demand** (lazy per-member by
  default) to keep the fan-out off the hot path.
- **Guardian model granularity:** a simple `guardian_of` list vs a full role model — start simple.
- **Household-shared write conflicts** (two adults editing the same shared attribute): last-write-wins
  + versioning, or a resolution rule — decide per attribute.
