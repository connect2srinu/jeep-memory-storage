# Memory Layer — Build vs Buy Gap Analysis

**Purpose:** Compare a custom-built memory layer (custom DB + MCP) against the current managed Memory
Bank implementation, across the team's agreed Areas of Assessment, to support the Build vs Buy decision.
**Status:** Draft for team review; re-checked against `feature/dynamic-household-members` on 2026-09-23.
Rows marked ⚠ still need data from the spikes in §12.
**Baseline:** GEAP Control Plane — FastAPI control plane, PostgreSQL system of record, Vertex Memory Bank
(`agentplatform` 2.x) as the managed store, deterministic in-process resolver.
**Framework:** The 9 weighted areas and weights were defined by the team (business directives: Cost,
Maintainability; technical requirements: DR, Scale, Exit, Ontology).

> **Terminology.** "Buy / Managed" = the current implementation: the Control Plane API wrapping Vertex
> Memory Bank. "Build / Custom" = replace the managed store with a self-hosted DB + custom memory logic,
> exposed to agents via MCP. The Control Plane API, PostgreSQL system of record, and resolver stay in
> both options; only the **memory store** changes.

---

## 1. How to read this document

- **Current (Buy)** = what the implementation does today, verifiable in code.
- **Custom (Build)** = what a self-hosted solution would entail.
- **Leaning** = which option the evidence favors, and why. **Confidence** = High / Med / Low.
- **⚠ Needs data** = not yet measured; tracked as a spike in §12.

---

## 2. Weighted assessment summary

| # | Area | Weight | Leaning | Confidence | Spike needed |
|---|---|---:|---|---|---|
| 1 | Cost & TCO | 20% | Leaning **Buy** | Low–Med | ✅ landing-zone cost run |
| 2 | Maintainability & Complexity | 20% | **Buy** | Med–High | — |
| 3 | Feature Parity & Data Modeling | 15% | Mixed (Buy: resolution, households, deletion · Build: ontology, native field updates) | Med | ✅ data-model spike |
| 4 | Resiliency & DR | 10% | **Build** *if Active/Active is hard-required* | Low | ✅ DR confirmation |
| 5 | Performance & Scalability | 10% | Neutral | Low–Med | ✅ load spike |
| 6 | Agent Integration | 10% | Neutral → Build *if heterogeneous hosts* | Med | — |
| 7 | Exit Strategy | 5% | **Buy acceptable** | Med | ✅ export test |
| 8 | Governance & Security | 5% | **Neutral** (was slight Build) | Med | ✅ PII/compliance review |
| 9 | Migration Path | 5% | Neutral | Low | ✅ KSA migration spike |

**Scores are still left blank.** Cost, DR, Scale, and Migration (45% of the weight) can't be scored
honestly until their spikes return data.

---

## 3. Cost & TCO — 20%

**Current (Buy).** Managed generation is **off**, so there are no Memory Bank generation or embedding
token charges, and extraction rides on the agent's existing LLM call (no extra model call). What remains
is per-operation billing: each resolve makes two calls per readable schema (`retrieve_profiles` +
`retrieve`); each write makes one read and one `create`. A session that saves one preference with three
readable schemas is about 13 reads and 1 write — roughly $0.45 per million sessions at published rates
(see the [cost analysis](memory-bank-vs-uml-cost-analysis.md)). Fixed run-rate is the Control Plane API
plus Cloud SQL; there is no self-managed memory database.

**Custom (Build).** Fixed infra (DB, pipeline, workers) plus your own model tokens for any extraction or
dedup you add.

**Gap.** The per-operation economics are now small and known in structure; the real numbers still
missing are billed usage in the target project and the infra run-rates. `scripts/memory_load_test.py`
produces the measurement once deployed. **⚠ Needs data.**

**Leaning: Buy (operations are cheap; engineering TCO favors managed). Confidence: Low–Med.**

---

## 4. Maintainability & Complexity — 20%

**Current (Buy).** Google operates storage, scaling, and retrieval. The team maintains the Control Plane
API, PostgreSQL, and a thin `MemoryStore` adapter. **Caveat with evidence:** the SDK shipped a breaking
change (`agentplatform` 1.x → 2.x: `agent_engines` → `memory_banks` / `runtimes`) that required an
adapter fix. Vendor API churn is a real, ongoing cost.

**Custom (Build).** You own everything: MCP server, DB operations, extraction pipeline and prompts,
dedup/conflict logic, scaling, upgrades, and on-call.

**Leaning: Buy. Confidence: Med–High.**

---

## 5. Feature Parity & Data Modeling — 15%

**Current (Buy).**
- **Conflict resolution** is implemented in the control plane (source → domain → explicit-over-inferred
  → recency → confidence, with a confidence gate), independent of the store. Global schema precedence
  from the wizard is not yet executed.
- **Scopes and households.** Three scope shapes (member, household-shared, household-member) with
  login-rooted households, runtime member resolution, aliases, merge/move/rename, and a consent ledger —
  all in the control plane, no provider change needed.
- **Versioned schemas.** New versions go live without a restart; stored values survive.
- **No field-level structured update** in the provider: explicit values are stored as typed exact-scope
  facts and overlaid at read time (newest write per field wins). Works, but a workaround.
- **Ontology:** domain → schema → attribute; not a knowledge graph.
- **Extraction model:** irrelevant while managed generation is off (it is Gemini-only if ever used).

**Custom (Build).** Richer ontology/graph, native field-level updates, bespoke dedup and conflict logic.

**Leaning: Mixed. Confidence: Med.** Ontology and native field updates favor Build only if they are hard
requirements.

---

## 6. Resiliency & DR — 10% *(key swing factor)*

**Current (Buy).** Memory Bank runs in a **single region** (`us-central1`). Active/Active multi-region
and cross-region replication of memory data are not configured or confirmed with Google. The Control
Plane API and Cloud SQL can be made multi-region; the memory data lives in one Vertex region.

**Custom (Build).** A self-hosted store can be Active/Active under your control.

**Gap.** If Active/Active East/Central is a hard requirement the managed service can't meet, that alone
can force Build. **⚠ Needs data: Google's Memory Bank DR guarantees.**

**Leaning: Build if Active/Active is hard-required, else Buy. Confidence: Low.**

---

## 7. Performance & Scalability — 10%

**Current (Buy).** The binding limit is the Memory Bank **per-minute quota** (reported in the build-vs-buy
deck as 300 reads and 100 writes per minute per project and region by default, with a larger raise
discussed with Google). Mitigations in the code: resolve once per session and cache; per-member schemas
read only when a member is named; per-line-of-business banks possible. Each resolve still makes two
sequential managed calls per readable schema. Provider `429` currently surfaces as HTTP 500, not a
retryable `503`. Latency at the 100k-concurrent target is **⚠ not load-tested**.

**Custom (Build).** Tunable latency via co-location and caching, limited by your own capacity.

**Leaning: Neutral. Confidence: Low–Med.**

---

## 8. Agent Integration — 10%

**Current (Buy).** Agents call the Control Plane **REST API** (`/api/v1/runtime`); the snapshot is
injected into ADK session state. Two reference agents exist (memory-agent with household tools, and a
minimal reference-agent), neither importing a provider SDK. There is **no MCP layer**; non-ADK hosts need a
client.

**Custom (Build).** MCP in front of a custom store standardizes tool discovery across heterogeneous hosts.
MCP could equally be a thin adapter in front of the current REST API without a full Build.

**Leaning: Neutral → Build only if many non-ADK hosts are required. Confidence: Med.**

---

## 9. Exit Strategy — 5%

**Current (Buy).** Lock-in is limited to stored memory values:
- **PostgreSQL is the system of record** for all configuration and governance (organizations, projects,
  domains, schemas, catalog, grants, policies, household roster, consent, audit).
- **A `MemoryStore` protocol** abstracts the provider (mock and Vertex implementations).

Portability of the stored values out of Vertex (a `list`-based export) is **⚠ not tested**.

**Leaning: Buy acceptable. Confidence: Med.**

---

## 10. Governance & Security — 5%

**Current (Buy).** The control plane enforces capabilities, per-agent schema grants, exact scopes, purpose
limitation, immutable admin audit, and deterministic resolution. **Since the first version:** a
sensitivity gate runs on every write (restricted blocked; sensitive only when user-directed; tiers stored
and surfaced), health data needs confirmation and records consent, other adults' health data is refused,
retention limits apply per tier, and deletion covers members, households, single values, purge, and
consent withdrawal. **Still missing:** redaction to the actionable form and semantic inference
detection. Data residency is tied to the Vertex region.

**Custom (Build).** Native masking, redaction, and residency control are easier with your own store.

**Leaning: Neutral (was slight Build — the cited gap, an unused `sensitivity_classification`, is closed).
Confidence: Med.**

---

## 11. Migration Path — 5%

**Current (Buy).** No tooling exists to migrate KSA Session Service data; it would map KSA data to domains,
schemas, and preferences and write through the runtime API. Effort depends on the KSA data shape,
**⚠ not known**.

**Custom (Build).** Bulk import into a schema you define may be simpler.

**Leaning: Neutral. Confidence: Low.**

---

## 12. Spikes

| Spike | Feeds | Question | Status |
|---|---|---|---|
| Cost | 1 | Billed operations and infra run-rate in the target project | Tooling ready (`memory_load_test.py`); needs a landing-zone deployment |
| DR / multi-region | 4 | Does Memory Bank support Active/Active East/Central with replication? | Open — needs Google confirmation |
| Load / scale | 5 | Latency and behavior toward 100k concurrent against quotas | Partially run locally (quota limits observed); full run needs the landing zone and raised quota |
| Data model / ontology | 3 | Is domain/schema/attribute enough, or is a graph + native field updates required? | Open; the household model shows complex relationships fit the current model |
| PII / compliance | 8, 10 | Masking/redaction requirements; residency | Legal review of retention limits, consent wording, and option (b) pending |
| KSA migration | 9, 11 | KSA data shape and migration effort | Open |
| Exit / portability | 7 | Round-trip export of stored values | Open |

---

## 13. Summary read

- **Buy is favored on the axes that can be judged today:** maintainability, and the governance, household,
  and resolution machinery that is already built and independent of the store.
- **With managed generation off, managed operation costs are small**; the cost question is mainly
  engineering TCO, which favors Buy.
- **Build's strongest case is DR (Active/Active)** — decisive only if it is a confirmed hard requirement
  Memory Bank can't meet. That single confirmation may decide the whole matter.
- **Lock-in is weaker than it looks** because configuration lives in PostgreSQL and the store sits
  behind a protocol.
- **Don't finalize the weighted score until the Cost, DR, and Load spikes return data.**
