# Memory Layer — Build vs Buy Gap Analysis

**Purpose:** Compare a custom-built memory layer (custom DB + MCP) against the current managed Memory Bank implementation, across the team's agreed Areas of Assessment, to support the Build vs Buy decision.
**Status:** Draft for team review — several rows are gated on spikes (marked ⚠ Needs data).
**Baseline:** GEAP Control Plane (`cloud-geap-control-plane-apaasg`) — FastAPI control plane, PostgreSQL system of record, Vertex Memory Bank (`agentplatform` 2.x) as the managed store, deterministic in-process preference resolver.
**Framework:** The 9 weighted areas and weights below were defined by the team (business directives: Cost, Maintainability; technical requirements: DR, Scale, Exit, Ontology).

> **Terminology.** "Buy / Managed" = the **current implementation** — a governance Control Plane API wrapping Vertex Memory Bank. "Build / Custom" = replace the managed store with a self-hosted DB + custom memory logic, exposed to agents via MCP. The Control Plane API, PostgreSQL system of record, and resolver are assumed to stay in both options; only the **memory store** changes.

---

## 1. How to read this document

- **Current (Buy)** = what the managed implementation does today, verifiable in code.
- **Custom (Build)** = what a self-hosted solution would entail.
- **Gap / Leaning** = which option the evidence favors for that area, and why.
- **Confidence** = High / Med / Low based on available evidence.
- **⚠ Needs data** = no evidence in the codebase or from the vendor yet; convert to a Jira spike.

Nothing below assumes a cost, latency, or DR figure we have not measured. Where a number is required, the row is marked ⚠ and a spike is proposed in §12.

---

## 2. Weighted assessment summary

| # | Area | Weight | Leaning | Confidence | Spike needed |
|---|---|---:|---|---|---|
| 1 | Cost & TCO | 20% | Neutral | Low | ✅ Cost spike |
| 2 | Maintainability & Complexity | 20% | **Buy** | Med–High | — |
| 3 | Feature Parity & Data Modeling | 15% | Mixed (Buy: conflict resolution · Build: ontology, field-level updates) | Med | ✅ Data-model spike |
| 4 | Resiliency & DR | 10% | **Build** *if Active/Active is hard-required* | Low | ✅ DR/multi-region spike |
| 5 | Performance & Scalability | 10% | Neutral | Low | ✅ Load spike |
| 6 | Agent Integration | 10% | Neutral → Build *if heterogeneous hosts* | Med | — |
| 7 | Exit Strategy | 5% | **Buy acceptable** (strong config portability) | Med | — |
| 8 | Governance & Security | 5% | Slight **Build** | Med | ✅ PII/compliance review |
| 9 | Migration Path | 5% | Neutral | Low | ✅ KSA migration spike |

**Scores intentionally left blank.** A 1–5 score per area × weight produces the final matrix, but four of the highest-weight rows (Cost, DR, Scale, Migration) cannot be scored honestly until the spikes in §12 return data. Filling them now would be guesswork.

---

## 3. Cost & TCO — 20%

**Current (Buy).** Managed Vertex Memory Bank is billed on API usage plus **provider-side structured-profile generation**, which runs an LLM to synthesize profiles from ingested events — a real, recurring token cost that is *not measured anywhere in the repo today*. Each `resolve` performs, per readable schema grant, two managed calls (`retrieve_profiles` + `retrieve`); each write performs `retrieve` + `create`. Fixed infra run-rate = Control Plane API (Cloud Run/GKE) + Cloud SQL PostgreSQL; there is **no self-managed memory database**.

**Custom (Build).** Cost shifts from managed per-call + generation fees to **fixed infra run-rate** (vector store + DB + embedding/generation pipeline) plus your own model tokens for generation/dedup. No managed markup, but you carry the always-on infra and the model spend directly.

**Gap.** The decision hinges on numbers we do not have: per-turn token cost of managed profile generation, per-`resolve` retrieval cost at real fan-out, and the two infra run-rates. **⚠ Needs data.**

**Confidence: Low.** Structure is known; unit economics are not.

---

## 4. Maintainability & Complexity — 20%

**Current (Buy).** The heavy, stateful work — structured profile generation, storage, scaling, retrieval, provider-side dedup — is operated by Google. The team's maintained surface is the Control Plane API + PostgreSQL + a thin `MemoryStore` SDK adapter. **Caveat, with direct evidence:** the managed SDK shipped a breaking change (`agentplatform` 1.x → 2.x: `agent_engines` → `memory_banks` / `runtimes`) that required a code fix to keep the service booting and provisioning working. Managed API version churn is a real, ongoing maintenance tax.

**Custom (Build).** You own everything: an MCP server, DB operations, the embedding/generation pipeline and its prompts, dedup/conflict logic, scaling, and upgrades. Substantially larger operational and on-call surface, and you own correctness of memory generation.

**Gap.** Managed clearly lowers day-to-day maintenance; the cost is exposure to vendor API churn (evidenced above) and less control. Build maximizes control at a large, permanent ops cost.

**Leaning: Buy. Confidence: Med–High.**

---

## 5. Feature Parity & Data Modeling — 15%

**Current (Buy).**
- **Conflict resolution — parity, arguably a strength.** Deterministic resolution is implemented **in the Control Plane**, not delegated to the store: a strategy chain of source priority → domain priority → explicit-over-inferred → recency → confidence, with a minimum-confidence gate. This is Build-independent and already ours.
- **Structured + unstructured.** Memory Bank stores schema-driven structured profiles (via `context_spec.structured_memory_configs`) and unstructured memories.
- **Known limitation — no field-level structured update.** The managed API has no direct structured-profile field update, so explicit preferences are written as typed exact-scope **overlay memories** and merged at read time. It works, but it is a workaround.
- **Ontology.** The model is domain → schema → attribute. It is **not** a rich ontology / knowledge graph.
- **Dedup.** Partly handled by the explicit-overlay merge; the provider also dedups during generation — exact managed dedup semantics **⚠ not confirmed**.
- **Extraction model — configurable, Google-only.** The Gemini model Memory Bank uses to extract/consolidate memories is now config-driven (`MEMORY_BANK_GENERATION_MODEL`, applied via the provisioner's `generation_config.model`). You can select any Google/Gemini tier (e.g. `gemini-2.5-flash` → `gemini-2.5-pro`), but Memory Bank accepts **Google-published models only** — no custom, tuned, or third-party extraction model. A non-Google extraction model is achievable **only on the Build path**. (Source: Google "Set up Memory Bank" — the generation-config `model` field, format `projects/.../publishers/google/models/{model}`.)

**Custom (Build).** Could implement a richer ontology/graph model, native field-level updates, and bespoke dedup/conflict logic — more modeling flexibility.

**Gap.** Conflict resolution favors staying (already built). Ontology and native field-level updates favor Build if those are hard requirements. Dedup semantics need confirmation.

**Leaning: Mixed. Confidence: Med.**

---

## 6. Resiliency & DR — 10%  *(key swing factor)*

**Current (Buy).** The implementation runs Vertex Memory Bank in a **single region** (`us-central1` in config). **Active/Active multi-region (East/Central) failover and cross-region replication of the memory data are not configured or validated in the repo.** The Control Plane API and Cloud SQL can be made multi-region, but the memory *data* lives in one Vertex region, and Memory Bank's multi-region/replication capabilities are a managed-service property we have **⚠ not confirmed** with Google.

**Custom (Build).** A self-hosted store (multi-region Postgres/Spanner/vector DB) can be architected Active/Active with cross-region replication under your control — a genuine Build advantage **if** Vertex cannot meet the East/Central Active/Active requirement.

**Gap.** This is potentially the decisive area despite its 10% weight: if Active/Active East/Central is a hard business requirement and the managed service cannot satisfy it, that alone can force Build. **⚠ Needs data: confirm Vertex Memory Bank multi-region / DR guarantees from Google.**

**Leaning: Build if Active/Active is hard-required, else Buy. Confidence: Low until vendor DR is confirmed.**

---

## 7. Performance & Scalability — 10%

**Current (Buy).** Each `resolve` issues N × (`retrieve_profiles` + `retrieve`) managed calls (one pair per readable grant) plus in-process resolution — i.e., multiple sequential network hops to a managed service on the read path. Writes issue `retrieve` + `create`. The effective snapshot is cached in ADK session state, which mitigates repeat reads. **Vertex Memory Bank throughput/latency limits at the stated 100k-concurrent target are ⚠ not documented in the repo and not load-tested.** (Also note: the API's in-process metrics reset per instance and are not aggregated — not a scalability blocker, but observability needs work before a load test is meaningful.)

**Custom (Build).** Latency can be tuned via co-location and caching, and scaled to self-imposed limits — an advantage only if managed quotas/latency prove insufficient.

**Gap.** Multiple sequential managed calls per resolve is a latency concern worth measuring; 100k concurrency vs Vertex quotas is unknown. **⚠ Needs data: load/scale spike.**

**Leaning: Neutral. Confidence: Low.**

---

## 8. Agent Integration — 10%

**Current (Buy).** Agents integrate via the Control Plane **runtime REST API** (`/api/v1/runtime`); the resolved snapshot is injected into ADK session state. Verified: **there is no MCP layer today** — the reference agent has zero provider-SDK imports (CI-enforced) and calls the API over HTTP. Integration is clean for ADK; other agent frameworks/hosts need a bespoke client. Agent init payload = the bounded effective snapshot (readable schemas/attributes); managed context-retrieval payload caps are **⚠ not confirmed**.

**Custom (Build).** A custom store fronted by **MCP** gives standardized, model-native tool discovery across heterogeneous agent hosts (Claude, LangGraph, IDE agents, partners) with less per-framework glue. Note: MCP can also be added as a thin adapter **in front of the current REST API** without a full Build — the two are not mutually exclusive.

**Gap.** REST + ADK is sufficient today. If the roadmap needs many non-owned agent hosts, MCP (with or without Build) becomes valuable.

**Leaning: Neutral → Build if heterogeneous hosts are required. Confidence: Med.**

---

## 9. Exit Strategy — 5%

**Current (Buy).** There is real lock-in to the Vertex `agentplatform` SDK for the memory *data*, but two mitigations are already in the architecture and are genuine strengths:
- **PostgreSQL is the system of record** for all configuration and governance (orgs, projects, domains, scopes, schemas, catalog, grants, policies, audit) — fully portable, provider-independent.
- **A `MemoryStore` Protocol abstracts the provider** (mock and Vertex implementations exist), so swapping the memory backend is an architecturally supported operation, not a rewrite.

What remains provider-bound is the exported user **memory data** itself; portability of that data out of Vertex is **⚠ not confirmed** (needs an export/round-trip test).

**Custom (Build).** Full data ownership, no lock-in by definition.

**Gap.** Config/switching cost is already low thanks to the Protocol + PostgreSQL SoR — this materially softens the lock-in argument. The open item is memory-data export.

**Leaning: Buy acceptable. Confidence: Med.**

---

## 10. Governance & Security — 5%

**Current (Buy).** The Control Plane enforces authorization (capabilities, per-agent schema grants, `organization_id + user_id` scope), immutable audit for admin mutations, and deterministic (non-model) resolution. **Gap:** PII masking / redaction at the memory boundary is **not implemented** — a `sensitivity_classification` field exists on preferences but nothing reads or enforces it. Guardrail flags (`confirmation_required`, dynamic-memory policy) exist. Compliance/data-residency is tied to the Vertex region.

**Custom (Build).** A self-hosted store makes native PII masking, redaction, and residency control easier to enforce end to end.

**Gap.** The PII-masking gap exists in *both* options today, but is easier to close in Build (you control the store). `sensitivity_classification` being unused is a concrete, fixable gap regardless of the decision.

**Leaning: Slight Build. Confidence: Med.**

---

## 11. Migration Path — 5%

**Current (Buy).** Guided setup + activation provisions schemas and applies them to Memory Bank. **No tooling exists to migrate existing KSA Session Service data** into Memory Bank — it would require mapping KSA session data → domains/schemas/preferences and ingesting via the runtime API (`memory/events` / `preferences`). Effort depends on KSA data shape, which is **⚠ not known** here.

**Custom (Build).** Migrating into a store you control may allow simpler bulk import against a schema you define.

**Gap.** No migration tooling exists for either path today; effort is unknown until the KSA data model is examined. **⚠ Needs data: KSA migration spike.**

**Leaning: Neutral. Confidence: Low.**

---

## 12. Recommended spikes (to complete the matrix)

| Spike | Feeds area(s) | Question to answer |
|---|---|---|
| **Cost spike** | 1 | Measure per-turn generation tokens, per-`resolve` retrieval cost at real fan-out, and both infra run-rates. |
| **DR / multi-region confirmation** | 4 | Confirm from Google whether Memory Bank supports Active/Active East/Central + cross-region replication; if not, quantify Build DR effort. |
| **Load / scale spike** | 5 | Measure read/write latency and behavior toward 100k concurrent against Vertex quotas. |
| **Data-model / ontology spike** | 3 | Decide whether domain/schema/attribute is sufficient or a true ontology/graph + native field-level updates are required. |
| **PII / compliance review** | 8, 10 | Define masking/redaction requirements and whether managed residency satisfies compliance. |
| **KSA migration spike** | 9, 11 | Inspect KSA Session Service data shape and estimate migration effort into each option. |
| **Exit / portability test** | 7 | Round-trip export of Memory Bank data to confirm real portability. |

---

## 13. Summary read (pending spikes)

- **Buy is favored on the two highest-weight operational axes it can be judged on today** — Maintainability (with the caveat of vendor API churn, already felt in the 1.x→2.x migration) and, structurally, the governance/resolution machinery that is *already ours* regardless of store.
- **Build's strongest cases are Resiliency/DR (Active/Active) and rich data modeling/ontology** — but the DR case is only decisive if Active/Active East/Central is a confirmed hard requirement the managed service cannot meet. That single confirmation (Spike 2) may drive the whole decision.
- **The lock-in argument for Build is weaker than it first appears**, because the `MemoryStore` Protocol + PostgreSQL system of record already make the config portable and the backend swappable.
- **Do not finalize the weighted score until the Cost, DR, and Load spikes return data** — those three sit on 40% of the total weight and are currently unmeasured.

*Prepared as an implementation-grounded baseline; all ⚠ rows require the spikes in §12 before scoring.*
