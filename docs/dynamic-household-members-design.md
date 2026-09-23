# Dynamic Household Members — Design

**Status:** Implemented on `feature/dynamic-household-members` (see "Implementation notes" at the
end). Design of record for household memory, pending Kroger Privacy/Legal review.
**Date:** 2026-09-22 (updated 2026-09-23 to absorb the earlier household-scope design)

---

## Foundation: household scopes

The first household iteration (now folded into this document) introduced the scope model everything
below relies on. It is unchanged:

- **Every person is a member of a household.** The account holder and people without a login (such as
  children) are all members with a stable `member_id`. An even earlier model with a separate
  `dependent_id` under a user was dropped because it could not represent multi-adult households.
- **Three scope shapes**, each a scope contract in the control plane, all within Memory Bank's 5-key
  scope limit:

  | Level | `scope_keys` | Holds |
  |---|---|---|
  | Member (classic) | `[organization_id, user_id]` | the customer's own base preferences (non-household setups) |
  | Household-shared | `[organization_id, household_id]` | preferences shared by the whole household |
  | Household-member | `[organization_id, household_id, member_id]` | one person's preferences |

- **One schema per scope level.** A schema version is bound to exactly one scope shape, so a schema is
  either household-shared or per-member, never both. The wizard's **Household + members** option
  generates one of each.
- **Reads stay lazy.** Household-shared data is read on every resolve; per-member data only when a turn
  names a member. A whole-household view fans out one read per member, so it is never done by default.
- **Deletion is scope-precise.** Forget with `householdId` + `memberId` removes one member; with
  `householdId` alone it cascades to the household-shared data and every member.
- **No new Memory Bank mechanism.** Households are a scope-key shape plus a PostgreSQL roster; Memory Bank
  stores profiles, PostgreSQL stores the relationships.

---

## Context

At Kroger scale (millions of customers) we cannot pre-provision household rosters through the Control
Plane UI. No authoritative Customer → Household → Member source exists today, and there is no committed
date for one.

The agent must handle conversations where the person mentioned is not the authenticated customer, for
example *"My son Ryan doesn't like peanuts."* It has to find or create that household member at runtime:
- without creating duplicates for name variants (`Anika`, `Anikaa`),
- without merging two different people who have similar names,
- and asking the user when it isn't sure.

Today that sentence fails. The agent may only use a `memberId` that is already in the snapshot's
`householdMembers`, and a customer who isn't on a roster resolves to an empty household.

## Decisions (agreed)

1. **One login = one household root.** On first use, the control plane creates the household and a root
   member linked to the login. `household_id` is a surrogate ID, not the login.
2. **Resolution happens in the control plane.** The agent sends a *reference* to a person (name plus
   relationship). The control plane matches it against that one household only.
3. **Confidence tiers.** Auto-match when confident, ask when unsure, create otherwise. Creating a new
   person always needs the user's confirmation.
4. **Dislikes are not allergies.** "Doesn't like peanuts" is a preference. "Allergic to peanuts" is
   health data and takes the stricter path: higher match threshold, confirmation, consent record.
5. **Three member kinds:**
   - `ROOT`: the logged-in customer.
   - `DEPENDENT`: a child. `relationship = child` sets `minor = true` by default, and the user can
     correct it (e.g. an adult son).
   - `PROXY_ADULT`: another adult with no login in this household. Non-health preferences only.
6. **Proxy-adult health data** is either (b) stored as a household-level product filter, or (c) recorded
   by that adult through their own login.
7. **`member_id` is a stable surrogate** and stays the Memory Bank scope key. The link fields for a
   future authoritative source (`provenance`, `authoritative_id`) exist from day one.
8. **Users can merge, split and rename members** inside their household now. Batch reconciliation with an
   authoritative source waits until that source exists.
9. **Purpose limitation is deny-by-default.** Memory data serves personalization only unless a governed
   change allows more. Minors' and health data are never used for advertising.
10. **Retention is set by schema owners** within Platform/Legal limits. Deletion requests, consent
    withdrawal, inactivity and legal holds always win.

---

## Layer-by-layer analysis

| Layer | Before this design (first household iteration) | Now (implemented) | Memory Bank change |
|---|---|---|---|
| **Organization / Project / Domain** | Owner → business unit → business area | Unchanged | None |
| **Customer (login)** | `userId` is the acting identity. It may not be on any roster. | One login = one household root. The household and root member are created on first authenticated use. | None |
| **Household** | Roster rows created by an admin (Households screen). `household_id` comes from the roster, falling back to `user_id`. | Created automatically on first use. Surrogate `household_id`. The Households screen stays for support and overrides. | None. Same `{org, household_id}` scope; the values are surrogates. |
| **Member** | Rows created ahead of time. Free-text `relationship`, one `is_guardian` flag. | Created at runtime through resolution. Adds `member_kind`, `minor`, `provenance`, aliases, confidence, and a lifecycle (`provisional` / `active` / `merged` / `inactive`). Surrogate `member_id`. | None. Same `{org, household_id, member_id}` scope; `member_id` is the stable key. |
| **Identity resolution** *(new)* | The agent maps a name to a `memberId` only if it is already in `householdMembers`. Otherwise it refuses. | The agent sends a member reference (`name`, `relationshipHint`). The control plane normalizes it, matches it inside the household, and returns `MATCHED`, `AMBIGUOUS`, `NEW` or `NEEDS_CONFIRMATION`. | None. Runs before Memory Bank is called. |
| **Preference classification** | Regex sensitivity classifier (normal / sensitive / restricted). | Also separates a preference to avoid something from a health condition. Health attributes take the strict path. | None |
| **Write authorization** | Writing another member's data requires `is_guardian`. | Authority depends on member kind (see the matrix below). | None. Checked before the write. |
| **Consent** *(new)* | Not modeled. | A consent ledger records every confirmed health write: who, about whom, category, prompt wording, time. Withdrawing consent triggers deletion. | None. Deletion uses the existing forget and purge. |
| **Purpose limitation** *(new)* | Not modeled. Only registered agents read, through resolve. | Agents declare a purpose. Schemas declare allowed purposes (default: personalization). Access approval rejects a mismatch. Minors' and health data are never allowed for advertising. | None |
| **Retention** | Dynamic memory only (the domain's `retention_days` sets an expiry on each write). Canonical schemas have none. | Three layers: Platform/Legal limits per sensitivity tier, then schema-owner retention within those limits, then overrides. | None. A control-plane retention sweep deletes values whose last write is older than the schema's retention. |
| **Duplicates / merge** | Not supported. | User-driven merge, split and rename inside a household. Two existing members are never merged automatically. | **A merge moves memories:** the retired member's memories are rewritten under the survivor's scope, then deleted. This is the only operation that changes Memory Bank keys. |
| **Authoritative source** | None. | Link fields from day one. Batch reconciliation deferred until a source exists; authoritative data then wins. | None for linking. Merges as above. |
| **Resolve / read** | Household-shared data always; per-member data only when a member is named. The snapshot lists `householdMembers`. | Same. The roster in the snapshot adds `memberKind`, `minor`, aliases and provisional status. | Unchanged |
| **Deletion** | Forget a member or a household (cascades). Purge by tier, attribute or topic. | Adds deletion on consent withdrawal, expiry of unconfirmed members, and removal of aliases and consent records. Backups handled as the law requires. | Existing forget and purge |
| **Agent** | Tools take an optional `member_id`. | Tools take a member reference. On `AMBIGUOUS` or `NEEDS_CONFIRMATION` the agent asks the user. The agent tells dislikes from allergies. | None |

The pattern from the first household design still holds. Almost everything happens in the control plane,
before Memory Bank is called. Memory Bank data changes shape in only two places: the retention sweep
deletes expired values, and a merge moves values under the kept member's scope.

---

## Member kinds and authority

| Writer → target | Normal preferences | Health data |
|---|---|---|
| Root → self | Allowed | Allowed after confirmation (consent recorded) |
| Root → dependent (`minor = true`) | Allowed | Allowed after confirmation. The parent's confirmation is the consent. |
| Root → dependent marked adult (e.g. adult son) | Proxy-adult rules | Proxy-adult rules |
| Root → proxy adult (spouse, etc.) | Allowed | Not stored against the person. (b) A household product filter ("exclude peanut products"), or (c) the adult records it through their own login. |
| Root → household-shared | Allowed | Product filter only |

**How (c) works while one login = one household.** An adult with their own login is the root of a
*separate* household. Under (c) they record their health data in their own household. Sharing it into
the other adult's household would need a household-link consent feature, which is out of scope for now.
Until then, the other household gets (b) only.

**The limit of (b).** A household filter isn't attributed to anyone. But in a two-person household it can
still point to one person, so Legal has to confirm it is acceptable.

---

## Identity resolution

Resolution is scoped to **one household**, so it never needs to search across customers.

1. **Normalize.** Lowercase; remove accents, punctuation and extra spaces; drop possessives and
   relationship words ("my son", "Ryan's").
2. **Load the household.** One indexed query for its active and provisional members and their aliases,
   typically 1–8 rows.
3. **Score each candidate.** Jaro-Winkler string similarity on names and aliases, with a phonetic match
   (Double Metaphone) as a second signal.
4. **Check the relationship.** Incompatible relationships (son vs daughter, child vs spouse) keep the score
   below the auto-match threshold, however similar the names are.
5. **Decide by tier.** A mention can match at most one member. Two existing members are never merged
   automatically.
6. **Remember variants.** On a confirmed match, the variant is stored as an alias so it matches directly
   next time.

### Confidence tiers

These are starting values. They should be tuned against a labeled set of name variants.

| Outcome | Normal attributes | Health attributes |
|---|---|---|
| Auto-match | Score ≥ 0.92 and relationship compatible | Exact name or known alias only |
| Ask ("Do you mean Ryan, your son?") | Score 0.80–0.92, or more than one candidate | Anything short of an exact or alias match |
| Create a new member | Score < 0.80; confirm the new person first | Score < 0.80; confirm the new person **and** the health fact |

A health write is confirmed **even after a match**. That confirmation is what the consent ledger records.

---

## Conversation examples

| User says | What happens |
|---|---|
| "My son Ryan doesn't like peanuts." (first mention) | Ryan isn't in the household, so the result is `NEW`. The agent asks: "Should I add Ryan, your son, to your household?" On yes: create a `DEPENDENT` with `minor = true` and save the dislike as a normal preference. |
| "Anikaa loves strawberries." (Anika exists) | Score about 0.95 and the relationship is compatible, so it auto-matches. "anikaa" is saved as an alias. |
| "Ryan is allergic to peanuts." | Matches Ryan. Because it's health data, the agent confirms: "I'll record that Ryan is allergic to peanuts. Is that right?" The consent record is written, then the allergy is saved. |
| "My wife is allergic to shellfish." | Wife is a proxy adult. The agent offers: "I can exclude shellfish products from household orders. Your wife can save her own allergy from her account." |
| "Sam wants oat milk." (two Sams) | `AMBIGUOUS`. The agent asks which Sam. |

---

## Data model

| Table | New fields | Why |
|---|---|---|
| `household_members` | `member_kind`, `minor`, `login_id` (root only), `normalized_name`, `provenance` (`INFERRED` / `USER_CONFIRMED` / `AUTHORITATIVE`), `match_confidence`, `authoritative_id`, `merged_into_member_id`, `created_by_agent_id`, `source_session_id`, `confirmed_at`; status gains `provisional` and `merged` | Runtime creation, audit, undo, future linking |
| `household_member_aliases` *(new)* | `org`, `household_id`, `member_id`, `normalized_alias`, `first_seen`, `source` | Duplicate prevention |
| `consent_records` *(new)* | `id`, `org`, `household_id`, `subject_member_id`, `granted_by_member_id`, `category`, `prompt_text`, `granted_at`, `withdrawn_at` | Proof of health-data consent; deletion on withdrawal |
| Schema versions | `retention_days` (optionally per attribute), `allowed_purposes` | Schema-owner retention and purpose limitation |
| Registered agents | `purpose` | Checked against `allowed_purposes` when access is approved |

Indexes: `(org, login_id)`, `(org, household_id)`, `(org, household_id, normalized_name)`, and the same
pattern on aliases.

---

## Retention

| Layer | Set by | Controls |
|---|---|---|
| **1. Limits** | Platform and Legal | Maximum retention per sensitivity tier. Health data is kept only while consent holds. Minors may get a stricter maximum. |
| **2. Schema retention** | Schema owner | Days per schema (optionally per attribute) within the limits. Values outside the limits are rejected at activation. Changes go through the existing schema-version approval and are audited. |
| **3. Overrides** | The system | User deletion, consent withdrawal, account inactivity, legal hold. These always win. |

- The retention clock runs from the **last write or confirmation**, so a re-confirmed allergy doesn't
  expire.
- **Unconfirmed (provisional) members expire after 30–90 days.** This is a platform setting, not a schema
  setting, because members span schemas.
- Deletion covers the roster, aliases, consent records, Memory Bank, cached session snapshots and backups.

---

## Purpose limitation

It is not yet known whether retail media (Kroger Precision Marketing) or another advertising pipeline will
ever read this data. We build the control now, denying by default, because adding it after data has
flowed somewhere is much harder.

- The only way data leaves the platform today is resolve, for a registered agent. So the check sits where
  schema access is approved: the agent's declared `purpose` must be in the schema's `allowed_purposes`.
- The default for `allowed_purposes` is `personalization`.
- Minors' data and health data are never allowed for advertising, whatever a schema declares.
- Allowing a new purpose is a governed change: Legal approval, a schema version change, and consent where
  the law requires it.

---

## Duplicates, merges and reconciliation

- **Merge** (user says "Anika and Anikaa are the same person"): pick a survivor, rewrite the other
  member's memories under the survivor's scope, delete the originals, mark the retired row
  `merged_into_member_id`. Audited and reversible through the audit trail.
- **Split** (two people were wrongly matched): create a new member and let the user reassign attributes.
- **Rename**: update the display name and keep the old name as an alias.
- **Authoritative source (future):** a batch job matches members to authoritative records using the same
  matching logic plus authoritative attributes, and sets `authoritative_id`. Linking changes metadata only.
  Only merges move Memory Bank data. Authoritative data wins on conflict.
- **A known interim duplicate:** a spouse with her own login is the root of her own household *and* may
  appear as a proxy adult in her husband's. That is accepted until a household-link feature or an
  authoritative source can join them.

---

## Scale

- **Matching cost doesn't grow with the customer base.** Each write looks only at its own household
  (1–8 members), so there is no global search.
- **Roster size.** Millions of households with a few members each means tens of millions of rows. That is
  comfortable for Postgres with the indexes above.
- **Root creation** is one upsert on a customer's first interaction, then cached in the session.
- **The consent ledger** is append-only and grows only with health writes.
- **The real limit is still the Memory Bank quota.** This design doesn't change it, and the lazy
  per-member reads still apply.
- **Merges** are rare and can be batched and rate-limited against the quota.

---

## Privacy and legal considerations

> Not legal advice. This is an engineering reading as of 2026, for Kroger Privacy/Legal to confirm.
> State privacy law changes quickly.

| Law | Why it applies | Key requirement | Effect on this design |
|---|---|---|---|
| **WA My Health My Data Act** (similar laws in NV, CT) | Allergies are very likely "consumer health data", and the law also covers health data inferred from other data. Kroger operates in WA (Fred Meyer, QFC). | Consent to collect (unless needed for a service the person asked for), separate consent to share, a health-data privacy policy, rights to access and delete (about 30 days; backups about 6 months). People can sue directly. | Consent must come from the person the data is about. A parent can consent for a child; a customer can't consent for a spouse. Hence the proxy-adult rules and the consent ledger. |
| **CCPA / CPRA** (CA) | Inferred profiles are personal information. Health data is "sensitive personal information". | Rights to know, delete and correct. Right to limit use of sensitive data. Collect and keep only what's needed, and disclose retention per category. Under-16s: no sale or ad sharing without opt-in (a parent for under-13s). The 2025 regulations add risk assessments for sensitive data. | Inferred members and preferences must be viewable, correctable and deletable. Purpose limitation keeps memory data out of advertising. |
| **Other state privacy laws** (CO, CT, VA, TX, OR, …) | Health data and a known child's data are "sensitive data". | Opt-in consent for sensitive data; parental consent under 13; several states add protections for teens under 18. | Same consent ledger; the `minor` flag. |
| **COPPA** (amended 2025) | Covers information collected *from* children under 13. A parent describing a child is generally not that. It would apply if a child used the agent. | Written retention policy, no indefinite retention, separate parental consent for third-party disclosure, a written security program. | Probably not triggered directly, but its retention discipline is the baseline. It becomes mandatory if children ever get their own logins. |
| **HIPAA boundary** | Kroger Health pharmacy is a covered entity. | Keep pharmacy data separate. | Pharmacy data never feeds grocery memory, and grocery memory never feeds pharmacy systems. A Health & Wellness agent needs its own isolated domain. |

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Wrong match puts an allergy on the wrong child | Physical harm | Relationship check, exact-or-alias only for health, confirmation on every health write |
| Name typo creates a duplicate | Preferences split across two records | Fuzzy and phonetic matching, aliases, user-driven merge |
| Bogus members or false facts added (typing or prompt injection) | Polluted household data | Only the logged-in root can add members; confirmation for new people; audit; rate limits |
| An inference can't be undone | A mistake becomes permanent | Provisional status, `merged_into`, audit trail, split and rename |
| Proxy-adult health data stored without that adult's consent | Legal exposure (MHMDA) | Options (b)/(c) only; nothing attributed to the person without their consent |
| Children's data reaches advertising | Legal exposure (CCPA, state laws) | Purpose limitation, deny by default; minors hard-denied |
| Same person in two households (spouses with separate logins) | Data out of sync between households | Accepted for now; household-link feature or authoritative source later |
| Retention too short for safety data | A known allergy disappears | Clock runs from last confirmation; health data kept while consent holds |

---

## Open items

**For Kroger Privacy/Legal**
1. Maximum retention per sensitivity tier, and whether minors need a stricter limit.
2. Whether option (b), the household product filter, is acceptable given it can point to one person in a
   small household.
3. Wording of the health-data confirmation prompt (it becomes the consent record).

**Engineering**
4. ~~Whether the Vertex profile store can expire a single profile field.~~ Resolved: retention is
   enforced by the control-plane retention sweep (purge by schema and last-write time). The sweep is
   triggered from the Households screen or the Admin API; nothing schedules it yet.
5. Tune the match thresholds on a labeled set of name variants, including nicknames and cultural name
   forms.
6. How much of the roster (aliases in particular) to include in the snapshot sent to the model.
7. Design of the household-link consent feature, which option (c) needs before data can be shared across
   households.

---

## Delivery order

Slices 1–5 are delivered. The "Later" items are not started.

| Slice | Content |
|---|---|
| 1 | Surrogate IDs, root creation on first use, `member_kind` / `minor` / `provenance` fields |
| 2 | Resolution service, reference-based writes, agent tool changes, confirmation flow |
| 3 | Dislike vs health classification, consent ledger, authority matrix |
| 4 | Purpose flags, schema-owner retention within limits, provisional-member expiry |
| 5 | Merge, split, rename (including moving memories on merge) |
| Later | Authoritative-source reconciliation job; household-link consent |

---

## Implementation notes

Built on `feature/dynamic-household-members`. End-to-end UI test steps:
[dynamic-household-test-guide.md](dynamic-household-test-guide.md).

Where the build refines the design:

- **Confirmation is enforced by the platform.** The first write for a new person or for health data
  never saves; it returns `needs_confirmation` with a platform-worded question. A health write only
  succeeds when `confirmed=true` redeems a **pending consent** created by that earlier call for the
  same person, attribute and value (pending prompts expire after 24 hours). A new person and a health
  fact about them share one question.
- **Phonetic matching uses Soundex**, not Double Metaphone, to avoid a new dependency. It only nudges
  scores that are already close (0.80 or more).
- **Provenance values:** `AUTHENTICATED` (root created from a login), `INFERRED` (proposed, not yet
  confirmed), `USER_CONFIRMED`, `ADMIN` (enrolled on the Households screen), `AUTHORITATIVE` (reserved).
- **Health rules key off `minor`:** health data is allowed for yourself, or for a minor you guard.
  Any other adult (a proxy adult, or a dependent marked not a minor) is refused.
- **Health is an attribute flag** (`validationRules.health`, set by the "Health data" checkbox in the
  setup wizard). It implies at least `sensitive`.
- **Merge** fills gaps in the kept member's profile (the kept member's values win on conflict) and
  only moves values in the agent's own per-member schemas. Values in other domains stay under the
  retired id, which records `merged_into_member_id`.
- **Retention limits** are placeholders pending Legal: 1095 days for normal data, 730 for sensitive
  or health data. Unconfirmed members expire after 60 days. A retention preview can use a future
  `asOf` date; an actual sweep always uses the current time.
- **Operator enrolment** on the Households screen still works: a member with a login signs in with
  its member id. A login that already roots another household is refused.
