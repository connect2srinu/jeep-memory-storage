# SPIKE: Validate Vertex Memory Bank POC & Technical Integration Gaps

**Story:** DEART-53184 / DEART-56710 · **Status:** Findings ready for review

Validation of Google Vertex AI Memory Bank as the shared long-term memory for the Unified Memory
Layer "Build vs. Buy" evaluation. The POC was hardened and exercised **against a real Vertex AI
Agent Engine** (not a mock) to resolve the outstanding data-modeling, streaming, observability, and
governance questions.

## Summary against acceptance criteria

| Acceptance criterion | Status | One-line result |
|---|---|---|
| Architecture Parity | ✅ Validated | ADK `DatabaseSessionService` → Postgres/Cloud SQL for sessions; shared long-term persisted in Vertex Memory Bank. |
| Data Streaming | ⚠️ Partial / clarified | Memory Bank ingests **application events** (`ingest_events`), not Cloud-SQL CDC. Mechanism validated, then **deliberately disabled** for governance. |
| Environment Configuration | ❌ Gap | Run against real Vertex from a local Docker harness; **GCP Dev/Pilot landing-zone deploy (networking, firewall, billing) is outstanding**. |
| Data Modeling | ✅ Validated | System differentiates **canonical (explicit)**, **dynamic (topic-gated)**, and **unstructured semantic** memory; the last is disabled by design. |
| Observability & Evals | ⚠️ Partial | Structured **logging** added and validated; **Cloud Trace not wired**; **eval harness not built**. |
| Model Flexibility | ✅ Assessed | Memory Bank's generation model is **Gemini-only** — `gemini-2.5` rejected, `gemini-3.5-flash` required. Custom/open-source models not supported for extraction. |
| Governance / CCPA | ✅ Validated (implemented) | Native `delete`/`list` wrapped in governed endpoints: **user `forget`** and **operator `purge`** (capability-gated, previewable). Verified live: forget deleted both tiers; purge removed a topic across users. |

Legend: ✅ validated · ⚠️ partial / caveated · ❌ open gap.

## Environment validated against

- **Provider:** Vertex AI Memory Bank via `agentplatform` 2.x SDK (`memory_banks.memories.*`,
  `runtimes.update`).
- **Real resource:** Agent Engine (reasoning engine) `5362284673558904832`, project
  `e2eml-222003`, `us-central1`, authenticated with Application Default Credentials.
- **Harness:** Docker Compose — `control-plane-api` (FastAPI) + PostgreSQL + admin console. Short-term
  sessions in Postgres (Cloud SQL stand-in, same `postgresql+asyncpg` driver Cloud SQL uses).
- **Live checks performed:** activation `201`; runtime resolve / write / refresh `200`; Agent Engine
  schema count increased on provisioning; canonical + dynamic writes read back through `resolve`.

## Findings by acceptance criterion

### 1. Architecture Parity — ✅ Validated

The POC runs the split-memory pattern Google documents for ADK:

- **Short-term / session state** → ADK `DatabaseSessionService` on PostgreSQL. In GCP this is Cloud
  SQL; the local harness uses the same async driver, so it is a faithful stand-in.
- **Long-term / shared memory** → persisted in Vertex Memory Bank, reached through the Control Plane
  runtime API (`/api/v1/runtime`) rather than a direct provider call from the agent.

A dedicated `memory-agent` demonstrates both tiers end to end (session 1 writes a preference; a fresh
session 2 recalls it). Sessions are confirmed to land in the Postgres `sessions` table; long-term
values are confirmed in Memory Bank via `resolve` and the raw-profiles endpoint.

### 2. Data Streaming — ⚠️ Partial / architecture clarified

**Finding:** Memory Bank does **not** consume a real-time change stream from Cloud SQL. Its ingestion
model is **application-driven event ingestion** — the app sends conversation events to
`ingest_events`, which the provider's model turns into memories asynchronously. There is no Cloud SQL
CDC → Memory Bank pipeline to validate as literally worded.

We validated that the `ingest_events` mechanism works, and then made a deliberate architecture
decision: **managed generation is disabled** in the POC (the `ingest_events` call was removed). The
provider's automatic extraction persists whatever it chooses, which is ungoverned; the evaluation
target requires the platform to control what is retained. Long-term memory is therefore written
through **explicit, governed calls** instead of a managed stream.

**Recommendation:** treat "streaming" as event ingestion, and note that using the managed generation
stream trades governance for convenience. If a Cloud SQL → Memory Bank sync is desired, it must be
built (application-level), not assumed from the managed service.

### 3. Environment Configuration — ❌ Gap (outstanding)

The POC was exercised against **real Vertex Memory Bank** but from a **local Docker harness** using
ADC. It has **not** been deployed into the GCP Dev/Pilot landing zone. Consequently the following are
**not yet captured** and remain open work:

- VPC networking rules and firewall constraints for the reasoning-engine / Vertex endpoints.
- Service-account / Workload Identity wiring (vs. local ADC).
- True billing data for Memory Bank generation and storage in the target project.

**Recommendation:** deploy `control-plane-api` to the Dev/Pilot landing zone (Cloud Run or GKE) with
Cloud SQL and Workload Identity, and capture networking + billing from a real run before the
build-vs-buy cost model is finalized.

### 4. Data Modeling — ✅ Validated (strongest area)

The system explicitly differentiates three memory types and treats each differently:

| Type | Definition | Handling |
|---|---|---|
| **Canonical (explicit)** | Value bound to a defined schema attribute | `PUT /preferences/{attribute}`; resolves as `MEMORY_PROFILE`, confidence `1.0`, deterministic. |
| **Dynamic** | Non-canonical fact inside an **approved topic** | `POST /memory/dynamic`; **platform-gated** by the domain's approved topics; resolves as `DYNAMIC_MEMORY` below canonical, subject to a confidence threshold. |
| **Unstructured semantic** | Free-form provider-generated memory | **Disabled by design** — managed generation is off, so ungoverned semantic memories are not persisted. |

Key controls validated live: writing an unregistered attribute is rejected; writing an unapproved
topic returns `403`; sensitive content (phone/SSN/card/email/secret) returns `400`; a low-confidence
dynamic entry is dropped from resolution by the confidence threshold; a canonical value always
outranks a dynamic one for the same key.

A latent read bug was also found and fixed during the spike: the provider returns memories
newest-first, and the overlay reconstruction was dropping all but the most-recent attribute; the fix
keeps the latest value **per attribute/topic**.

### 5. Observability & Evals — ⚠️ Partial

- **Logging — validated.** Every long-term write now emits a structured `memory_write` event with
  `tier` (canonical/dynamic), `op` (created vs updated, derived from version), attribute/topic,
  schema, version, and request `correlation_id`. Values are never logged. Every HTTP request is also
  logged with correlation id, method, path, status, and duration. These flow to container logs and,
  in GCP, to Cloud Logging (`jsonPayload.event="memory_write"`).
- **Tracing — gap.** No OpenTelemetry / Cloud Trace exporter is configured. Memory Bank calls will
  **not** appear in Cloud Trace without added instrumentation.
- **Evals — gap.** Memory Bank's out-of-the-box generation-quality eval metrics were **not** tested;
  because managed generation is disabled, generation-quality evals are not applicable to the governed
  path, and no separate eval harness was built.

**Recommendation:** if traces are required, add OTel spans around the provider SDK calls with the
Cloud Trace exporter. Decide whether generation-quality evals matter given the governed (non-managed)
approach.

### 6. Model Flexibility — ✅ Assessed (lock-in confirmed)

- Memory Bank's memory-generation/extraction model is **configurable but Google-only**. Attempting
  `gemini-2.5-flash` was **rejected** by the provider: *"Gemini 2.5 models are not supported. Use
  `gemini-3.5-flash` instead."* The value was pinned to `gemini-3.5-flash` and made configurable via
  `MEMORY_BANK_GENERATION_MODEL`.
- **Custom / open-source models are not supported** for Memory Bank extraction — strict Gemini
  enforcement.
- Note the distinction: the **agent's own chat model** is free to be any model (via ADK); the lock-in
  is specific to **Memory Bank's internal extraction model**. In the governed POC, managed generation
  is disabled, so this lock-in has limited impact on our path — but it is a real constraint for any
  design that relies on managed generation.

### 7. Governance / CCPA (explicit deletion) — ✅ Validated (implemented & tested live)

**Finding:** Vertex Memory Bank **supports hard deletion natively**, and the POC now wraps it in two
governed endpoints. The `agentplatform` SDK (`memory_banks.memories`) exposes, out of the box:

- **`delete(name=…)`** — delete a single memory by its full resource name
  (`…/reasoningEngines/{id}/memories/{memory}`).
- **`purge(name=…, filter=…, filter_groups=…, force=…)`** — bulk delete by a standard list `filter`
  or `filter_groups` (metadata filters in disjunctive normal form). `force=false` **stages** the
  purge without executing it — a built-in preview/dry-run before deletion.
- **`list` / `get`** — enumerate and fetch memories (to resolve names for targeted deletes).
- **`revisions()` + `rollback(name, target_revision_id)`** — memories are versioned and can be rolled
  back to a prior revision.

This covers **both** requested scenarios:

| Scenario | Endpoint (implemented) | Result |
|---|---|---|
| **User "forget me"** (CCPA right-to-be-forgotten) | `POST /api/v1/runtime/memory/forget` (gated by `SUBMIT_CANDIDATES`) | Lists the user's memories (isolated by immutable scope) and deletes each by name. Verified live — deleted both canonical + dynamic, count 2, resolve then empty. |
| **Operator on-demand** ("this memory must be deleted for users in the org") | `POST /api/v1/runtime/memory/purge` (gated by `ADMINISTER_MEMORY`) | Lists org memories, matches by `tier`/`attribute`/`topic`, deletes matches; `dryRun` (default) previews first. Verified live — previewed then removed a topic across users. |

Both endpoints emit a `memory_deletion` audit event. The earlier assumption that deletion was
unavailable was about our POC wrapper, not the provider — the underlying service supports it. Writes
are versioned/append-style, but hard delete is first-class.

**Implementation notes / caveats:**

- Enumeration uses `list` (authoritative) rather than `retrieve` (similarity-based, which can miss
  memories), filtered by each memory's immutable `{organization_id, user_id}` scope.
- Targeting matches on the stored `fact` (tier via schema, plus attribute/topic). Attaching provider
  **`metadata`** at write time would additionally enable native `purge` filter/`filter_groups`; not
  required for the current list-and-match approach.
- **Eventual consistency:** Memory Bank reads lag writes/deletes, so an immediate `deleted`/`matched`
  count can under-report a just-written value. The end state is correct. For hard-delete SLAs, await
  the delete operations to completion.

## Key decisions & cross-cutting findings

1. **Managed generation is ungoverned** — disabling it and using explicit + topic-gated writes is the
   only way to guarantee the platform controls what is retained.
2. **Versioned storage with native delete/purge** — there is no field-level *update* (an update is a
   new version), but the provider **does** offer hard `delete`, filter-based `purge` (stageable), and
   revision `rollback`. CCPA deletion is achievable out of the box (see #7).
3. **Gemini lock-in** applies to Memory Bank extraction only, not the agent chat model.
4. **No native per-user memory browser** in the Cloud console — inspection is via API/SDK
   (`resolve`, raw-profiles, or `memories.retrieve`); Vertex Data Access audit logs can show API
   calls if enabled.

## Outstanding work (to fully close the spike)

- [ ] Deploy to GCP Dev/Pilot landing zone; capture networking, firewall, and true billing.
- [x] Governed deletion — user `forget` + operator `purge` endpoints, capability-gated, previewable,
      audited; validated live (see #7).
- [ ] (Optional) attach write-time `metadata` and await delete operations for hard-delete SLAs.
- [ ] Add Cloud Trace instrumentation if tracing is required.
- [ ] Decide on eval strategy given the governed (non-managed) approach.

## Artifacts

- **Branch:** `feature/adk-dual-memory` (pushed to `origin`).
- **Runtime API:** `POST /api/v1/runtime/preferences/resolve`, `PUT /api/v1/runtime/preferences/{attribute}`,
  `POST /api/v1/runtime/memory/dynamic`, `POST /api/v1/runtime/profiles`.
- **Key commits:** overlay-drop fix `065da4f`; generation model pin `f280556`; topic-gated dynamic
  memory `2eff48e`; agent flow `38495b9`; memory-write logging `a4bbcbc`.
- **Tests:** `test_runtime_api.py::test_dynamic_memory_is_topic_gated_and_surfaces_in_resolution`,
  `test_vertex_memory_store.py` (managed generation off; latest-per-topic), `test_preference_resolution.py`
  (confidence gate).
- **Design docs:** `docs/dynamic-memory-topic-gating.md`; memory-flow diagrams in
  `docs/GEAP_Memory_Flows.drawio` (page 5 — Dynamic Memory Topic Gate).
