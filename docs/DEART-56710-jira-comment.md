**Spike findings — Vertex Memory Bank POC** (details in Confluence: "SPIKE: Validate Vertex Memory Bank POC & Technical Integration Gaps")

Hardened the POC and exercised it against a **real** Vertex Memory Bank Agent Engine (project `e2eml-222003`, `us-central1`). Status per acceptance criterion:

- ✅ **Architecture Parity** — ADK `DatabaseSessionService` → Postgres/Cloud SQL for sessions; shared long-term persisted in Memory Bank via the control plane. Demoed end-to-end.
- ⚠️ **Data Streaming** — Memory Bank ingests **application events** (`ingest_events`), not Cloud SQL CDC. Mechanism validated, but we **disabled managed generation** on purpose (it persists ungoverned memories) and write explicitly instead.
- ❌ **Environment Configuration** — validated from a local Docker harness against real Vertex; **GCP Dev/Pilot landing-zone deploy (networking, firewall, billing) still outstanding**.
- ✅ **Data Modeling** — system differentiates **canonical (explicit)**, **dynamic (topic-gated)**, and **unstructured semantic** memory; the last is disabled by design. Gates verified live (unapproved topic → 403, sensitive → 400, low-confidence dropped). Also found + fixed a read bug dropping all but the newest value.
- ⚠️ **Observability & Evals** — structured create/update **logging added and verified** (Cloud Logging–ready); **Cloud Trace not wired**; **no eval harness** (managed generation is off, so generation evals N/A).
- ✅ **Model Flexibility** — Memory Bank extraction model is **Gemini-only**: `gemini-2.5` rejected, `gemini-3.5-flash` required; **no custom/open-source models**. Lock-in applies to Memory Bank extraction, not the agent chat model.
- ✅ **Governance/CCPA** — hard deletion is supported **out of the box** and now **implemented + tested live**: `POST /memory/forget` (user right-to-be-forgotten, deletes all their memories) and `POST /memory/purge` (operator on-demand across the org by tier/attribute/topic, capability-gated, `dryRun` preview). Both audited. Live: forget deleted both tiers; purge removed a topic across users. Caveat: Memory Bank reads are eventually consistent, so immediate counts can lag (end state correct).

**Top open items:** (1) landing-zone deploy + real billing, (2) Cloud Trace, (3) eval strategy. (Deletion/CCPA now done.)

**Code:** branch `feature/adk-dual-memory` (pushed). Endpoints: `/preferences/resolve`, `/preferences/{attribute}`, `/memory/dynamic`, `/profiles`.
