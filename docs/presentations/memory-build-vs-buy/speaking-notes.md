# Speaking Notes — Memory Bank for GEAP (Presentation 2)

**Audience:** technical managers · **Duration:** ~30–40 min + Q&A · **Deck:** `memory-build-vs-buy-three-way.md`

> **This is the follow-up to the custom-architecture talk.** Last time we presented a custom memory
> design and the room asked us to evaluate **Memory Bank**. This talk is the answer to that homework:
> we evaluated it seriously, we're adopting it, and we kept only the thin governance layer it doesn't
> provide. Tone: *not* a reversal — a convergence.

## The one sentence to land
> "You asked us to look at Memory Bank — we did, we're using it as the storage engine, and the only
> thing we keep building is the thin governance layer Memory Bank doesn't have. That's less custom
> code than we proposed last time, with Google's managed scale and SLA underneath."

## Three landmines to avoid saying
- ❌ "Last time we were wrong." → You weren't. The gaps you identified are *real*; Memory Bank just
  covers most of the rest. Say **"we've refined the design in light of your feedback."**
- ❌ Introducing the Control Plane in the first five minutes. → It reads as defending custom. Earn it
  first (slides 3–5), introduce it at slide 6.
- ❌ Overclaiming Memory Bank's weaknesses. → The original doc did that and it didn't survive
  fact-checking. Be the honest narrator: correct the stale claims *yourself*, keep only the two real gaps.

---

## Talk track, slide by slide

### Opening (before slide 1) — 1 min · set the frame
> "When we last met, we walked through a custom memory architecture, and the guidance was clear: before
> you build, evaluate Google's Memory Bank. We took that seriously. We ran it against hard gates,
> fact-checked the claims — including our own — and today I'll show you what we found and what we
> recommend. Short version: we're adopting Memory Bank. The question this talk answers is *how much,
> if anything, we still build around it* — and the answer is: a thin governance layer, and only that."

Transition: "Let me start with the shape of the decision, because it's not the two-way choice it looks like."

### Slide 1 — It's a three-way choice, not two · 3 min
- Name the original framing honestly: **Custom vs. Pure Memory Bank.** Then reframe: there's a third
  option we've actually built — **Memory Bank governed by a thin Control Plane.**
- Give each option one honest line (from the slide): Custom = full control, 35–45 person-weeks + ~1 FTE
  forever. Pure Memory Bank = lowest effort, but no hard never-store, no bulk export. Hybrid = moderate
  effort, agents call a simple interface, governance enforced then storage delegated to Google.
- **Say the quiet part:** "The real decision isn't build-vs-buy. It's **raw Memory Bank vs. Memory Bank
  with our governance in front of it**. Both *buy* the storage."

Transition: "So how do we decide between those? Not with a scorecard — with gates."

### Slide 2 — Decision gates · 3 min
- "A weighted scorecard gave a 3.45-to-3.40 near-tie and then had to be overridden case by case. That's
  the scorecard telling you the weights are wrong."
- Introduce **gates first (pass/fail), score only the survivors.** Walk the six gates at a high level.
- The two gates that matter: **G1 never-store** and **G6 bulk/clean-exit** — Memory Bank's only two
  genuine, confirmed gaps. Everything else substantially closes (next slide).
- Concrete hook for managers: "A pharmacy / Health-&-Wellness agent — prescriptions, HIPAA — *needs*
  G1 and G6. That single fact rules out pure Memory Bank and leaves Custom or Hybrid."

Transition: "And before we trust those gates, we had to correct the record on Memory Bank itself."

### Slide 3 — Re-validation (the credibility slide) · 4 min · **most important slide**
- Be explicit and fair: "The original assessment was written by the owner of the custom solution.
  Several Memory Bank limitations didn't survive fact-checking against Google's current docs. Here's
  the corrected picture." (This is what earns you the room's trust for the rest of the talk.)
- Walk the four corrections crisply:
  - **SLA:** Memory Bank hit **GA on Dec 16, 2025** → SLA/SLOs apply. "No SLA" is stale.
  - **Deletion/retention:** **granular TTL (30/90/365 days) + `DeleteMemory` + revisions** — supported.
  - **5-KV "cap":** that's the **scope *identifier*** (namespace dimensions), **not** a limit on how
    many memories you store or recall. Common misread.
  - **Direct writes:** synchronous `CreateMemory` exists — not forced into a racy background path.
  - **Quota:** **300 reads/min + 100 writes/min per project·region**, raisable via GCP.
- Then the honest close: "**Two gaps genuinely remain — no hard never-store denylist, no bulk/SQL
  export.** Hold that thought, because that's precisely what our layer adds."

Transition: "Those two gaps — plus the governance an enterprise needs — are the whole reason the thin
layer exists. Here's what it is."

### Slide 6 (deck §10) — Introduce the Control Plane, delineated · 4 min · **the reveal**
> Present slide 10 ("Control-Plane dependency, delineated") *here* — this is where you name the Control
> Plane for the first time. Use the three-layer picture.
- "This is **not** 'buy the whole Control Plane to get memory.' Memory Bank does the storage. The
  Control Plane adds only the enterprise governance Memory Bank can't: **never-store enforcement,
  per-schema RBAC, deterministic resolution, sensitivity screening, governed deletion, audit, and
  per-member scope.**"
- "What it delegates to Google, unchanged: **durable storage, retrieval, DR, low per-op cost.**"
- "Coupling is bounded: the agent talks to a **small HTTP contract** — `resolve / save / dynamic /
  forget` — through a self-contained client. **No SDK lock-in, no schema baked into the agent.**"
- Portability line for the skeptics: "Because **Postgres is our system-of-record**, all data is
  SQL-exportable — that's how the Hybrid also closes the clean-exit gap."

Transition: "Let me show you it actually running — one write, one read."

### Slide 4 — How the Hybrid works (the flow) · 3 min
- **Write path:** never-store screen → sensitivity + RBAC → governed write → audit → **Memory Bank
  (storage) + Postgres (system-of-record).** "Governance runs *before* anything is stored."
- **Read path:** deterministic **list-by-scope** (not similarity guesswork) → merge canonical + dynamic
  + session → prioritize → return a trustworthy snapshot.
- The manager takeaway: "Agents see a **simple `save()` / `resolve()`**. Every enterprise rule lives in
  the platform, not in each app's code — so governance is uniform and can't be forgotten per team."

Transition (optional demo hook): "One capability this unlocks that pure Memory Bank can't govern —
households." *(Use the household example only if you have time; it's a strong concrete proof point.)*

### (Optional) Household proof point · 2 min
- "Real GEAP case: ~95% of users are one person = one member, but ~5% (growing) are **households with
  multiple members** — a shared account, kids with no login. Memory Bank stores profiles; it doesn't
  know who may write for whom."
- "Our layer models a **household roster** in Postgres: household-shared data, per-member data, and a
  **guardian check** before anyone writes another member's profile. Deletion is scope-precise — 'forget
  Timmy' removes only Timmy's partition; 'forget household' cascades." (See appendix A1.)
- Point: "That's governance Memory Bank *can't* enforce alone, delivered without changing the storage
  engine."

Transition: "So that's the what and the how. Managers care about three more things — will it scale, can
we run it, and how do apps adopt it."

### Slides 7–9 — Operational readiness (scale / Day-2 / adoption) · 5 min
- **Scalability (slide 7):** "The one ceiling is the Vertex quota — 300 reads/min per project·region.
  It's **raisable, and Google (Kapil) has already agreed to ~10×** → ~3,000 reads/min. Our access
  patterns keep us well under it: **lazy per-member resolve, session-cached snapshot, per-LOB Memory
  Banks** for heavy/regulated lines. Cost isn't the constraint — managed generation is off."
- **Operations (slide 8):** "Every write/delete is **audited** (never the values). Deletion and
  retention are first-class. Provider `429` maps to **`503 + Retry-After`** so consumers back off
  cleanly; the 10× raise removes the common trip."
- **Adoption (slide 9):** "Apps **own** prompts, tools, workflows. They **inherit** memory,
  governance, RBAC, deletion, audit, scaling. Onboarding is **register + 6 env vars + reuse the client,
  2 callbacks, 3 tools** — hours, not weeks. New platform capabilities reach every app with no agent
  change, because the agent learns everything from the snapshot at runtime."

Transition: "Where are we, and what's next."

### Slide 11 — Timeline · 2 min
- **Phase 0 (done):** dual memory, governance, deletion, observability, **household + per-member
  memory**, thin-agent onboarding. "The foundation is delivered — not a proposal, working code."
- **Phase 1 (next):** quota 10× (Google-agreed), `429→503`, per-LOB Memory Bank strategy, household
  admin UI, SLA/DR confirmation.
- **Phase 2 (planned):** memory-quality/eval harness, schema registry + change notification,
  conflict-resolution hardening, cost/usage dashboards.

### Close — Recommendation + the ask · 2 min
- "**Default to the Hybrid.** It passes every gate and inherits Google's managed storage, SLA, and
  low per-op cost. **Reserve pure Custom** only for use cases that need first-class high-volume SQL
  analytics. **Pure Memory Bank alone** is fine only where none of the governance gates apply."
- **Make the ask explicit** (managers want a decision to make): 
  1. Endorse the **gate-first framework** as how we choose per line of business.
  2. Approve proceeding on the **Hybrid default** for the regulated LOBs (pharmacy/health first).
  3. Support the **Phase-1 items that need org backing** — the Google quota raise and SLA/DR confirmation.
- Land the closing line (the one-sentence-to-land, above).

---

## Anticipated Q&A (crisp answers)

- **"Aren't you just rebuilding custom under a new name?"** → No. Storage, retrieval, DR, scale, cost
  are Google's, unchanged. We keep ~a governance shim: never-store, RBAC, resolution, audit, export.
  That's a fraction of the 35–45 person-weeks a full custom build costs.
- **"What if the Control Plane is down?"** → Reads continue from the **cached session snapshot**; writes
  are deferred/retried. The API is stateless and horizontally scaled; Postgres is durable; **Memory
  Bank storage is independent of Control-Plane uptime.**
- **"What's the lock-in?"** → Agent → small HTTP contract (`resolve/save/dynamic/forget`), no SDK
  baked in. Postgres is system-of-record, so data is **SQL-exportable** — clean exit by design.
- **"Is the quota a real risk?"** → It's the only ceiling, it's raisable, **10× already agreed with
  Google**, and our steady-state load sits far below it (lazy resolve + session cache).
- **"Why not wait for Google to add governance?"** → We don't control that roadmap; the gaps (never-store,
  clean exit, per-schema RBAC) block regulated LOBs *today*, and our layer is thin and already built.
- **"Cost?"** → Managed generation is off, so no per-op LLM cost; the cost driver is Memory Bank
  read/write ops within quota, plus a stateless API + Postgres we already run.
- **"Multi-agent conflicts?"** → Per-schema ownership (WRITE only on owned schemas), deterministic
  resolution (source priority + schema precedence), versioned writes. See appendix A2.
- **"Still open?"** → Exact SLA % and RTO/RPO, multimodal handling, per-project instance cap,
  separation-of-duties granularity — all flagged to our GCP contact (deck §6).
