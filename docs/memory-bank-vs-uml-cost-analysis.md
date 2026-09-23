# Memory Bank vs. Unified Memory Layer Cost, Operations, and Development Analysis

## Purpose and caution

This is a decision model, not a procurement quote. Prices change, region and edition matter, discounts
are excluded. Recalculate with billing exports and the Google Cloud Pricing Calculator before production
approval. The access pattern below was re-checked against `feature/dynamic-household-members` on
2026-09-23; prices were last checked on 2026-08-28:

- [Gemini Enterprise Agent Platform pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing) (includes Memory Bank)
- [Generative AI pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)

## What changed since the first version

- **Managed generation is off.** The platform never triggers Memory Bank extraction, so there are no
  Memory Bank generation or embedding tokens. Extraction happens inside the agent's existing LLM call
  (the tool-selection decision), so it adds no extra model call either.
- **No event write in the normal path.** Agents save values with explicit writes; the event endpoint is
  optional.

## Comparison unit

One unit is one customer session that saves one preference:

- one session-start resolve;
- one explicit write;
- one post-write refresh (the agent re-resolves after every write);
- three readable schemas (`R = 3`);
- for the custom UML only: about 1 KiB per queued event and an extractor call of 1,000 input and 200
  output tokens;
- us-central1 illustrative infrastructure rates; no committed-use discounts, taxes, support, or egress.

The token envelope is a modeling assumption for the UML extractor only.

## Managed Memory Bank operation model

The Vertex adapter makes two reads per readable schema per resolve (`retrieve_profiles` + `retrieve`),
and each write reads once (to compute the write counter) and writes once:

```text
initial resolve:       2R reads
explicit write:        1 read + 1 write
post-write refresh:    2R reads
-----------------------------------------
total:                 4R + 1 reads, 1 write
```

With `R = 3`: 13 reads and 1 write per unit. In household setups the per-member schema is read only when a
turn names a member, so `R` counts the household-shared and member-level schemas actually read.

Published Memory Bank rates (checked 2026-08-28):

- stored memory including revisions: **$0.30 per GiB-month**;
- reads: one Agent Compute vCPU-hour (**$0.085**) per 3 million read operations;
- writes: one Agent Compute vCPU-hour (**$0.085**) per 1 million write operations;
- generation and embedding tokens are billed separately (not used by this platform);
- billing under this structure began **September 1, 2026**.

### Illustrative monthly operation charge

| Workload | Reads | Writes | Read charge | Write charge | Operations subtotal |
|---|---:|---:|---:|---:|---:|
| 1 million units/month | 13 million | 1 million | $0.37 | $0.09 | **$0.45** |
| 30 million units/month | 390 million | 30 million | $11.05 | $2.55 | **$13.60** |

Excluded: storage and revisions, the Control Plane (Cloud Run, Cloud SQL), logging, networking, and
support. API-operation charges are unlikely to dominate; the binding constraint is the per-minute
**quota**, not cost.

## Custom UML variable-cost model

### Pub/Sub

For one publisher and one subscriber, about twice the payload is billed as throughput. At 1 KiB per
event:

| Workload | Publish + delivery volume | Illustrative throughput charge |
|---|---:|---:|
| 1 million events/month | 1.86 GiB | $0 within the 10 GiB free allowance |
| 30 million events/month | 55.9 GiB | about **$1.79** after the free allowance, at $40/TiB |

Excludes retained-message storage, snapshots, replay, cross-region charges, extra subscriptions, and the
1 KiB minimum billable size.

### Custom extraction model

Using Gemini 2.5 Flash Lite standard pricing ($0.10 per million input tokens, $0.40 per million output
tokens) and the assumed 1,000 / 200 tokens per event:

```text
cost per event = (1,000 / 1,000,000 × $0.10) + (200 / 1,000,000 × $0.40) = $0.00018
```

| Workload | Illustrative extraction charge |
|---|---:|
| 1 million events/month | **$180** |
| 30 million events/month | **$5,400** |

Excludes retries, classification, embeddings, conflict calls, cached-token and batch discounts, and price
changes. If every message (not only the ~10% that contain a preference) were sent to the extractor, the
event count — and this cost — would be roughly ten times the preference count.

## Fixed infrastructure model

The Terraform default is a single-zone Cloud SQL PostgreSQL `db-custom-1-3840`. At illustrative
us-central1 Enterprise on-demand rates ($0.0413 per vCPU-hour, $0.007 per GiB-hour):

```text
(1 vCPU × $0.0413 + 3.75 GiB × $0.007) × 730 hours ≈ $49.31/month
```

An HA configuration roughly doubles that (≈ $98.62/month) before storage, backups, replicas, and network.
The managed option already needs this database and the Control Plane API, so those shared costs aren't
counted only against Memory Bank.

The custom UML additionally needs highly available gateway and writer compute, autoscaling and
backpressure, database storage and indexes and backups, Pub/Sub topics and DLQs, model calls, and
operational dashboards, reconciliation jobs, and on-call procedures.

## Cost comparison by category

| Cost category | Managed Memory Bank + governance | Custom UML |
|---|---|---|
| Memory operations | Metered reads/writes; small in the example | SQL capacity plus gateway/worker compute |
| Extraction | None extra: the agent's own LLM call | Direct model tokens plus orchestration and retries |
| Storage | $0.30/GiB-month including revisions | Cloud SQL data, indexes, audit, backups, PITR; replicas multiply it |
| Queue | None | Pub/Sub throughput, retention, DLQ, replay |
| Baseline infrastructure | Existing API and governance database | Same plus writer/engine capacity and a larger database |
| Scaling | Managed engine; quota raises from Google | Capacity planning for connections, hot tenants, indexes, workers, model quotas |
| Disaster recovery | Provider capability plus application recovery | Platform-owned restore, replay, and regional strategy |
| Cost attribution | Correlate provider SKUs to tenant metadata | Easier to instrument, still needs allocation logic |

## Operations comparison

| Concern | Managed option | Custom UML |
|---|---|---|
| Availability | Provider SLO plus Control Plane availability | Combined SLO of gateway, queue, workers, SQL, and model calls |
| Capacity | Provider quota and request rate | Queue lag, worker concurrency, SQL CPU/IO/connections, model quotas |
| Data repair | Provider revisions plus platform reconciliation | Build replay, re-extraction, merge repair, audit reconstruction |
| Upgrades | SDK/API compatibility and schema versions | All of those plus database migrations and engine algorithm versions |
| Security | Provider IAM Conditions, VPC-SC/CMEK options, application grants | Full database/service security and privileged access |
| Observability | Provider metrics/billing plus platform logs | Instrument every pipeline stage |
| Incident response | Provider escalation plus application runbooks | The whole memory engine is platform-owned |

## Development comparison

| Area | Managed option | Custom UML |
|---|---|---|
| Remaining initial work | Admin read isolation, schema precedence, scope cleanup, idempotency, quota handling, least-privilege IAM, landing-zone deploy | Gateway, access matrix, writer, prompts/models, ontology compiler, dedupe, conflicts, OCC, audit, revisions, privacy, migrations, replay, tooling — plus the same governance work |
| Ongoing work | Provider upgrades, policy evolution, adapter tests, governance UX | Model quality, database performance, engine correctness, migrations, on-call |
| Test surface | Authorization, provider integration, policy, failure handling | All of that plus distributed delivery, ordering, duplicates, concurrency, extraction evaluation, recovery |
| Time to production evidence | Shorter: control plane and adapter are built and live-validated | Longer: no implementation |
| Flexibility | Bounded by provider capabilities | Maximum control and portability |

## Engineering TCO dominates the decision

At low and moderate volumes, infrastructure and API-operation charges are far smaller than the cost of
building and operating a reliable custom memory engine. Don't choose the UML because PostgreSQL or
Pub/Sub looks cheap in isolation; include design, implementation, evaluation, security review,
migrations, 24x7 operations, incident recovery, and opportunity cost.

## Recommended measurement plan

1. Deploy to the landing zone and run a representative load test (`scripts/memory_load_test.py`).
2. Export billing by SKU and correlate requests by organization, project, agent, and schema.
3. Measure provider read/write counts, revision growth, latency, error rates, and quota headroom.
4. Prototype only a differentiating UML path for one domain, if a requirement demands it.
5. Estimate engineering and on-call staffing for both options over three years.
6. Revisit the ADR only if a prototype proves a regulatory, quality, latency, portability, or
   direct-query advantage worth that cost.

## Related documents

- [Current Memory Bank Architecture Validation](current-memory-bank-architecture-validation.md)
- [Memory Bank Assumption Validation](memory-bank-assumption-validation.md)
- [Capability Matrix](memory-bank-vs-uml-capability-matrix.md)
- [ADR-0001](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md)
