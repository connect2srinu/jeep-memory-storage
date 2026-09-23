**Spike findings — Vertex Memory Bank POC** (status as of 2026-09-23; details in Confluence: "SPIKE: Validate Vertex Memory Bank POC & Technical Integration Gaps")

Exercised the POC against a **real** Vertex Memory Bank Agent Engine (project `e2eml-222003`, `us-central1`). Status per acceptance criterion:

- ✅ **Architecture Parity** — ADK `DatabaseSessionService` → Postgres/Cloud SQL for sessions; shared long-term memory in Memory Bank via the Control Plane runtime API. Demoed end to end.
- ✅ **Data Streaming (clarified)** — Memory Bank ingests **application events** (`ingest_events`), not Cloud SQL CDC. Mechanism validated, then **managed generation disabled on purpose** (it persists ungoverned memories); all long-term memory is written through governed calls.
- ❌ **Environment Configuration** — validated from a local Docker harness against real Vertex; **GCP Dev/Pilot landing-zone deploy (networking, firewall, billing) still outstanding**.
- ✅ **Data Modeling** — canonical (schema-bound), dynamic (topic-gated), and unstructured (disabled) memory; now also household-shared and per-member scopes with runtime member resolution, confirmation turns, and a consent ledger for health data. Gates verified live (unapproved topic → 403, restricted content → 400, low-confidence dropped). Found and fixed a read bug that dropped all but the newest value.
- ⚠️ **Observability & Evals** — structured `memory_write` / `memory_deletion` / request logging (Cloud Logging–ready); **Cloud Trace not wired**; **no eval harness** for agent memory behavior.
- ✅ **Model Flexibility** — Memory Bank's extraction model is **Gemini-only** (`gemini-2.5` rejected, `gemini-3.5-flash` required); no custom/open-source extraction models. Doesn't affect the governed path because managed generation is off.
- ✅ **Governance/CCPA** — hard deletion is native and implemented: `POST /memory/forget` (user, member, or household with cascade), single-value forget, `POST /memory/purge` (operator, capability-gated, `dryRun` preview), a retention sweep, and deletion on consent withdrawal. All audited. Memory Bank reads are eventually consistent (end state correct).

**Top open items:** (1) landing-zone deploy + real billing, (2) map provider 429 to 503 + Retry-After, (3) Cloud Trace, (4) eval strategy for agent save behavior.

**Code:** spike on `feature/adk-dual-memory`; continued on `feature/dynamic-household-members`.
