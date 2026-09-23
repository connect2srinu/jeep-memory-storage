# SPIKE: Validate Vertex Memory Bank POC & Technical Integration Gaps

**Story:** DEART-53184 / DEART-56710 · **Status:** Findings ready for review; status re-checked
2026-09-23 against `feature/dynamic-household-members`.

Validation of Google Vertex AI Memory Bank as the shared long-term memory for the Unified Memory Layer
"Build vs. Buy" evaluation. The POC was exercised **against a real Vertex AI Agent Engine** (not a mock)
to resolve the data-modeling, streaming, observability, and governance questions. The live findings
below were recorded during the spike; the status column reflects the code today.

## Summary against acceptance criteria

| Acceptance criterion | Status | Result |
|---|---|---|
| Architecture Parity | ✅ Validated | ADK `DatabaseSessionService` on PostgreSQL/Cloud SQL for sessions; shared long-term memory in Vertex Memory Bank through the Control Plane runtime API. |
| Data Streaming | ✅ Clarified (by design) | Memory Bank ingests **application events** (`ingest_events`), not Cloud SQL CDC. The mechanism was validated, then **deliberately disabled**; all long-term memory is written through governed calls. |
| Environment Configuration | ❌ Open | Validated from a local Docker harness against real Vertex. No GCP Dev/Pilot landing-zone deployment (networking, firewall, billing) is recorded yet. |
| Data Modeling | ✅ Validated and extended | Canonical (schema-bound), dynamic (topic-gated), and unstructured (disabled) memory; since the spike also household-shared and per-member scopes with runtime member resolution. |
| Observability & Evals | ⚠️ Partial | Structured `memory_write` / `memory_deletion` / request logs; no Cloud Trace exporter; no eval harness. |
| Model Flexibility | ✅ Assessed | Memory Bank's extraction model is Google-Gemini-only. It doesn't affect the governed path because managed generation is off. |
| Governance / CCPA | ✅ Implemented | User `forget` (member, or household with cascade), single-value forget, operator `purge`, retention sweep, and consent-withdrawal deletion; all audited. |

Legend: ✅ validated · ⚠️ partial · ❌ open.

## Environment validated against

- **Provider:** Vertex AI Memory Bank via the `agentplatform` 2.x SDK (`memory_banks.memories.*`,
  `runtimes.update`).
- **Real resource:** Agent Engine `5362284673558904832`, project `e2eml-222003`, `us-central1`, with
  Application Default Credentials.
- **Harness:** Docker Compose — `control-plane-api` + PostgreSQL + Admin Console; short-term sessions in
  PostgreSQL with the same `postgresql+asyncpg` driver Cloud SQL uses.
- **Live checks performed:** activation `201`; resolve / write / refresh `200`; the Agent Engine schema
  count increased on provisioning; canonical and dynamic writes read back through `resolve`.

## Findings by acceptance criterion

### 1. Architecture Parity — ✅

- **Short-term / session state** → ADK `DatabaseSessionService` on PostgreSQL (Cloud SQL in GCP).
- **Long-term / shared memory** → Vertex Memory Bank, reached only through the Control Plane runtime API
  (`/api/v1/runtime`), never directly from the agent.

The [`memory-agent`](../apps/memory-agent) demonstrates both tiers: session 1 saves a preference and a
fresh session 2 recalls it. Sessions land in the PostgreSQL `sessions` table; long-term values are read
back through `resolve` and the raw-profiles endpoint.

### 2. Data Streaming — ✅ clarified

Memory Bank does not consume a change stream from Cloud SQL. Its ingestion model is application-driven:
the app sends conversation events to `ingest_events`, and the provider's model turns them into memories
asynchronously. We validated that mechanism, then **disabled managed generation**: the provider's
extraction persists whatever it chooses, which is ungoverned. The platform instead writes only
explicit, governed values. If a Cloud SQL → Memory Bank sync is ever wanted, it must be built at the
application level.

### 3. Environment Configuration — ❌ open

Still outstanding:

- VPC networking and firewall rules for the reasoning-engine / Vertex endpoints;
- service-account / Workload Identity wiring instead of local ADC;
- real billing data for Memory Bank storage and operations in the target project.

The Terraform module in `infrastructure/terraform` defines the Cloud Run, Cloud SQL, networking, and IAM
resources for such a deployment; it has not been applied to the landing zone as part of this spike.

### 4. Data Modeling — ✅ (strongest area)

| Type | Definition | Handling |
|---|---|---|
| **Canonical** | Value bound to a schema attribute | `PUT /preferences/{attribute}`; resolves as `MEMORY_PROFILE`, confidence `1.0`, deterministic |
| **Dynamic** | Non-canonical fact inside an **approved topic** | `POST /memory/dynamic`; platform-gated by approved topics; resolves as `DYNAMIC_MEMORY` below canonical, subject to a confidence threshold |
| **Unstructured semantic** | Free-form provider-generated memory | **Disabled by design** |

Since the spike, canonical memory also supports three scope shapes (member, household-shared,
per-member) with runtime household member resolution, confirmation turns, and a consent ledger for
health data. See [Dynamic Household Members](dynamic-household-members-design.md).

Controls validated live during the spike: an unregistered attribute is rejected; an unapproved topic
returns `403`; restricted content returns `400`; a low-confidence dynamic entry is dropped from
resolution; a canonical value outranks a dynamic one for the same key.

A read bug was found and fixed during the spike: the provider returns memories newest-first, and the
overlay reconstruction dropped all but the most recent attribute. The fix keeps the latest value per
attribute and per topic.

### 5. Observability & Evals — ⚠️ partial

- **Logging — done.** Every long-term write emits a structured `memory_write` event (tier, operation,
  attribute/topic, schema, version, sensitivity, source, correlation ID); deletions emit
  `memory_deletion`; every request is logged with correlation ID, method, path, status, and duration.
  Values are never logged. On Cloud Run these are Cloud Logging `jsonPayload` entries.
- **Tracing — open.** Terraform grants `roles/cloudtrace.agent`, but no OpenTelemetry / Cloud Trace
  exporter is configured, so Memory Bank calls don't appear in Cloud Trace.
- **Evals — open.** Managed generation is off, so provider generation-quality evals don't apply. What
  matters instead is whether agents call the save tools correctly; no eval harness exists for that yet.

### 6. Model Flexibility — ✅ assessed

- Memory Bank's extraction model is configurable but Google-only. During the spike the provider rejected
  `gemini-2.5-flash` ("Gemini 2.5 models are not supported. Use `gemini-3.5-flash` instead."); the value
  was pinned to `gemini-3.5-flash` and made configurable via `MEMORY_BANK_GENERATION_MODEL`.
- Custom and open-source extraction models are not supported.
- The agent's own chat model is unaffected (any ADK-supported model). With managed generation off, this
  lock-in has no effect on the governed path.

### 7. Governance / CCPA — ✅ implemented

Memory Bank supports hard deletion natively. The `agentplatform` SDK exposes `delete(name=…)`,
filter-based `purge(…, force=…)` (with `force=false` as a staged preview), `list` / `get`, and
`revisions()` + `rollback(…)`.

The platform wraps deletion in governed operations:

| Scenario | Operation | Behavior |
|---|---|---|
| Customer "forget me" | `POST /api/v1/runtime/memory/forget` (`submit_candidates`) | Lists memories (authoritative `list`, filtered by immutable scope) and deletes each. With `householdId` it removes one member or cascades to the whole household. Verified live for the member scope. |
| Forget one value | `POST /api/v1/runtime/preferences/{attribute}/forget` | Deletes every stored version of one attribute at one scope; for health data also withdraws the consent. |
| Operator on-demand | `POST /api/v1/runtime/memory/purge` (`administer_memory`) | Matches organization memories by tier/attribute/topic; `dryRun` default. Verified live: previewed, then removed a topic across users. |
| Retention | `POST /api/v1/admin/organizations/{org}/retention/sweep` | Deletes values older than each schema's retention; expires unconfirmed members and pending consents. |

All deletions are audited. Memory Bank reads are eventually consistent, so an immediate count can lag a
just-written value; the end state is correct.

## Key decisions

1. **Managed generation is ungoverned** — disabling it and writing only explicit, topic-gated, or
   household-resolved values is how the platform controls what is retained.
2. **Versioned storage with native delete** — no field-level update (an update is a new fact), but hard
   delete, staged purge, and revision rollback exist.
3. **Gemini lock-in** applies only to Memory Bank's extraction model, which the platform doesn't use.
4. **No per-user memory browser** in the Cloud console; inspection is through the API (`resolve`, raw
   profiles) or Vertex Data Access audit logs.

## Outstanding work

- [ ] Deploy to the GCP Dev/Pilot landing zone; capture networking, firewall, and real billing.
- [x] Governed deletion: forget, purge, single-value forget, retention sweep, consent withdrawal.
- [ ] Map provider `429` to `503` + `Retry-After` (today it surfaces as HTTP 500).
- [ ] Add Cloud Trace instrumentation if tracing is required.
- [ ] Decide the eval strategy for agent memory behavior (tool-call precision/recall).
- [ ] (Optional) attach write-time `metadata` for native purge filters; await delete operations for
      hard-delete SLAs.

## Artifacts

- **Branches:** spike work on `feature/adk-dual-memory`; continued on
  `feature/dynamic-household-members`.
- **Runtime API:** see the [Control Plane API README](../apps/control-plane-api/README.md).
- **Spike commits:** overlay-drop fix `065da4f`; generation model pin `f280556`; topic-gated dynamic
  memory `2eff48e`; agent flow `38495b9`; memory-write logging `a4bbcbc`.
- **Tests:** `test_runtime_api.py`, `test_vertex_memory_store.py` (managed generation off,
  latest-per-topic), `test_preference_resolution.py` (confidence gate), `test_dynamic_household.py`.
- **Design docs:** [Dynamic Memory Topic Gating](dynamic-memory-topic-gating.md),
  [Vertex Memory Bank](vertex-memory-bank.md).
