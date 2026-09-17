# Unified Memory Layer — Custom vs. Memory Bank vs. Hybrid

**A three-way assessment for the team.** Status: for review.

> **Importing to Confluence:** import this file via **Confluence → Import → Markdown**, then attach the four images in `img/` to the page so the `![](img/…)` references resolve. PNGs are used for maximum compatibility.

> **What's new vs. the original assessment:** (1) a **third option** — Hybrid (our Control Plane over Memory Bank) — which the original compared out of existence; (2) a **re-validation** of the Memory Bank claims, several of which were wrong or outdated; (3) a **gate-first framework** so the decision is made on what's decisive, not on a near-tie scorecard.

---

## 1. The headline: it's a three-way choice, not two

The original document framed this as **Custom (build our own)** vs. **Pure Memory Bank (adopt Google's)**. But what our team has actually built is a **third option**: a governed **Control Plane *over* Memory Bank** — Google runs the managed storage; our layer adds the governance Memory Bank lacks.

![Three options: Custom Design, Pure Memory Bank, and Hybrid (Control Plane over Memory Bank)](img/01_three_options.png)

**Key message:** the real decision is **raw Memory Bank vs. Memory Bank governed by our Control Plane** — and the Hybrid keeps Google's managed storage/SLA/cost while adding enterprise control.

**Talking points**
- **Custom:** full control, but 35–45 person-weeks to build plus 1–1.5 ongoing FTE — we own extraction, merge, and compliance code forever.
- **Pure Memory Bank:** ready-made connector, lowest effort — but no hard "never-store," no bulk export, instance-wide config.
- **Hybrid:** moderate effort — agents call a simple interface; the Control Plane enforces governance, then delegates storage to Memory Bank with Postgres as system-of-record.

---

## 2. Decision gates — decide on what's decisive

A weighted scorecard produced a 3.45-vs-3.40 near-tie and then had to be overridden per use case. That's the sign the weights were wrong. Instead, check **non-negotiable gates first** (pass/fail); only score the survivors.

![Gate matrix: six gates scored pass/partial/fail across Custom, Pure Memory Bank, and Hybrid](img/02_gate_matrix.png)

**Key message:** the **Hybrid passes every critical gate**; pure Memory Bank fails on never-store and clean exit.

**Talking points**
- **G1 never-store** and **G6 bulk/SQL exit** are Memory Bank's two genuine, confirmed gaps.
- **G2 deletion/retention, G3 recall, G4 SLA** substantially close for Memory Bank once the facts are corrected (next section).
- Gates make the client decision almost mechanical: **a use case that needs a gate rules out any option that can't meet it.**
- Example — a **pharmacy / Health & Wellness agent** (prescriptions, DEA/HIPAA) needs G1 + G6 → pure Memory Bank is out; **Custom or Hybrid** qualify.

---

## 3. Re-validation — correcting the Memory Bank claims

The original assessment was authored by the owner of the Custom solution; several Memory Bank limitations did not survive fact-checking against Google's current documentation.

![Re-validation: four claims corrected, plus the two gaps that genuinely remain](img/04_revalidation.png)

**Key message:** Memory Bank is **stronger than the original doc claims** — but its two real gaps are **exactly what the Hybrid's Control Plane adds**.

**Talking points**
- **SLA:** Memory Bank reached **GA on Dec 16, 2025** → SLA/SLOs now apply. The original "no SLA → 2/5 resiliency" is stale.
- **Deletion/retention:** **granular TTL (30/90/365 days) + `DeleteMemory` + audit/revisions** — retention is supported, not absent.
- **5-KV "cap":** that's the **scope *identifier*** (namespace dimensions), **not** a limit on how many memories you store or recall.
- **Writes:** **direct synchronous `CreateMemory`** exists — you're not forced into the racy background path.
- **Quota (corrected):** **300 reads/min, 100 writes/min per project per region** (raisable via GCP). *(This also corrects the earlier ~10/min figure — our 429s at ~490/min and clean runs at ~60/min both fit a 300/min cap.)*
- **Still true:** no hard **never-store denylist**, no **bulk/SQL export** — both provided by the Hybrid.

---

## 4. How the Hybrid works — the flow

The Control Plane sits in the write and read paths, enforces governance, then hands storage to the managed service.

![Hybrid write and read flow through the Control Plane to Memory Bank and Postgres](img/03_hybrid_flow.png)

**Key message:** governance is enforced **before anything is stored**; storage stays managed.

**Talking points**
- **Write:** never-store screen → sensitivity + RBAC → governed write → audit → Memory Bank (storage) + Postgres (system-of-record).
- **Read:** deterministic **list-by-scope** (not similarity guesswork) → merge canonical + dynamic + session → prioritize → return a trustworthy snapshot.
- Agents see a **simple `save()` / `resolve()`** interface; all enterprise rules live in the platform, not agent code.
- **Best of both:** managed storage, SLA, low cost from Memory Bank; never-store, deterministic recall, RBAC, audit, clean exit from the Control Plane.

---

## 5. Finalized criteria to propose to the client

**Tier 1 — Decision Gates (pass/fail, per use case).** Checked first; disqualify any option that can't meet a required gate.

| Gate | Custom | Pure Memory Bank | Hybrid |
|---|---|---|---|
| G1 Provable never-store (code-enforced denylist) | ✅ | ❌ | ✅ |
| G2 Policy deletion & retention (TTL + delete + audit) | ✅ | ✅ | ✅ |
| G3 Deterministic recall of standing instructions | ✅ | ◐ | ✅ |
| G4 Contractual SLA + documented DR (RTO/RPO) | ✅ | ◐ | ◐ |
| G5 Separation of duties (config-change ≠ deploy) | ✅ | ◐ | ✅ |
| G6 Bulk / SQL analytics & clean exit | ✅ | ❌ | ✅ |

*(✅ meets · ◐ partial/conditional · ❌ structural gap)*

**Tier 2 — Weighted trade-offs (only for use cases that trigger no gate).** Re-weighted so importance isn't inverted:

| Criterion | Weight |
|---|---|
| Data Governance & Compliance (residency, audit depth, consent) | 18% |
| Security & Multi-tenant Isolation (RBAC, per-LOB, quota blast radius) | 12% |
| Cost & TCO (incl. per-LOB instances, generation-model & write-cadence traps) | 18% |
| Operability, Maintainability & Delivery Velocity | 15% |
| Reliability, DR & Service Maturity | 12% |
| Performance, Scalability & Quota Headroom | 10% |
| Data Modeling & Feature Fit | 8% |
| Memory Quality & Evaluability | 7% |

Gates capture the binary must-haves; Tier 2 grades the rest — so nothing is double-counted.

---

## 6. Recommendation

- **Default to the Hybrid** (Control Plane over Memory Bank): it passes every gate and inherits Google's managed storage, SLA, and low per-op cost.
- **Reserve pure Custom** for use cases that need direct SQL/bulk analytics as a first-class, high-volume path.
- **Pure Memory Bank alone** is viable only for use cases that trigger **none** of G1/G3/G5/G6.
- **Per line of business,** run the Tier-1 gate checklist first; only reach for the Tier-2 scorecard when no gate decides it.

### Still to confirm with our GCP contact
- Exact **SLA %** and documented **RTO/RPO** for Memory Bank (GA).
- **Multimodal** handling (text-only vs. images/attachments).
- **Per-project resource cap** for reasoning-engine instances.
- **Separation-of-duties** granularity in current IAM roles.
