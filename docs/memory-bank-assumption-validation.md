# Memory Bank Assumption Validation

## Purpose

This document separates verified behavior, repository-specific assumptions, and unresolved questions for
the managed Memory Bank option. It is supporting evidence for
[ADR-0001](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md). Statuses were re-checked
against `feature/dynamic-household-members` on 2026-09-23.

Status labels:

- **VALIDATED** — supported by current repository behavior or official Google documentation.
- **PARTIAL** — some layers implement it, but the end-to-end path is incomplete.
- **NOT VALIDATED** — intended, but without a provider-backed proof.
- **CONFLICT** — the implementation contradicts the assumption.
- **BY DESIGN** — the capability exists but the platform deliberately doesn't use it.
- **OPEN QUESTION** — a product or governance decision is still required.

## Assumptions and findings

| ID | Assumption | Status | Finding / required action |
|---|---|---|---|
| MB-01 | Business agents don't need direct Memory Bank access. | VALIDATED | The memory agent and reference agent call only the Control Plane API. A repository test forbids provider SDK imports in the reference agent; the memory agent is not yet covered by that test. |
| MB-02 | The Control Plane API validates identity, capability, scope, and grants before memory access. | PARTIAL | Runtime endpoints validate agent, capability, grants, purpose, writable mappings, exact scope, and household membership. Admin list and hierarchy reads are not yet filtered by organization membership. |
| MB-03 | Preferences are loaded once per session and cached in ADK session state. | VALIDATED | The agents resolve in `before_agent_callback`, cache the snapshot, inject it every turn, and refresh it after a write. |
| MB-04 | One profile per schema and scope. | VALIDATED | The Memory Bank profile model; schemas are registered and customer profiles stay lazy. |
| MB-05 | Memory Bank extracts and consolidates memories from ingested events. | BY DESIGN | Validated live during the spike, then turned off: provider extraction stores ungoverned memories. The platform stores only explicit, governed values. |
| MB-06 | Memory Bank provides revision history and rollback. | PARTIAL | The provider and SDK expose `revisions()` and `rollback()`; the platform exposes no operator workflow for them. |
| MB-07 | Scopes isolate customers across organizations in one bank. | PARTIAL | The runtime builds exact scopes (member, household, household-member) and derives the household from the login. Admin read isolation and least-privilege IAM Conditions are still gaps. |
| MB-08 | Every scope type the wizard offers works at runtime. | PARTIAL | Per User, Per Household, and Household + members work. Per User + Store and Custom are still offered and rejected at runtime. |
| MB-09 | Cross-organization reads work after approval; writes stay owner-only. | PARTIAL | Runtime behavior is correct. An approval covers the whole logical schema across versions, including preferences added later. Listing APIs are not yet isolated. |
| MB-10 | Configured schema precedence controls resolution. | PARTIAL | Attribute overrides apply; global schema priorities from the wizard are stored but not loaded at runtime. |
| MB-11 | A dynamic-memory policy change takes effect in the next session. | VALIDATED | The platform enforces topics, sensitivity, confidence, and retention itself on every write and resolve; no provider propagation is involved. A new session shows the updated `approvedTopics`. |
| MB-12 | Explicit writes are idempotent and concurrency-safe. | CONFLICT | Process-local lock plus append-only facts; no idempotency keys, distributed locking, retry state, or reconciliation. |
| MB-13 | Event ingestion is durably decoupled from the agent request. | BY DESIGN / PARTIAL | Provider `IngestEvents` isn't used. Events and values are written synchronously in the request; there is no outbox or retry layer. |
| MB-14 | Overlapping events are deduplicated. | BY DESIGN | Not applicable while managed generation is off; duplicate explicit writes simply become the newest value. |
| MB-15 | Provider quotas and costs are observable. | NOT VALIDATED | `scripts/memory_load_test.py` measures throughput, latency, and a price model; production telemetry for provider operations, quota, and per-organization cost does not exist. Provider `429` surfaces as HTTP 500. |
| MB-16 | Terraform deploys the complete managed memory resource. | CONFLICT | Terraform deploys the application stack and takes an existing Agent Engine / Memory Bank identifier. |
| MB-17 | The Vertex adapter uses the supported SDK surface. | VALIDATED | `agentplatform` 2.x (`memory_banks.memories`, `runtimes.update`), exercised live in the spike. Pin the SDK range more tightly. |
| MB-18 | Existing tests prove production Memory Bank compatibility. | PARTIAL | Automated tests use the mock store and a fake client; an opt-in contract test runs against a real bank; the live spike was manual. No automated live test for IAM Conditions, quotas, or failure recovery. |
| MB-19 | Control-plane audit equals complete memory lineage. | PARTIAL | Admin audit, `memory_write` / `memory_deletion` logs with correlation IDs, and the consent ledger exist. Provider revisions are not correlated. |
| MB-20 | One Memory Bank is right for every organization. | OPEN QUESTION | Logical isolation by scope and IAM Conditions is possible; residency, keys, blast radius, or quotas may justify separate banks or projects per line of business. |
| MB-21 | Household memory fits the scope model without provider changes. | VALIDATED | Household-shared (2 keys) and per-member (3 keys) scopes are within the 5-key limit; the roster lives in PostgreSQL. |
| MB-22 | A new schema version is usable without a restart and keeps existing values. | VALIDATED | An approved version replaces the registered one on the next request; values are keyed by the logical schema ID, so earlier values stay readable. |

## Provider semantics that shaped the design

### Profiles and generation

Memory profiles are structured, schema-driven memory for a scope, and generation extracts and
consolidates information into them. The platform uses the schema and scope model but not generation,
because generated memories can't be governed before they are stored.

### Streaming ingestion

`IngestEvents` decouples event submission from generation. Because generation is off, the platform
doesn't need it; a platform outbox would be justified only by durability, backpressure, or replay needs.

### Revisions

Memory Bank keeps immutable revisions. The platform should expose revision IDs and rollback through its
governance API rather than build a second revision mechanism.

### IAM and scope

Memory Bank-specific roles and IAM Conditions over scope values can back up the database grants as
defense in depth. They are not configured yet.

## Decisions

| Decision | Status |
|---|---|
| Scope contract | **Decided:** member, household-shared, and household-member shapes. Store and custom scopes to be hidden or built. |
| Conflict semantics | **Decided for households:** confidence tiers, confirmation for new people and health data, no automatic merges. Cross-schema source/domain rules are policy data. |
| Deletion and privacy | **Mostly implemented:** user/member/household forget, single-value forget, purge, retention sweep, consent ledger with withdrawal. Legal hold and backup deletion are open. |
| Retention limits | **Placeholders** (1095 / 730 days) pending Legal. |
| Tenant topology | Open (MB-20). |
| Write durability | Open (MB-12). |
| Cost attribution | Open (MB-15). |
| Provider failure policy | Open: today requests fail; agents keep the cached session snapshot. |

## Recommended validation tests

Done in the automated suite: grant revoke/expire without restart; cross-organization read-only sharing;
schema versions without restart; household isolation; consent and confirmation; purpose denial;
retention sweep.

Still to do:

- Two organizations with the same user ID, proving neither can list the other's records through the admin
  API (fails today; see MB-02).
- Conflicting values across schemas, proving global precedence (fails today; see MB-10).
- Duplicate explicit writes with idempotency keys, and concurrent writes from several instances.
- Revision history and rollback, with the snapshot version and provenance changing.
- IAM Conditions with allowed and denied scopes.
- Provider timeouts, throttling, partial failure, and retry exhaustion.

## Official references

- [Memory profiles](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/profiles)
- [Generate memories](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/generate-memories)
- [Ingest events](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/ingest-events)
- [Memory revisions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/revisions)
- [Memory Bank IAM Conditions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/iam-conditions)
