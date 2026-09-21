# Household Scope — Design Analysis

**Context:** today the Memory Bank scope key is `organization_id + user_id`, where `user_id` **is** the
member id (1 household = 1 member for ~95% of users). A minority (~5%, growing) are households with
**multiple member ids**. This documents how we model households.

**POC note:** we have **no production data yet**, so we can change schemas freely and there is **no
migration** to worry about. That removes the only reason to prefer a "parallel/additive" scheme, so
this design adopts the cleaner **nested** model: every person is a `member_id` under a `household_id`.

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
  household-shared or member-level — never both. Same modeling discipline as member-vs-dependent:
  **one schema per scope level; don't combine.**

### Resolve — bound the fan-out
Vyas's table correctly flags that resolving the whole household is **one `retrieve_profiles` per
member** (fan-out). To keep this scalable:
- **Default = the member in context** (+ the household-shared profile), resolved once per session and
  **cached** — same lazy pattern we use for per-child reads today.
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
A `household_members` table (`organization_id, household_id, member_id, display_name, relationship,
has_login, guardian_of, status`) — the mirror of today's `member_dependents` roster. It answers "who
is in this household," "who may write for whom," and supplies `member_id` values. Memory Bank stores
*profiles*; Postgres stores the *relationships*.

---

## What changes in the build (cheap — POC, no data)

The Option C work already made scope levels **pluggable** (a scope registry, `scope_keys` per grant,
a roster table, a per-scope schema). Adopting the household model **re-points** that same machinery:

| Piece we built (Option C) | Change for household |
|---|---|
| Scope contract `…-dependent-profile` = `[org, user, dependent_id]` | Re-point to `[org, household_id, member_id]`, and add `[org, household_id]` for shared data |
| `member_dependents` roster | Becomes `household_members` (adds `has_login`, `guardian_of`) |
| Dependent-scoped schema + grant (seed) | Household-shared + member schemas + grants |
| Lazy per-dependent resolve + cache | Lazy per-member resolve + optional whole-household aggregate |
| `forget` (per-dependent / cascade) | `forget member` / `forget household` |

No new Memory Bank mechanism is introduced at any layer — every "Memory Bank change" in the table is
either **None** or **a scope-key shape change**, which is an app-side contract, not an engine gap.

---

## Is the earlier (Option C) design still valid?

**Partly — and it is superseded where it was optimized for a constraint we no longer have.**

- My earlier recommendation was **parallel/additive** (keep `{org, user_id}`, add household beside it)
  **specifically to avoid migration**. With **no data and POC flexibility**, that rationale is gone, so
  I've switched to the cleaner **nested** `{org, household_id, member_id}` model.
- My **dependent-only** model (`{org, user_id, dependent_id}`) handled kids hanging off one member but
  **not** the real 5% case — **multiple adult members** in a household. The **household-of-members**
  model handles both uniformly, so it is the better target.
- **What stays valid and is folded in:** household-shared vs member-private separation; lazy
  resolve + caching to bound fan-out; and — importantly — the **scope-plumbing investment is reused**,
  not thrown away (we re-point `dependent_id` to `{household_id, member_id}`).

**Net:** the recommendation is updated to the nested household model above; the engineering built for
Option C is the enabler that makes adopting it a configuration/seed change, not a rewrite.

---

## Open decisions
- **`household_id` for the 95%:** generate a household per account (recommended, uniform), or set
  `household_id = member_id` until a second member joins. Recommend a real `household_id` from day one.
- **Whole-household resolve as default vs on-demand:** recommend **on-demand** (lazy per-member by
  default) to keep the fan-out off the hot path.
- **Guardian model granularity:** a simple `guardian_of` list vs a full role model — start simple.
- **Household-shared write conflicts** (two adults editing the same shared attribute): last-write-wins
  + versioning, or a resolution rule — decide per attribute.
