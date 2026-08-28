# Memory Bank vs. Unified Memory Layer Cost, Operations, and Development Analysis

## Purpose and caution

This document provides a decision model, not a procurement quote. Prices change, region and edition matter, discounts are excluded, and Memory Bank generation-token usage depends on actual payloads and model behavior. Recalculate with billing exports and the Google Cloud Pricing Calculator before production approval.

Official pricing checked on 2026-08-28:

- [Gemini Enterprise Agent Platform pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing)
- [Generative AI pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)

## Comparison unit

The illustrative workload uses:

- one completed conversation event per unit;
- one explicit candidate update;
- one session-start resolve and one post-write refresh;
- three readable schemas (`R = 3`);
- approximately 1 KiB per queued UML event;
- for the custom UML extractor only, 1,000 input and 200 output tokens per event;
- us-central1 illustrative infrastructure rates where a regional example is necessary;
- no committed-use discounts, taxes, support charges, or network egress.

The token envelope is an explicit modeling assumption. It must not be interpreted as Memory Bank's internal token usage.

## Managed Memory Bank operation model

Based on the current repository adapter, one unit performs approximately:

```text
initial resolve:       2R reads
explicit update:       1 read + 1 write
event fact + ingestion:          2 writes
post-write refresh:    2R reads
-----------------------------------------
total:                 4R + 1 reads, 3 writes
```

With `R = 3`, that is 13 read operations and 3 write operations per unit. This is a repository-specific estimate, not a statement that every application must use this access pattern.

Google's current published Memory Bank rate states:

- stored memory including revisions: **$0.30 per GiB-month**;
- reads: one Agent Compute vCPU-hour (**$0.085**) per 3 million read operations;
- writes: one Agent Compute vCPU-hour (**$0.085**) per 1 million write operations;
- generation and embedding tokens are charged separately under the applicable model SKUs;
- billing under this Memory Bank structure begins **September 1, 2026**.

### Illustrative monthly operation charge

| Workload | Reads | Writes | Read charge | Write charge | Operations subtotal |
|---|---:|---:|---:|---:|---:|
| 1 million units/month | 13 million | 3 million | $0.37 | $0.26 | **$0.62** |
| 30 million units/month | 390 million | 90 million | $11.05 | $7.65 | **$18.70** |

Excluded: stored memories/revisions, generation and embedding tokens, Control Plane Cloud Run/Cloud SQL, logging, networking, and support.

The main conclusion is that API-operation charges are unlikely to dominate. Generation tokens, retention/revision growth, application infrastructure, and engineering effort require measurement.

## Custom UML variable-cost model

### Pub/Sub

For one publisher and one subscriber, approximately twice the message payload is billed as throughput. At 1 KiB per event:

| Workload | Approximate publish + delivery volume | Illustrative throughput charge |
|---|---:|---:|
| 1 million events/month | 1.86 GiB | $0 within the first 10 GiB free allowance |
| 30 million events/month | 55.9 GiB | about **$1.79** after the first 10 GiB, at $40/TiB |

This excludes retained-message storage, snapshots, seek/replay storage, cross-region charges, additional subscriptions, and the 1 KiB minimum billable request size.

### Custom extraction model

Using Gemini 2.5 Flash Lite standard pricing as an illustrative custom extractor—$0.10 per million input tokens and $0.40 per million output tokens—and the assumed 1,000 input/200 output tokens per event:

```text
cost per event = (1,000 / 1,000,000 * $0.10)
               + (  200 / 1,000,000 * $0.40)
               = $0.00018
```

| Workload | Illustrative extraction charge |
|---|---:|
| 1 million events/month | **$180** |
| 30 million events/month | **$5,400** |

This excludes retries, safety/classification calls, embeddings, conflict-resolution calls, cached-token discounts, batch discounts, and future model price changes. The same empirical token measurement is needed for the managed option; Memory Bank's internal generation envelope must not be assumed equal to this custom pipeline.

## Fixed infrastructure model

The repository's current Terraform default uses a single-zone Cloud SQL PostgreSQL instance sized as `db-custom-1-3840`. Using the current Cloud SQL Enterprise general-purpose us-central1 illustrative on-demand rates of $0.0413 per vCPU-hour and $0.007 per GiB-hour:

```text
(1 vCPU * $0.0413 + 3.75 GiB * $0.007) * 730 hours
= approximately $49.31/month
```

An HA configuration roughly doubles compute and memory before storage, backups, replicas, network, and support, yielding about $98.62/month for that narrow component. Confirm the actual database edition, region, machine compatibility, and calculator output.

The custom UML additionally needs:

- highly available gateway and writer compute;
- autoscaling and backpressure controls;
- database storage, indexes, audit growth, backups, PITR, and possibly replicas;
- Pub/Sub topics, subscriptions, DLQs, retention, replay, and monitoring;
- model calls for extraction, classification, consolidation, and conflicts;
- operational dashboards, alerts, reconciliation jobs, and on-call procedures.

The managed option already needs the Control Plane API and governance database, so those shared costs should not be counted only against Memory Bank.

## Cost comparison by category

| Cost category | Managed Memory Bank + governance | Custom UML |
|---|---|---|
| Memory operations | Metered managed reads/writes; inexpensive in the example | SQL reads/writes included in database capacity; gateway/worker compute additional |
| Extraction/consolidation | Provider generation and embedding tokens; measure from billing | Direct model-token expense plus custom orchestration and retries |
| Storage | $0.30/GiB-month including revisions under current published schedule | Cloud SQL data/index/audit/backup/PITR storage; replicas multiply cost |
| Queue | Provider event ingestion; optional platform outbox | Pub/Sub throughput, retention, DLQ, and replay |
| Baseline infrastructure | Existing API and governance DB | Existing control plane plus new writer/engine capacity and a larger operational DB footprint |
| Scaling | Managed memory engine | Capacity planning for SQL connections, hot tenants, indexes, workers, and model quotas |
| Disaster recovery | Provider capabilities plus application recovery | Platform-owned restore, replay, version compatibility, and regional strategy |
| Cost attribution | Must correlate provider and token SKUs to tenant metadata | Easier to instrument directly, but all services still require allocation logic |

## Operations comparison

| Operational concern | Managed option | Custom UML |
|---|---|---|
| Availability | Provider SLO plus Control Plane/API availability | Platform owns gateway, queue, workers, SQL, model orchestration, and their combined SLO |
| Capacity | Provider quotas and application request rate | Queue lag, worker concurrency, SQL CPU/IO/connections, table growth, and model quotas |
| Data repair | Provider revisions plus platform reconciliation | Build replay, re-extraction, compaction, merge repair, and audit reconstruction |
| Upgrades | SDK/API compatibility and schema evolution | All managed concerns plus database migrations and engine algorithm versions |
| Security | Provider IAM Conditions, VPC-SC/CMEK options, application grants | Full database/table/service security and privileged operational access |
| Observability | Provider metrics/billing plus platform traces | Instrument every pipeline stage and correlate messages, model calls, SQL versions, and agents |
| Incident response | Provider escalation plus application runbooks | Entire memory engine is a platform-owned incident domain |

## Development comparison

| Development area | Managed option | Custom UML |
|---|---|---|
| Initial work | Repair SDK adapter, enforce isolation, finish resolver/scope correctness, add live tests | Design and build gateway, access matrix, writer, prompts/models, ontology compiler, dedupe, conflicts, OCC, audit, revisions, privacy, migrations, replay, and tooling |
| Ongoing work | Provider upgrades, policy evolution, adapter tests, governance UX | Model/prompt quality, database performance, engine correctness, schema migrations, on-call tooling, and all managed-option governance work |
| Test surface | Authorization, provider integration, policy, failure handling | Same plus distributed delivery, ordering, duplicates, concurrency, migrations, extraction evaluation, replay, and storage recovery |
| Time to production evidence | Shorter after current P0/P1 gates | Longer; proposal currently has no implementation evidence |
| Flexibility | Bounded by provider capabilities | Maximum control and portability |

## Engineering TCO dominates the decision

For both low and moderate volumes, the illustrative infrastructure and API-operation charges are smaller than model-generation cost and dramatically smaller than the cost of building and operating a reliable custom memory engine. A team should not choose UML because PostgreSQL or Pub/Sub appears cheap in isolation. The decision must include design, implementation, evaluation, security review, migrations, 24x7 operations, incident recovery, and opportunity cost.

## Recommended measurement plan

Before an accepted production decision:

1. Correct the Memory Bank integration and run a representative load test.
2. Export billing by SKU and correlate requests by organization, project, agent, and schema.
3. Measure provider read/write counts, generation/embedding tokens, revision growth, latency, and error rates.
4. Prototype only the differentiating UML path for one domain, not the full engine.
5. Measure extraction quality and token use on the same evaluation dataset.
6. Load-test PostgreSQL JSONB queries, OCC conflicts, queue lag, replay, and recovery.
7. Estimate engineering and on-call staffing for both options over three years.
8. Revisit the ADR only if the custom prototype proves a regulatory, quality, latency, portability, or direct-query advantage worth that TCO.

## Related documents

- [Current Memory Bank Architecture Validation](current-memory-bank-architecture-validation.md)
- [Memory Bank Assumption Validation](memory-bank-assumption-validation.md)
- [Capability Matrix](memory-bank-vs-uml-capability-matrix.md)
- [ADR-0001](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md)
