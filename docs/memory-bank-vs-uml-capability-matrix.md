# Memory Bank vs. Unified Memory Layer Capability Matrix

## Scope

This matrix compares:

- **Current managed architecture:** the repository's control plane plus Google Memory Bank, as
  implemented on `feature/dynamic-household-members` (re-checked 2026-09-23).
- **Proposed UML:** the Unified Memory Layer proposal — a custom gateway, Pub/Sub writer, LLM
  extraction/consolidation pipeline, and PostgreSQL memory store.

The UML is a proposal, not implemented behavior. Where it doesn't specify behavior, the matrix says
`UML_PROPOSAL_ASSUMPTION` or `OPEN QUESTION` rather than inferring it.

Legend: **Yes** — implemented or inherent · **Partial** — with a gap · **Build** — the platform team must
build and operate it · **Open** — not specified enough to assess · **Off by design** — available but
deliberately unused.

## Capability matrix

| Capability | Managed Memory Bank + current control plane | Proposed custom UML | Assessment |
|---|---|---|---|
| Platform-owned agent API boundary | Yes | Yes | Both keep storage details out of business agents. |
| Agent identity and capability validation | Yes | Build in gateway | The control plane is reusable in either option. |
| Organization/project/schema grants | Yes; admin list reads not yet membership-filtered | Build | Existing governance is more mature than the proposal. |
| Cross-organization read approval | Yes, whole-schema grants | Build | Neither option has per-attribute grants yet. |
| Owner-only writes | Yes | UML_PROPOSAL_ASSUMPTION | The UML must define write authority explicitly. |
| Purpose limitation | Yes: agent purpose vs schema `allowed_purposes`; advertising denied for per-member and health data | Build | New since the first comparison. |
| Physical per-LOB data isolation | No; logical scope/IAM isolation unless separate banks/projects | Yes, per-LOB tables | Separate managed resources may meet stronger boundaries without a custom engine. |
| Structured scopes | Yes: member, household-shared, household-member | Build | Store and custom scopes are offered in the wizard but not supported. |
| Household / family model | Yes: login-rooted households, runtime member resolution, aliases, merge/move/rename | Build | Entirely in the control plane; works with either store. |
| Structured profile schema | Yes, versioned; new versions live without restart | Yes, JSONB ontology | The UML owns its schema compiler and migrations. |
| Lazy profile creation | Yes | Build | |
| Session-boundary retrieval | Yes | Yes | Implemented in both ADK agents. |
| Low-latency retrieval | Managed; quota is the ceiling | Depends on SQL/index/cache design | Both need benchmarks at target load. |
| Natural-language extraction | Off by design; the agent's own LLM extracts, the platform validates | Build an LLM extraction service | See the extraction slide in the build-vs-buy deck. |
| Event-stream ingestion | Off by design | Build Pub/Sub pipeline and worker | Useful only if replay/backpressure guarantees are required. |
| Consolidation / deduplication | Newest write per field wins; household name matching prevents duplicate people | Build | |
| Source / confidence metadata | Yes: source, sensitivity, confidence, provenance in the snapshot | Build and persist | |
| Deterministic preference resolution | Yes; global schema precedence not executed | Build | Fix the existing resolver. |
| Sensitivity screening before persistence | Yes: restricted blocked, sensitive requires user-directed | Proposed custom stage | Semantic inference detection is missing in both. |
| Health-data consent | Yes: confirmation turn plus consent ledger; adult proxies refused | Build | |
| Immutable revisions and rollback | Provider capability; no operator workflow | Build | Managed option avoids a complex subsystem. |
| Optimistic concurrency control | No | Proposed | The managed option still needs idempotency. |
| Durable outbox / retry / DLQ | No | Proposed; producer semantics unspecified | Both need an end-to-end failure contract. |
| User deletion / retention | Yes: forget (member/household cascade), single value, purge, retention sweep, consent withdrawal | Build | Legal hold and backup deletion open in both. |
| Fine-grained provider IAM | Available (Memory Bank roles, IAM Conditions); not configured | Database/table/service IAM | |
| Control-plane audit | Yes | Build or reuse | |
| Field-level lineage | Partial: write/delete logs with correlation IDs; provider revisions not linked | Build | |
| Semantic / episodic retrieval | Managed capabilities, unused | Future | Not part of the decision. |
| Data residency / CMEK / VPC-SC | Managed platform options, subject to region/product | Build with GCP services | Validate per regulatory need. |
| Autoscaling engine | Managed | Build and capacity-plan | |
| Portable storage / direct SQL | Lower; export needed | Higher | UML wins where direct SQL is strategic. PostgreSQL already holds all governance metadata. |
| Multi-tenant noisy-neighbor control | Provider quotas plus per-LOB banks | Build | Both need quota and budget attribution. |
| Implementation maturity | Control plane, console, approvals, resolver, households, consent, ADK agents; live-validated adapter | Proposal only | Replacing it would discard working layers. |

## Functional overlap

A custom UML would re-create capabilities Memory Bank already has: schema-driven profiles, extraction,
consolidation, asynchronous ingestion, metadata, revisions and rollback, scope-aware access control, and
managed retrieval and scaling. Several of those are deliberately unused today, which narrows the overlap
the platform actually depends on to storage, retrieval, deletion, and scaling.

The UML's real differentiators are ownership of the whole engine, physical per-LOB tables, custom
preprocessing, direct SQL access, and freedom to add episodic/vector/graph subsystems.

## Gaps independent of engine choice

Needed whichever store holds canonical memory:

1. Organization membership enforcement on every admin read.
2. One supported scope contract across UI, runtime, and provider (hide store/custom scopes).
3. Per-attribute grants, if approvals must be narrower than a whole schema.
4. Durable idempotency, retries, correlation, and reconciliation.
5. Legal hold and backup deletion.
6. Resolution correctness (global schema precedence) and value validation against the catalog.
7. Per-tenant observability, quotas, and budget attribution.

Closed since the first comparison: household scopes, explicit cross-domain ownership rules, deletion and
retention, purpose limitation, and the schema-version contract.

## Capability conclusion

For the current requirements, managed Memory Bank plus the control plane provides the broader
implemented capability set and the shorter path to production. A custom UML is justified only when a
requirement demands physical SQL ownership or processing that provider scopes, IAM Conditions, separate
managed resources, or the existing control plane can't meet. The control plane already absorbs the
UML's governance ideas (explicit writes, sensitivity gate, consent, lineage logging) independent of the
store.

## Related documents

- [Current Memory Bank Architecture Validation](current-memory-bank-architecture-validation.md)
- [Memory Bank Assumption Validation](memory-bank-assumption-validation.md)
- [Cost, Operations, and Development Analysis](memory-bank-vs-uml-cost-analysis.md)
- [ADR-0001](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md)
