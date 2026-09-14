# Memory Sensitivity & Classification — Legal Requirements Gap Analysis

Analysis of the legal team's `agent_memory_sensitive_examples` matrix against the codebase
(`feature/adk-dual-memory`).

> **Implementation update (first slice landed):** a deterministic, server-side **memory
> classification & source gate** is now enforced on every write (canonical `update_preference`,
> `ingest_event`, and dynamic `write_dynamic_memory`). It enforces attribute-level sensitivity,
> blocks Restricted categories (PII, weapons, discriminatory targeting) on **all** writes, captures
> **source** (user-directed vs inference) and applies the rule *sensitive + inferred ⇒ reject*, and
> audits the effective sensitivity + source in the `memory_write` log. See **Implemented** below.
> The remaining gap is semantic inference detection (needs a classifier model) and surfacing the
> tags in the resolve snapshot.

Original verdict: the platform had **partial building blocks** (a whitelist model, an unenforced
attribute-level sensitivity field, a PII denylist, a source concept in the resolver) but did not
implement the core policy the matrix describes.

## The legal matrix (transcribed)

| # | Example user message | Appropriate memory (store) | Inappropriate memory (do NOT store) | Class | Source |
|---|---|---|---|---|---|
| 1 | Observes kosher dietary practices; wants kosher-aligned recommendations | "Household follows kosher practices; prefers kosher recommendations" | "…is likely Jewish" | Sensitive | User-directed |
| 2 | Type 2 diabetes; wants lower-sugar / diabetic-friendly suggestions | "Has Type 2 diabetes; prefers lower-sugar, diabetic-friendly recs" | "…at elevated risk for cardiovascular disease and obesity" | Sensitive | User-directed |
| 3 | Avoid uncooked meat, deli meats, raw sushi, unpasteurized dairy, alcohol | "Wants to avoid [those foods]" | "…is pregnant" | Non-sensitive | User-directed |
| 4 | No pork recipes | "Avoid pork recipes" | "…is Muslim / is Jewish" | Non-sensitive | User-directed |
| 5 | Planning a fish fry for Lent | "Likes fish / hosting fish fry" | "…is Catholic" | Non-sensitive | Inference |
| 6 | Favorite foods: grandma's fajitas, tamales, salsa | "Fondly remembers grandma's fajitas/tamales/salsa" | "…is Hispanic" | Non-sensitive | Inference |
| 7 | New medication, appetite down, wants protein/hydration/low-GI foods | "Wants protein-rich, hydrating, low-GI recommendations" | "…started a GLP-1 medication" | Non-sensitive (appropriate) / Sensitive (inappropriate) | Inference / User-directed |
| 8 | "Remember that I am Muslim." | "User is Muslim" | n/a | Sensitive | User-directed |
| 9 | "Remember I wish I could bring my guns into Kroger." | n/a | "User likes guns" | Restricted | User-directed |
| 10 | "Don't let a &lt;race&gt; person pick my grocery order." | n/a | "User dislikes when &lt;race&gt; people pick their groceries" | Restricted | Inference |

## Distilled requirements

- **R1 — Store the actionable form, not the protected fact.** Persist the dietary/food preference,
  not the underlying protected characteristic ("avoid pork", not "is Muslim").
- **R2 — Suppress protected-class inferences.** Never store inferred religion, ethnicity, health
  condition/risk, or pregnancy (the "inappropriate" column), even when derivable.
- **R3 — Classify each stored memory:** Non-sensitive / Sensitive / Restricted.
- **R4 — Capture source:** User-directed vs Inference.
- **R5 — Sensitive handling:** an actionable preference may be stored even when Sensitive (rows 1–2),
  but the underlying sensitive fact is stored **only if the user explicitly directs it** (row 8);
  otherwise suppressed (rows 1–7 "inappropriate"). User-directed does **not** by itself make a
  sensitive fact storable (row 7: GLP-1 is user-mentioned yet not stored).
- **R6 — Restricted → never store,** even when user-directed (rows 9–10: weapons, discrimination).

## Codebase mapping

| Requirement | Status | Evidence / gap |
|---|---|---|
| R1 store appropriate form | 🟡 Partial | Whitelist + the classification gate block restricted/sensitive-inferred content, but there is still no server-side **redaction** to the actionable form — the stored value is what the agent supplies. |
| R2 suppress protected-class inferences | 🟡 Partial | Now enforced for *explicit* protected-class content flagged as inference (rejected). **Residual gap:** subtle inferences the value doesn't literally contain (e.g. deriving religion from "avoid pork") need a classifier model. Managed generation stays off. |
| R3 sensitivity classification (3 tiers) | ✅ Implemented (enforcement) | `sensitivity_classification` is now read at runtime and enforced; a content classifier assigns a tier to every write; effective tier is audited. **Remaining:** dynamic memory has no per-topic declared sensitivity yet, and tiers aren't surfaced in the resolve snapshot. |
| R4 source (user-directed vs inference) | ✅ Implemented | Writes carry a `source` field (`user_directed`/`inference`), recorded in the `memory_write` audit. |
| R5 sensitive handling rule | ✅ Implemented | Sensitive + inferred ⇒ rejected; sensitive + user-directed ⇒ stored and tagged; non-sensitive ⇒ stored. |
| R6 restricted hard-block | ✅ Implemented | Restricted categories (PII, weapons, discriminatory targeting) blocked on **all** writes (canonical + dynamic + events); attribute-level `restricted` also enforced. **Residual:** category patterns are deterministic, not exhaustive. |
| Platform-enforced (not agent) | ✅ Implemented | The gate runs server-side on every write, deterministically. Source is agent-declared but the platform makes the decision. |

## Implemented (this slice)

Server-side, deterministic, no model dependency:

- **`domain/sensitivity.py`** — `SensitivityTier` (`normal`/`sensitive`/`restricted`) and
  `MemorySource` (`user_directed`/`inference`) with tier ordering.
- **`services/memory_classification.py`** — `classify_content(value)` scans for categories (PII,
  weapons, discriminatory targeting ⇒ Restricted; religion/ethnicity/health keywords ⇒ Sensitive);
  config-extendable pattern list.
- **`runtime_repository`** — the runtime grant now carries each attribute's
  `sensitivity_classification` from `preference_definitions`.
- **`runtime_service._screen_memory_write`** — effective tier = max(declared attribute tier, content
  scan); **Restricted ⇒ reject (400)**, **Sensitive + inference ⇒ reject (403)**, otherwise allow.
  Applied to `update_preference`, `ingest_event`, and `write_dynamic_memory`.
- **Requests** carry `source` (`user_directed` default / `inference`).
- **Audit** — the `memory_write` log now records `sensitivity` and `source`.
- Tests: `test_memory_classification.py` plus runtime integration tests for restricted-content
  blocking on all writes and the sensitive-requires-user-directed rule.

## Remaining gaps

1. **Semantic inference detection.** Deriving "is Muslim" from "avoid pork" needs a classifier model
   or agent-declared category — regex only catches explicit content.
2. **No redaction to the appropriate form.** Storage still takes the agent's value verbatim.
3. **Dynamic per-topic sensitivity.** Dynamic writes default to `normal`; there is no per-topic
   declared tier yet (only content scan + source apply).
4. **Tags not surfaced in resolve.** Sensitivity/source are enforced and audited but not returned in
   the effective-preference snapshot or persisted on the memory record.
5. **Category lists are deterministic, not exhaustive** — defense in depth, not a guarantee.

## What is genuinely working in our favor

- **Whitelist governance** (canonical schema attributes + approved dynamic topics) means the system
  cannot store arbitrary protected facts unless someone explicitly approves an attribute/topic for
  them — a strong coarse control.
- **Managed generation disabled** removes the provider's own inference/extraction path, so the model
  never auto-writes "is Jewish"-style inferences.
- The **PII denylist** already blocks a class of Restricted content on dynamic writes.
- Building blocks exist to extend: `sensitivity_classification`, `PreferenceSource.INFERRED_MEMORY`,
  the resolver's source/confidence machinery, and a single write path to hook.

## Recommendation — a server-side memory-classification gate

Add one classification step on **every** write (canonical `update_preference`, `ingest_event`, and
`write_dynamic_memory`), platform-enforced and deterministic in its decision:

1. **Classify content** into a category set (religion, ethnicity, health-condition, pregnancy,
   weapons, discrimination, PII, …) → maps to Non-sensitive / Sensitive / Restricted. Reuse and
   extend `sensitivity_classification`; make the category list config-driven.
2. **Capture source** — require the write to declare `source: user_directed | inference` (the agent
   already knows which tool/intent it used; the platform records and can down-rank inference).
3. **Apply policy:** Restricted ⇒ reject; Sensitive + inference ⇒ reject; Sensitive + user-directed
   ⇒ store and tag; Non-sensitive ⇒ store. Enforce the attribute-level `restricted` classification.
4. **Persist + surface + audit** the sensitivity and source on each memory; include them in the
   resolve snapshot and the `memory_write` / `memory_deletion` events.
5. **Extend the denylist** into a category classifier and run it on canonical writes too.

**Caveat on feasibility:** reliably detecting *"likely Jewish"*-style inferences and distinguishing
user-directed from inferred intent is not achievable with regex alone — it needs either (a) the agent
to pass an explicit source/category with each write (fast, but trusts the agent) or (b) a
classification model in the control plane (governable, deterministic to invoke, but a model
dependency). A layered approach — agent-declared source + a server-side category classifier for
Restricted/protected content + the existing whitelist — gives defense in depth. This is a
**substantive new capability**, not a config change.

## Bottom line

The **infrastructure and guardrails exist** (whitelist, disabled managed generation, an unenforced
sensitivity field, a source enum, a PII denylist), but the **legal classification policy itself is
not implemented**. Closing it is a well-scoped feature centered on a single server-side
classification gate plus source capture.
