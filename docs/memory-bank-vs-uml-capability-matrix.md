# Memory Bank vs. Unified Memory Layer Capability Matrix

## Scope

This matrix compares:

- **Current managed architecture:** the repository's enterprise control plane plus Google Memory Bank.
- **Proposed UML:** the supplied Unified Memory Layer proposal with a custom gateway, Pub/Sub writer, LLM extraction/consolidation pipeline, and PostgreSQL memory store.

The UML proposal is an architecture reference, not implemented repository behavior. Unspecified behavior is marked `UML_PROPOSAL_ASSUMPTION` or `OPEN QUESTION` rather than inferred as fact.

Legend:

- **Yes** — inherent or implemented capability.
- **Partial** — available with a gap, custom control, or incomplete validation.
- **Build** — must be designed, implemented, and operated by the platform team.
- **Open** — proposal does not define enough behavior to assess safely.

## Capability matrix

| Capability | Managed Memory Bank + current control plane | Proposed custom UML | Assessment |
|---|---|---|---|
| Platform-owned agent API boundary | Yes | Yes | Both keep provider/storage details out of business agents. |
| Agent identity and capability validation | Yes; runtime API validates registered agent and capabilities | Build in gateway/access matrix | Current control plane is reusable in either option. |
| Organization/project/schema grants | Yes, with API isolation gaps to fix | Build in access matrix | Existing governance is more mature than the proposal detail. |
| Cross-organization read approval | Partial; modeled and runtime-supported after grant | Build | Preserve owner-only writes in either option. |
| Owner-only cross-organization writes | Yes in runtime | UML_PROPOSAL_ASSUMPTION | UML must define owner/project write authority explicitly. |
| Physical per-LOB data isolation | No; logical scope/IAM isolation unless separate banks/projects are provisioned | Yes, via per-LOB tables | UML is stronger if physical table isolation is a hard requirement. Separate managed resources may satisfy stronger boundaries without a custom engine. |
| Arbitrary structured scope | Provider supports it; application currently supports only organization + user | Build | Application scope contract is the immediate limitation. |
| Structured profile schema | Yes | Yes, JSONB ontology | Memory Bank profiles are schema-driven; UML owns its schema compiler and migrations. |
| Lazy profile creation | Yes | Build | Current setup registers schemas without pre-creating every user profile. |
| Session-boundary retrieval | Yes | Yes | Already implemented in the ADK reference agent. |
| Low-latency profile retrieval | Managed capability; live integration not yet validated | Depends on SQL/index/cache design | UML latency and capacity require benchmarks. |
| Natural-language extraction | Managed generation | Build LLM extraction service | UML enables custom models/prompts but assumes their lifecycle and quality burden. |
| Event-stream ingestion | Managed asynchronous ingestion | Build Pub/Sub pipeline and worker | A custom queue is useful only when platform replay/backpressure guarantees justify it. |
| Consolidation/deduplication | Managed capability; application must provide stable event identity and validate behavior | Build | UML provides maximum control but duplicates a managed feature. |
| Source/confidence metadata | Managed memory/provenance metadata plus control-plane source rules | Build and persist | Both can expose it; exact provider metadata needs live validation. |
| Deterministic preference resolution | Yes in application resolver; global schema precedence gap | Build in gateway/resolver | Existing resolver can be corrected without changing the memory engine. |
| Cross-domain conflict semantics | Partial through domain/source/attribute priority | OPEN QUESTION | The UML proposal does not fully specify canonical ownership, confirmation, or tie-breaking. |
| Immutable revisions and rollback | Managed capability; operator workflow incomplete | Build audit/version tables and rollback logic | Managed option avoids a complex subsystem. |
| Optimistic concurrency control | Not durable in current adapter | Proposed | UML explicitly calls for OCC; managed option still needs request idempotency and correct provider revision usage. |
| Durable platform outbox/retry/DLQ | No | Proposed Pub/Sub, but producer transaction semantics are unspecified | Both need an explicit end-to-end failure contract. |
| Privacy/PII policy before persistence | Partial through schema sensitivity/governance; provider behavior needs policy review | Proposed custom stage | UML offers precise inspection/redaction control at higher engineering cost. |
| User deletion/retention/legal hold | Partial / not fully surfaced | Build | Must be specified and tested in either architecture. |
| Fine-grained provider IAM | Supported by Memory Bank roles and IAM Conditions; Terraform not yet least privilege | Database/table/service IAM must be built | Managed option has provider defense in depth. |
| Control-plane audit | Yes | Build/reuse | Existing append-only audit can be reused. |
| Field-level memory lineage | Partial; correlate provider revisions with control-plane events | Build | Neither option is complete without an operator-facing lineage view. |
| Semantic/episodic retrieval | Managed memory retrieval capabilities | Future pgvector/episodic ledger | UML proposal labels this as future work. |
| Graph export/dreaming | Not a current requirement/capability | Future concept | Exclude from the initial architecture decision until use cases and SLOs exist. |
| Data residency/CMEK/VPC-SC | Managed platform capabilities, subject to regional/product constraints | Build with GCP services and database topology | Validate organization-specific regulatory requirements. |
| Autoscaling provider engine | Managed | Build and capacity-plan gateway, workers, SQL, and model calls | Significant operational difference. |
| Portable storage/query model | Lower; provider-specific adapter and semantics | Higher; PostgreSQL/JSONB under platform control | UML wins where direct SQL access and portability are strategic requirements. |
| Direct downstream SQL analytics | Export/integration required | Native PostgreSQL access, governed carefully | Direct reads can bypass gateway policy; use curated views or event exports. |
| Multi-tenant noisy-neighbor control | Provider quotas plus application controls; separate resources available | Build table/partition/queue/worker controls | Both need quota and budget attribution at organization/project level. |
| Existing implementation maturity | Substantial control plane, UI, approvals, resolver, ADK integration; provider adapter needs repair | Architecture proposal only | Replacement would discard or rewrite working integration layers. |

## Functional overlap

The proposed UML would recreate several capabilities already offered by Memory Bank:

- schema-driven profile memory;
- natural-language extraction;
- consolidation;
- asynchronous event ingestion;
- memory metadata and provenance;
- immutable revisions and rollback;
- scope-aware access controls;
- managed retrieval and scaling.

The UML differentiators are not simply “PostgreSQL instead of Memory Bank.” They are platform ownership of the complete memory engine, physical per-LOB tables, custom preprocessing/conflict logic, direct SQL accessibility, and freedom to add custom episodic/vector/graph subsystems.

## Gaps independent of engine choice

The following work is required regardless of whether Memory Bank or UML stores the canonical memory:

1. Consistent organization/project membership enforcement in every API.
2. A single supported scope contract across UI, database, runtime, and provider.
3. Explicit cross-domain and cross-organization ownership rules.
4. Durable idempotency, retries, correlation, and reconciliation.
5. Complete privacy, retention, deletion, and legal-hold controls.
6. Resolution-policy correctness and deterministic test suites.
7. Per-tenant observability, quotas, budget attribution, and incident procedures.
8. A migration/version compatibility contract for schema changes.

## Capability conclusion

For the current requirements, managed Memory Bank plus the existing enterprise governance layer provides the broader implemented capability set and the shorter path to production. A custom UML is justified only when requirements demand physical SQL ownership or memory processing behavior that cannot be met through provider scopes, IAM Conditions, separate managed-resource topology, or the existing resolver.

The recommended architecture therefore keeps Memory Bank as the default engine and adopts selected UML patterns—durable delivery, stable event IDs, stronger preprocessing/privacy controls, and improved lineage—inside the existing control plane. Regulated domains may opt into a separately evaluated storage tier.

## Related documents

- [Current Memory Bank Architecture Validation](current-memory-bank-architecture-validation.md)
- [Memory Bank Assumption Validation](memory-bank-assumption-validation.md)
- [Cost, Operations, and Development Analysis](memory-bank-vs-uml-cost-analysis.md)
- [ADR-0001](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md)
