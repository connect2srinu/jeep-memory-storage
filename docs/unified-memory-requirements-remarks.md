# Unified Memory for Agentic Commerce — proposed remarks

Remarks to paste into the requirements page, row by row, in the page's own layout. Each remark
starts with a status:

- **Implemented** — built and tested in the governed-memory platform.
- **Partial** — part is built; the remark says what is missing.
- **Not implemented** — not built; the remark says what it would take.
- **Recommend change** — the requirement should be reworded or narrowed.
- **Concern** — a security, privacy, or feasibility issue to raise before implementing.

"The platform" below means the governed-memory control plane in front of Vertex Memory Bank.

---

## Assumptions (comments — the page has no remarks column here)

| # | Assumption | Comment |
|---|---|---|
| 1 | Phase 1 = KSA, Cooklist, GECX | Agreed. KSA and Cooklist are tested end to end; GECX has not been onboarded yet. |
| 2 | No off-property agents | Agreed. |
| 3 | Profile-level dietary preferences disabled | Agreed. |
| 4 | Consent / purpose disclosure at agent level | **Concern:** memory is shared, so a purpose disclosed by one agent must cover every agent that reads the value. The platform already limits use by purpose (each agent declares one; each schema lists the purposes allowed). Align the disclosure text with those purposes. |
| 5 | Memory keyed by individual GUID | **Implemented:** "Per User" memory is keyed by organization + customer ID, with no cross-customer reads. Household support exists but is optional and not needed for Phase 1. |
| 6 | Batch/offline summarization instead of per-turn inference | **Recommend change:** keep explicit and health preferences in-session (the agent must ask the customer to confirm health data, which can't happen after the session). Use batch only for inferred, non-sensitive preferences. Today extraction is in-session. Batch results can be submitted through the existing events API. |
| 7 | Privacy Office review for material changes | Agreed. Decision logs and the audit trail support the review. |
| 8 | Fallback/retry at agent level | **Partial:** when Memory Bank is over quota, the platform currently returns HTTP 500. It should return 503 with Retry-After so agents can retry correctly (planned story). |
| 9 | No confidence decay | Agreed. |
| 10 | GECX one-time data transfer | **Concern:** a bulk load goes through the same Memory Bank write quota (default 100 writes/min per project and region). Plan a throttled import or a temporary quota raise. The data must also be classified and screened like any other write. |
| 11 | Concurrent writes are an edge case; no queue | Agreed for Phase 1. **Known limit:** two platform instances writing the same customer at the same moment can produce duplicate version numbers, and the last write wins. |

---

## 1.1 Memory Capture & Storage

| Area | Acceptance Criteria | Remarks |
|---|---|---|
| Explicit Preferences | Capture preferences a customer directly states or confirms (e.g. dietary restriction, favorite items, brand/size preferences) | **Implemented.** Agents save stated or confirmed preferences into governed attributes. Health data (e.g. allergies) is saved only after the customer confirms, and a consent record is kept. |
| Implicit / System-Inferred Preferences | Infer non-sensitive preferences from behavior (repeat purchases, reorder cadence). Sensitive data must never be inferred — only stored if explicitly provided | **Partial.** The platform accepts inferred values, but refuses an inferred value that is sensitive and blocks restricted content (SSN, card, weapons…). There is no job that infers from purchase behavior; it needs a purchase-history source. **Concern:** the sensitive-content check is pattern-based and misses cases such as an SSN without dashes, sexual orientation or mental health. The list of what to detect must be agreed with Privacy. |
| Storage Model | Shared customer ontology; optional app-specific ontology; key-value per GUID & app; hierarchical lookup (GUID, GUID + app_id + key, GUID + key); no cross-GUID reads; static and dynamic LLM-generated keys; off-property alias ID | **Partial.** Implemented: the shared ontology as governed schemas owned by a domain; app-specific preferences (an agent's own schema); consumer-only agents; no cross-customer reads. Not implemented: lookup by app_id or single key (agents read the customer's whole approved snapshot), and the off-property alias (out of scope). **Recommend change:** allow LLM-generated keys only within approved topics (implemented this way). Open-ended keys can't be classified or governed. |
| Memory capture | Ontology defined by CX stakeholders; LLMs can't change the structure; agents read/write the shared layer with an audit trail; read at session start; batch update after session via LLM; KSA reuses the eval trigger | **Partial.** Implemented: the ontology is owned and defined by stakeholders, and the LLM can't add or change attributes; memory is read at session start; agents read, and optionally write, other agents' preferences only when the owner approves each preference; every write is logged. Not implemented: a query/UI for a value's history (it's kept in Memory Bank and the logs, but not exposed), and the post-session batch update (see Assumption 6). |
| Conflict resolution (text cut off) | "Any sort of conflict resolution between agent memory and customer …" | **Partial.** Resolution policies exist: source priority, domain priority, most recent and highest confidence, plus schema precedence. Confirm the full criterion; conflicts between agent memory and customer-stated values need a documented rule, e.g. customer-stated always wins. |
| Authentication & Authorization | Shared memory store enforces authentication and authorization for calling agents | **Implemented.** Agents authenticate with Google ID tokens (the agent-ID header is local development only); access is authorized per agent, per schema and per preference (read or read + write); administrators use Entra/IAP roles. |
| MCP server | MCP server to access the shared memory store | **Not implemented.** Agents use the REST API or the Python client today. A thin MCP server over read/save/forget is small. **Concern:** it must use the same agent authentication, and must not expose administrative operations such as purge or approvals. |

## 1.2 Provenance, Confidence & Retention

| Area | Acceptance Criteria | Remarks |
|---|---|---|
| Source Tagging | Every record tags a Memory Source Category: Chat History, User Directed, or System Inferred | **Partial.** Every write carries user-directed or inferred. **Recommend change:** drop "Chat History" as a memory source. The objective excludes raw session/chat dumps, and chat-derived facts are either user-directed or inferred. |
| Confidence | Every inferred record carries a confidence/support level | **Partial (low priority, agreed).** Dynamic memory stores confidence, and reads can filter below a threshold or rank by confidence. Agents don't send a score yet, and canonical preferences have none. |
| Retention & Decay | Every record is assigned a creation timestamp and a decay/expiry rule at ingestion | **Implemented.** Values are timestamped. Retention is set per schema and per topic, with platform maximums by sensitivity (3 years normal, 2 years sensitive/health). A sweep deletes expired values. **Concern:** this conflicts with the NFR "Data retention: infinite, no expiry"; one of the two must change. |

## 1.3 Privacy Classification & Governance

| Area | Acceptance Criteria | Remarks |
|---|---|---|
| Data Classification | Every record classified as Global, Personal, Sensitive Personal, or Restricted Personal per the Privacy Standard | **Partial.** Each preference is classified non-sensitive, sensitive or restricted, with a separate health-data flag, and every value's content is also scanned. **Recommend change:** agree a mapping from the Standard's four tiers to these levels with Privacy. "Global" (non-personal) data likely isn't customer memory at all. |
| Restricted Data Approval | Restricted Personal Memory Data requires Privacy Office approval prior to storage | **Not implemented — Concern.** Today "restricted" means never stored, which is stricter. Storing restricted data after approval needs a Privacy Office approval workflow per attribute, plus audit. Recommend keeping "never stored" in Phase 1 unless a specific restricted use case is approved. |
| Purpose Limitation | Memory used only for the purpose disclosed to the customer at capture | **Implemented.** Each agent declares a purpose, and each schema lists its allowed purposes. Access is refused for any other purpose, and advertising use is never allowed for health or per-person data. The customer-facing disclosure itself is at agent level (Assumption 4). |

## 1.4 Customer Transparency & Control

| Area | Acceptance Criteria | Remarks |
|---|---|---|
| Disclosure | Customer-facing disclosure of what is remembered and why | **Not implemented in the platform** (handled via the CCPA process). On "app memory or global memory?": recommend global, because memory is shared across agents, so the disclosure should cover every agent that can read a value. |
| Access & Deletion (DSAR) | Support DSAR retrieval and deletion of a customer's memory records | **Partial.** Deletion is implemented: forget everything for a customer, or one value, plus an admin purge. Retrieval is not: there is no single export of everything held about a customer across all schemas, which the CCPA process will need (small to build). **Known gap:** forgetting a household currently keeps its member roster and withdrawn consent records. |
| Editing | Customer-initiated update/removal of preferences | **Implemented** via chat (save and forget). An agent approved to write another agent's preference can also update it. |
| Disabling/Enabling | Chat as anonymous user | **Not implemented.** An anonymous user has no GUID, so nothing is stored by design. For a signed-in "don't save this session", recommend a flag the platform enforces by refusing writes, not just an instruction in the prompt. |
| Account deletion | Delete all associated user memory when user deletes their digital account | **Concern.** GUID decoupling removes the link, but the memory itself stays stored in Memory Bank under that GUID. Recommend calling the platform's forget-customer operation from the account-deletion event, so the data is actually deleted. |

## 1.5 Preference Categories

| Area | Acceptance Criteria | Remarks |
|---|---|---|
| Food Purchase Preferences | Dietary restrictions, brand/size/format preferences, favorite items | **Implemented** as configurable catalog preferences (e.g. organic brand, dietary restriction, preferred size). Allergies are classified as health data, separate from dietary choices. |
| Agent Interaction Preferences | Communication style, channel, interaction preferences | **Supported by configuration:** add them as catalog preferences or approved topics. None are defined yet. |
| Customer Touchpoint Interactions | Preferences tied to ordering touchpoints (pickup, delivery, store) | **Supported by configuration.** Per-store values are possible with the "Per User + Store" scope. |

## 1.6 Cost Visibility & Control

| Area | Acceptance Criteria | Remarks |
|---|---|---|
| Cost Attribution | Costs captured at GCP project/CX level; per-agent attribution not in scope | Agreed. Memory Bank, Cloud SQL and Cloud Run bill to the project. LLM tokens for extraction bill where the agent runs; a batch job would add its own. Per-agent attribution could come from the decision logs later. |
| Apptio Integration | Storage costs reported via Apptio dashboard | **Not in scope of the platform code.** It depends on the GCP billing export feeding Apptio. |

## Out of scope (Phase 1) — comments

| Item | Comment |
|---|---|
| Household-level / multi-person identity resolution | The platform already supports household and member memory, but it is optional; Phase 1 can use Per User memory only. |
| Preference center | Note that DSAR retrieval (1.4) still needs an export even without a preference center. |
| All other items | Agreed. |

---

## 2. Non-Functional Requirements

**Overall concern:** these targets are written for a Cloud SQL / PostgreSQL memory store. In the
current design, memory values live in **Vertex Memory Bank**; Postgres holds only the platform's
configuration (schemas, agents, approvals, consents). Each target needs to say which store it
applies to.

| Category | Requirement | Target/Metric | Remarks |
|---|---|---|---|
| Performance | Latency | Read ≤ 10 ms, Write ≤ 20 ms | **Concern.** Achievable only for the Postgres configuration store. Memory reads and writes are Memory Bank API calls (a read is one call per schema; a save is two calls), so 10–20 ms isn't realistic. Re-baseline from the load test. |
| Performance | Throughput | 10 tx/sec per agent per region | **Concern.** The default Memory Bank quota is 300 reads/min (5/sec) and 100 writes/min per project and region. Even the agreed 10× raise (50 reads/sec) is tight for three agents at 10 tx/sec. |
| Resiliency | Zonal Failover | ≤ 2 min | Achievable for the Postgres store with Cloud SQL HA. Memory Bank is Google-managed: request Google's availability/failover statement. |
| Resiliency | RPO | 0 sec (zonal) | As above: Cloud SQL HA for configuration; Memory Bank per Google SLA. |
| Resiliency | RTO | ≤ 12 h from cross-region backup | Achievable for Cloud SQL. **Concern:** Memory Bank has no customer-controlled backup or restore, and no export/restore tooling exists yet. |
| Resiliency | Data Durability | HA, 7-day PITR, daily backups | Cloud SQL: yes. Memory Bank: no point-in-time recovery; confirm Google's durability terms. |
| Scalability | Vertical Scaling | 200 tx/sec in 1 hour | **Concern.** Cloud Run and Cloud SQL can scale, but 200 tx/sec is well above the Memory Bank quota, even raised. This is the main scaling risk. |
| Security | Data Encryption | TLS 1.2+; Google keys at rest; API keys encrypted | **Implemented** by GCP defaults. **Recommend change:** no static API keys. Agents use short-lived Google ID tokens. |
| Security | Access Control | VPC private IPs, IAM roles | **Partial.** Platform access is IAM-authenticated. Memory Bank is reached through Google APIs with a service account. Confirm the private networking (Private Google Access / VPC-SC) in the landing zone. |
| Security | Auditability | Admin audit logs 90 days | **Partial.** Admin actions are written to an audit table with no retention rule yet. Cloud Audit Logs also apply. Add the 90-day rule. |
| Security | Data Isolation | Data is isolated by agent | **Recommend change.** This contradicts shared memory. Suggest: "Data is isolated per customer; access is isolated per agent by approved grants (per preference)". That is what is implemented. |
| Reliability | Error Rate | ≤ 0.01% | **Concern.** Under load, quota rejections would exceed this; today they surface as HTTP 500. Needs 503 + retry and the quota raise. |
| Reliability | Data Integrity | ACID | **Partial.** ACID holds within Postgres. Saving to Memory Bank and recording it in Postgres is not one transaction. Also, a known issue: the platform commits to Postgres just after it responds. |
| Maintainability | Monitoring | Alerts for failover, replication lag, CPU | **Not implemented.** Replication lag doesn't apply to Memory Bank. Propose alerts on Memory Bank latency, errors and quota, plus save/refuse rates from the decision logs. |
| Maintainability | Backup and Restore | ≤ 1 hr for 50 GB | Cloud SQL configuration store only. Memory Bank data can't be restored this way (see RTO). |
| Data Retention | Data retention | Infinite, no expiry | **Concern.** Conflicts with 1.2 (expiry at ingestion) and likely with the Privacy Standard. The platform enforces maximum retention by sensitivity. Recommend a finite retention per tier, agreed with Privacy. |
