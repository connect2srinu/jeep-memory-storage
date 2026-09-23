# ADR-0001: Managed Memory Bank vs. Custom Unified Memory Layer

- **Status:** Proposed — the managed-first path is implemented; acceptance waits on the open gates below
- **Date:** 2026-08-28 (gate status updated 2026-09-23)
- **Decision owners:** Agent Platform Architecture and Engineering
- **Scope:** Canonical shared-memory engine and its enterprise governance boundary

## 1. Decision and context

We must decide whether to continue with the managed Google Memory Bank architecture or replace it with
the proposed Unified Memory Layer (UML): a custom Memory Gateway, Pub/Sub writer, LLM
extraction/consolidation pipeline, and PostgreSQL memory engine.

This is not simply "Memory Bank vs. PostgreSQL." Both options need the enterprise control plane for
organizations, projects, agents, schemas, grants, approvals, resolution, households, consent, purpose,
retention, audit, and observability. The real choice is:

1. **Managed engine:** Google Memory Bank as the storage engine behind the Control Plane API.
2. **Custom engine:** own extraction, consolidation, conflict handling, revisions, storage, scaling,
   privacy processing, and recovery in the UML.
3. **Tiered hybrid:** the managed engine by default, with a custom or separately isolated tier only for
   requirements the managed topology can't meet.

Since this ADR was drafted, the managed path has been built out on `feature/dynamic-household-members`:
the Vertex adapter uses the supported `agentplatform` 2.x surface and was exercised live; household
scopes, runtime member resolution, confirmation turns, a consent ledger, purpose limitation, retention,
and governed deletion are implemented; and Memory Bank's managed generation is deliberately off, so
extraction happens in the agent's own LLM call and every value is validated by the control plane before
it is stored. Details are in
[Current Memory Bank Architecture Validation](../current-memory-bank-architecture-validation.md) and
[Memory Bank Assumption Validation](../memory-bank-assumption-validation.md).

## 2. One-page architecture comparison

```text
MANAGED MEMORY BANK (built)                      CUSTOM UML (proposal)

Business Agent                                   Business Agent
  extracts in its own LLM call                         |
      |                                                v
      v                                          Memory Gateway
Control Plane API                                  identity/access matrix
  identity/capabilities/purpose                    trusted domain mapping
  org/project/schema grants                        read resolver
  scopes + households + consent                    audit
  sensitivity gate + resolver                          |
  approvals + audit + retention                        v
      |                                          PostgreSQL per-LOB tables
      v                                            user/domain JSONB ontology
Google Memory Bank                                 audit/version tables
  typed facts per exact scope                      custom OCC/merge logic
  profiles + retrieval                                 ^
  revisions + rollback                                 |
  (managed generation off)                          Pub/Sub
                                                       ^
                                                Platform Memory Writer
                                                  privacy/PII processing
                                                  LLM extraction/classification
                                                  dedupe/conflict/consolidation
```

| Dimension | Managed Memory Bank + control plane | Custom UML |
|---|---|---|
| Differentiator | Managed storage, retrieval, revisions, scaling; governance already built | Full ownership, physical per-LOB SQL isolation, custom algorithms, direct SQL |
| Reuse | Keeps the API, governance model, resolver, console, and ADK agents | Rebuilds the memory engine and its integration paths |
| Primary risk | Provider/SDK dependency, quotas, logical-isolation correctness | Distributed-system correctness, extraction quality, SQL scaling, privacy, migrations, staffing |
| Best fit | Default enterprise preference/profile memory | A regulated or specialized domain with proven requirements the managed topology can't meet |

The UML proposal still doesn't define cross-domain conflict semantics, owner override rules, or
transactional delivery from producer to Pub/Sub; these remain open questions, not credited benefits.

## 3. Capability summary

| Capability | Managed option | Custom UML | Significance |
|---|---|---|---|
| Gateway, capabilities, grants, purpose | Implemented; admin read isolation open | Build or reuse | Keep the control plane either way. |
| Structured profiles, scopes, lazy creation | Implemented (member, household, household-member) | Build | Managed is ahead. |
| Household model and health consent | Implemented in the control plane | Build | Independent of the store. |
| Extraction | Agent-side, validated centrally; provider generation off | Build and evaluate | No duplicate engineering needed. |
| Deterministic resolution | Implemented; global schema precedence open | Build | Fix the existing resolver. |
| Deletion and retention | Implemented | Build | Managed is ahead. |
| Revisions and rollback | Provider capability; no operator workflow | Build | Material managed advantage. |
| Physical per-LOB isolation | Separate banks/projects, or logical scope/IAM | Native | UML advantage only if physical SQL ownership is mandatory. |
| Durable idempotency / retry / reconciliation | Missing | Proposed, unspecified end to end | Needed either way. |
| Direct SQL analytics and portability | Export needed; governance metadata already in PostgreSQL | Native | Possible UML justification. |
| Implementation evidence | Built and live-validated in a local harness | Proposal only | Favors managed. |

Full comparison: [Capability Matrix](../memory-bank-vs-uml-capability-matrix.md).

## 4. Cost, operations, and development

With managed generation off, the repository's access pattern is about 13 reads and 1 write per session
that saves a preference (three readable schemas): roughly **$0.45 per 1 million sessions** or **$13.60
per 30 million** in Memory Bank operation charges at published rates, excluding storage and shared
infrastructure. The binding constraint is the per-minute quota, not cost.

A custom UML adds Pub/Sub, writer compute, a larger production PostgreSQL footprint, replay tooling, and
direct model calls: illustrative extraction at 1,000 input / 200 output Gemini 2.5 Flash Lite tokens
costs about **$180 per 1 million events** or **$5,400 per 30 million**, before retries, classification,
and embeddings — and ten times that if every message rather than every preference is sent to it.

| Dimension | Managed option | Custom UML |
|---|---|---|
| Fixed infrastructure | Existing control plane and governance database | Same plus gateway/writer capacity and memory database growth |
| Variable cost | Memory Bank operations and storage | Pub/Sub, model calls, SQL/worker compute, storage, replay |
| Operations | Provider engine plus application runbooks | Own the combined SLO of gateway, queue, workers, SQL, models |
| Development | Close the remaining gates | Build and validate an entire engine plus the same governance work |
| Three-year TCO driver | Provider usage and a smaller platform team | Engineering, evaluation, on-call, migrations, incident recovery |

Assumptions and formulas: [Cost, Operations, and Development Analysis](../memory-bank-vs-uml-cost-analysis.md).

## 5. Recommendation and consequences

### Decision

Adopt a **tiered managed-first architecture**:

1. The Control Plane API is the only business-agent memory boundary.
2. Google Memory Bank is the default storage engine; its managed generation stays off.
3. Adopt the useful UML patterns inside the control plane: explicit governed writes, sensitivity
   screening, consent, lineage logging (done); durable idempotency/outbox, stable request identity, and
   reconciliation (open).
4. Use separate GCP projects / Memory Banks, IAM Conditions, CMEK, and residency controls where stronger
   managed isolation is required.
5. Allow a custom PostgreSQL tier only for a domain with an approved regulatory, direct-query,
   portability, latency, or custom-processing requirement that a measured managed design can't meet.

### Positive consequences

- Preserves the implemented governance, household, resolver, console, and ADK investment.
- Reuses managed storage, retrieval, revision, and scaling.
- Shortens the path to production and keeps the operational surface small.
- Keeps a governed escape hatch for hard-isolation or specialized domains.

### Negative consequences

- Dependency on Google APIs, SDK compatibility, pricing, quotas, and regions.
- Logical multi-tenant isolation must be proven at the application and IAM layers.
- A tiered model adds complexity if a custom tier is ever introduced.
- Direct SQL over stored memory values needs an export or analytics path.

### Acceptance gates

| Gate | Status 2026-09-23 |
|---|---|
| Correct and pin the Vertex SDK integration | ✅ Correct and live-validated; 🟡 version range still broad |
| Prove organization/project isolation and read-only cross-organization sharing | 🟡 Runtime isolation and sharing proven in tests; admin list/hierarchy reads not yet membership-filtered |
| Execute global schema precedence; restrict the UI to supported scopes | ❌ Precedence not executed; store/custom scopes still offered |
| Durable idempotency, retry/reconciliation, stable request identity | ❌ Open |
| Least-privilege Memory Bank roles and scope IAM Conditions | ❌ Open |
| Live validation of profiles, deletion, retention, quotas, latency, failure behavior | 🟡 Profiles, writes, and deletion validated live in a local harness; landing-zone deploy, quota, and failure tests open |
| Tenant-level usage, storage, latency, and cost telemetry | ❌ Open |
| Revisit if a bounded UML prototype shows a requirement managed can't meet | Not triggered; no UML prototype has been built |
