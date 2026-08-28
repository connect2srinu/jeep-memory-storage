# ADR-0001: Managed Memory Bank vs. Custom Unified Memory Layer

- **Status:** Proposed — production gates must pass before acceptance
- **Date:** 2026-08-28
- **Decision owners:** Agent Platform Architecture and Engineering
- **Scope:** Canonical shared-memory engine and its enterprise governance boundary

## 1. Decision and context

We must decide whether to continue with the repository's managed Google Memory Bank architecture or replace it with the proposed Unified Memory Layer (UML): a custom Memory Gateway, Pub/Sub writer, LLM extraction/consolidation pipeline, and PostgreSQL memory engine.

This is not simply “Memory Bank vs. PostgreSQL.” Both options require the existing enterprise control plane for organizations, projects, agents, schemas, grants, approvals, resolution policies, audit, budgets, and observability. The real choice is:

1. **Managed engine:** keep Google Memory Bank as the canonical profile/generation engine behind the existing Control Plane API.
2. **Custom engine:** own extraction, consolidation, conflict handling, revisions, storage, scaling, privacy processing, and recovery in the UML.
3. **Tiered hybrid:** use the managed engine by default and permit a custom or separately isolated tier only for requirements the managed topology cannot meet.

Repository validation shows that the current control-plane and ADK patterns are substantial and reusable. It also identified production blockers: the Vertex SDK adapter targets the wrong public surface, organization read isolation is incomplete, global schema precedence is not executed, unsupported scope types are exposed, and write idempotency/recovery is incomplete. Those findings are detailed in [Current Memory Bank Architecture Validation](../current-memory-bank-architecture-validation.md) and [Memory Bank Assumption Validation](../memory-bank-assumption-validation.md).

## 2. One-page architecture comparison

```text
MANAGED MEMORY BANK                              CUSTOM UML

Business Agent                                  Business Agent
      |                                               |
      v                                               v
Control Plane API                               Memory Gateway
  identity/capabilities                           identity/access matrix
  org/project/schema grants                      trusted domain mapping
  scope + policy resolver                        read resolver
  approvals + audit                              audit
      |                                               |
      v                                               v
Google Memory Bank                              PostgreSQL per-LOB tables
  profiles + scope                                user/domain JSONB ontology
  extraction + consolidation                     audit/version tables
  async event ingestion                          custom OCC/merge logic
  revisions + rollback                                ^
  managed retrieval                                   |
                                                   Pub/Sub
                                                      ^
                                                      |
                                              Platform Memory Writer
                                                privacy/PII processing
                                                LLM extraction/classification
                                                dedupe/conflict/consolidation
```

| Dimension | Managed Memory Bank + control plane | Custom UML |
|---|---|---|
| Differentiator | Managed profiles, generation, revisions, retrieval, and scaling | Full platform ownership, physical per-LOB SQL isolation, custom algorithms, direct SQL portability |
| Reuse | Preserves the current API, governance model, resolver, UI, and ADK integration | Can reuse governance concepts, but replaces/rebuilds the memory engine and integration paths |
| Primary risk | Provider/SDK dependency, logical-isolation correctness, quotas, and product constraints | Distributed-system correctness, extraction quality, SQL scaling, privacy, migrations, recovery, and staffing |
| Best fit | Default enterprise preference/profile memory | A regulated or specialized domain with proven requirements unmet by managed topology |

The UML proposal does not yet define complete cross-domain conflict semantics, owner override rules, or transactional delivery from the producer to Pub/Sub. These remain `UML_PROPOSAL_ASSUMPTION / OPEN QUESTION` rather than benefits credited to the option.

## 3. Capability matrix

| Capability | Managed option | Custom UML | Decision significance |
|---|---|---|---|
| Platform gateway, agent capabilities, org/project grants | Implemented, with isolation gaps to fix | Must build or reuse | Keep the current control plane in either option. |
| Structured profiles and lazy creation | Managed | Must build | Managed option is ahead. |
| Extraction, consolidation, event ingestion | Managed | Must build and evaluate | Avoid duplicate engineering without a proven gap. |
| Deterministic enterprise resolution | Implemented, with schema-priority defect | Must build | Fix the existing resolver. |
| Revisions and rollback | Managed; operator workflow incomplete | Must build | Material managed advantage. |
| Physical per-LOB storage isolation | Separate managed resources or logical scope/IAM; not per-table | Native proposal characteristic | UML advantage only when physical SQL ownership is mandatory. |
| Durable idempotency, retry, reconciliation | Incomplete | Proposed but not specified end to end | Required in both designs. |
| Custom privacy/preprocessing pipeline | Limited by provider integration points | Full control | Potential UML/hybrid justification. |
| Direct SQL analytics and portability | Export/integration required | Native, subject to governance | Potential UML justification. |
| Semantic/episodic/vector/graph roadmap | Managed capabilities vary | Future proposal | Not part of the initial decision. |
| Production implementation evidence | Control plane is implemented; live provider path is blocked | Proposal only | Favors repairing and validating managed first. |

The complete comparison is in [Memory Bank vs. UML Capability Matrix](../memory-bank-vs-uml-capability-matrix.md).

## 4. Cost, operations, and development comparison

Current published pricing makes Memory Bank API-operation charges small in the illustrative repository access pattern: at three readable schemas, approximately 13 reads and 3 writes per unit produce about **$0.62 per 1 million units** or **$18.70 per 30 million units**, excluding storage, generation/embedding tokens, and shared application infrastructure. Google states that billing under this Memory Bank structure begins September 1, 2026.

A custom UML adds Pub/Sub, writer compute, a larger production PostgreSQL footprint, backup/replay tooling, and direct model calls. Pub/Sub throughput is inexpensive at the modeled payload, but illustrative custom extraction using 1,000 input and 200 output Gemini 2.5 Flash Lite tokens costs about **$180 per 1 million events** or **$5,400 per 30 million events** before retries, classification, embeddings, and conflict calls. Memory Bank generation tokens must also be measured; this comparison does not assume its token envelope.

| Dimension | Managed option | Custom UML |
|---|---|---|
| Fixed infrastructure | Existing control plane/governance database | Existing stack plus gateway/writer capacity and production memory database growth |
| Variable cost | Managed operations, storage/revisions, generation and embeddings | Pub/Sub, model calls, SQL/worker compute, storage/audit/backups, replay |
| Operations | Provider engine plus application runbooks | Own combined SLO for gateway, queue, workers, SQL, models, migrations, and recovery |
| Development | Repair adapter and production gaps; add live tests | Build and validate an entire memory engine plus the same governance work |
| Three-year TCO driver | Token use, provider usage, and a smaller platform team | Engineering, evaluation, on-call, migrations, and incident recovery dominate service prices |

Dollar values are illustrative, undiscounted, and require validation with billing telemetry. Assumptions, formulas, exclusions, and official pricing links are in [Cost, Operations, and Development Analysis](../memory-bank-vs-uml-cost-analysis.md).

## 5. Recommendation and consequences

### Decision

Adopt a **tiered managed-first architecture**:

1. Keep the existing Control Plane API as the only business-agent memory boundary.
2. Keep Google Memory Bank as the default canonical profile and generation engine.
3. Adopt selected UML patterns inside the control plane: stable event IDs, durable idempotency/outbox where justified, stronger preprocessing/privacy checks, explicit conflict contracts, richer lineage, and reconciliation.
4. Prefer separate GCP projects/Memory Banks, scope-aware IAM Conditions, CMEK, and residency controls when stronger managed isolation is required.
5. Allow a custom PostgreSQL UML tier only for a domain with an approved regulatory, direct-query, portability, latency, or custom-processing requirement that a measured managed design cannot satisfy.

Do not begin a wholesale UML replacement until the managed production gates are repaired and both options are evaluated on the same representative dataset and SLOs.

### Positive consequences

- Preserves the implemented governance, approval, resolver, UI, and ADK investment.
- Reuses managed extraction, consolidation, revision, retrieval, and scaling capabilities.
- Shortens the path to production evidence and reduces the platform's operational surface.
- Retains a governed escape hatch for hard-isolation or specialized domains.
- Focuses engineering on enterprise differentiation: authorization, policy, audit, privacy, observability, and developer experience.

### Negative consequences

- Creates dependency on Google APIs, SDK compatibility, pricing, quotas, and supported regions.
- Requires disciplined provider abstraction and live integration tests.
- Logical multi-tenant isolation must be proven at both application and IAM layers; some organizations may require separate resources.
- A tiered model adds governance and migration complexity if a custom tier is later introduced.
- Direct SQL access to canonical managed memories is unavailable without an export or curated analytics path.

### Mandatory acceptance gates

- Correct and pin the supported Vertex Agent Platform/Memory Bank SDK integration.
- Prove organization/project isolation and approved cross-organization read-only sharing with live tests.
- Execute global schema precedence and restrict the UI to runtime-supported scopes.
- Add durable idempotency, retry/reconciliation, and stable event identity.
- Apply least-privilege Memory Bank roles and scope IAM Conditions.
- Validate live profiles, ingestion, revisions, rollback, deletion, retention, quotas, latency, and failure behavior.
- Establish tenant-level usage, token, storage, latency, and cost telemetry.
- Revisit this ADR if a bounded UML prototype demonstrates a material requirement the managed topology cannot meet.
