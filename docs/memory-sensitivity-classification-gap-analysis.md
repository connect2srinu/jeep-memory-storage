# Memory Sensitivity & Classification — Legal Requirements vs Implementation

Analysis of the legal team's `agent_memory_sensitive_examples` matrix against the code on
`feature/dynamic-household-members` (re-checked 2026-09-23).

**Summary:** a deterministic, server-side classification and source gate runs on every write (canonical
preferences, events, and dynamic memories). It blocks restricted content everywhere, stores sensitive
content only when the customer directed it, persists and surfaces the tier and source, and — since the
household work — adds health-data handling with confirmation, consent, and minor/adult rules. What is
still missing is **semantic** inference detection and **redaction** to the actionable form; both need a
model or agent-side discipline, not more patterns.

## The legal matrix

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

## Requirements

- **R1 — Store the actionable form, not the protected fact** ("avoid pork", not "is Muslim").
- **R2 — Suppress protected-class inferences** (religion, ethnicity, health condition or risk,
  pregnancy), even when derivable.
- **R3 — Classify each memory:** non-sensitive / sensitive / restricted.
- **R4 — Capture source:** user-directed vs inference.
- **R5 — Sensitive handling:** the actionable preference may be stored even when sensitive (rows 1–2);
  the underlying sensitive fact only when the user explicitly directs it (row 8). User-mentioned is not
  the same as user-directed (row 7).
- **R6 — Restricted is never stored,** even when user-directed (rows 9–10).

## Status

| Requirement | Status | Evidence / remaining gap |
|---|---|---|
| R1 actionable form | 🟡 Partial | The whitelist (catalog attributes + approved topics) limits *what kind* of thing can be stored, and the agent instruction asks for the actionable form. There is no server-side redaction; the stored value is what the agent sends. |
| R2 suppress inferences | 🟡 Partial | Explicit protected-class content (religion, pregnancy, diabetes, cancer, HIV, disability, medication) sent as `source: inference` is rejected. Inferences the value doesn't literally contain (religion from "avoid pork") are not detected. Managed generation is off, so the provider never infers on its own. |
| R3 classification | ✅ Implemented | Effective tier = max(attribute's declared `sensitivity_classification`, per-topic declared tier, content scan). Dynamic memories store their tier; canonical values take it from the catalog. Both are surfaced in the snapshot (`sensitivity` on every preference) and audited. |
| R4 source | ✅ Implemented | Every write carries `source` (`user_directed` default, or `inference`); recorded in the memory and the `memory_write` audit event; surfaced as `memorySource` for dynamic entries. |
| R5 sensitive handling | 🟡 Mostly | Sensitive + inference ⇒ rejected (403); sensitive + user-directed ⇒ stored and tagged. Row 7's distinction (mentioned vs directed) depends on the agent labelling the source correctly; the agent always sends `user_directed`. |
| R6 restricted | ✅ Implemented | Restricted categories — SSN, card, phone, email, credentials, weapons, discriminatory targeting — are rejected (400) on every write path; attribute-level `restricted` is also enforced. Patterns are deterministic, not exhaustive. |
| Platform-enforced | ✅ | The gate runs server-side on every write; the agent can't bypass it. |

## Added since the original analysis: health data and minors

These address the same legal concerns (WA My Health My Data Act, CCPA sensitive data, state laws):

- **Health attributes** (the wizard's *Health data* checkbox, `validationRules.health`) are at least
  sensitive and take a stricter path.
- **Confirmation and consent:** a health write never saves on the first call. It returns
  `needs_confirmation` with a platform-worded question; only `confirmed=true` redeeming a pending consent
  for the same person, attribute, and value (24-hour expiry) saves it. The consent ledger records who
  consented, about whom, the prompt, and when. Forgetting the value withdraws the consent.
- **Who may record whose health data:** yourself, or a minor you guard. Another adult's health data is
  refused (`not_allowed`); the agent can offer a household-level product filter instead.
- **Purpose limitation:** health and per-member data never reach an agent whose purpose is advertising.
- **Retention limits:** 730 days for sensitive and health data, 1095 for normal (placeholders pending
  Legal).

See [Dynamic Household Members](dynamic-household-members-design.md).

## Remaining gaps

1. **Semantic inference detection.** Deriving "is Muslim" from "avoid pork" needs a classifier model or
   an agent-declared category; patterns catch only explicit content.
2. **No redaction to the appropriate form.** The value is stored as sent.
3. **Source is agent-declared.** The platform enforces the rule but trusts the label.
4. **Category lists are deterministic and incomplete** — defense in depth, not a guarantee.

## What works in our favor

- **Whitelist governance:** nothing can be stored unless someone approved an attribute or topic for it.
- **Managed generation disabled:** the provider never auto-writes "is Jewish"-style inferences.
- **One write gate** in the control plane for every path, so new rules apply everywhere at once.

## Code map

- Classification: `apps/control-plane-api/app/control_plane_api/services/memory_classification.py`
- Write gate: `_screen_memory_write` and `_health_gate` in `services/runtime_service.py`
- Tiers and sources: `domain/sensitivity.py`; retention limits: `domain/governance.py`
- Tests: `test_memory_classification.py`, `test_runtime_api.py`, `test_dynamic_household.py`
