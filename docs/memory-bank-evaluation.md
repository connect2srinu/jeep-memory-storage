# Evaluating Vertex AI Memory Bank for Shared Agent Memory

**Purpose:** explain how we are evaluating Google's Vertex AI Memory Bank as the shared memory for
agentic commerce agents (KSA, Cooklist and those that follow), and what we recommend.
**Read time:** about 6 minutes.

## Background

Agents like KSA need to remember a customer's preferences across conversations and channels: the
store they shop at, their organic brand, their diet, their allergies. Several agents need some of
the same facts, and all of it must follow our privacy standards.

We first designed a custom solution: our own store, with a batch pipeline that extracts memories
after each conversation. When Memory Bank became generally available, we evaluated it against that
design. We evaluate on **three criteria**:

1. **Extraction** — where memories are pulled out of the conversation.
2. **Storage** — where memories are kept.
3. **Governance** — how sharing between agents stays controlled and compliant.

---

## 1. Extraction: where should memory extraction happen?

"Extraction" means turning what the customer says into a saved preference, for example "I always
buy Simple Truth" becomes `organic_brand = Simple Truth`.

| Option | How it works | Strengths | Weaknesses |
|---|---|---|---|
| **A. Custom batch pipeline** | After each session, a pipeline (Pub/Sub, a writer service, an LLM call) reads the conversation and decides what to save | Central control of extraction quality; no extra work during the chat | Many components to build and run; memories appear only after the session; can't ask the customer to confirm sensitive data such as allergies |
| **B. Memory Bank managed extraction** | Conversations are sent to Memory Bank, and its own model extracts and consolidates memories | No extraction code to write; consolidation built in | Less control over what gets saved; sensitivity and schema rules are hard to apply *before* storage; extra model cost per extraction |
| **C. Agent-level extraction, governed by the control plane** | The agent's own model decides, during the conversation, to save a preference through a tool. Our control plane checks every write before it reaches storage | No extra pipeline; real time; the agent can ask the customer to confirm; every write is checked against schema, sensitivity and consent rules | Quality depends on each agent's model and prompt, so it needs evaluations; a small token overhead per turn |

**Recommendation: Option C**, which is built and working today. Option A remains useful later for
inferred, non-sensitive preferences (for example reorder cadence), feeding the same governed write
path. We keep Memory Bank's managed extraction (B) switched off, so that nothing is stored without
passing our checks.

---

## 2. Storage: PostgreSQL or Memory Bank?

| | **Memory Bank** | **PostgreSQL (custom)** |
|---|---|---|
| Version history of each value | **Out of the box.** Every change is kept, with revision history | Build history tables and versioning logic |
| Per-customer scoping | **Out of the box.** Memories are keyed to the customer; no cross-customer reads | Build and index it |
| Retrieval | **Out of the box**, including semantic search | SQL queries; semantic search needs extra work (pgvector) |
| Scaling, durability, operations | **Managed by Google**; no database to run | Our team runs capacity, upgrades, backups, failover and on-call |
| Expiry and deletion | Supported; our platform enforces retention by sensitivity | Build it |
| Ad-hoc queries and reporting | Limited; analytics need an export | Full SQL |
| Transactions and point-in-time restore | Not customer-controlled | Native |
| Latency and throughput | API calls; bounded by the Memory Bank quota | Milliseconds; bounded by instance size |

**What we get out of the box with Memory Bank:** versioning and revision history, per-customer
scoping, retrieval and semantic search, managed scale and durability, and no database operations.
With PostgreSQL we would build and run all of these ourselves.

**What to watch:**
- **Quota.** The default is 300 reads and 100 writes per minute per project and region. A 10×
  increase has been agreed with Google; a load test will confirm what we need.
- **Latency.** Each read and write is an API call, so it is slower than a local database.
- **Backup and restore** are managed by Google, not by us.

**Recommendation:** store memory **values** in Memory Bank. Keep the **governance data** (schemas,
agents, approvals, consent records, audit) in PostgreSQL, where it already lives.

---

## 3. Governance: how do we enforce rules while sharing memory?

Memory Bank stores data; it doesn't decide who may see it. That is the job of our **control
plane**, a service that sits between every agent and Memory Bank.

**Ownership.** Each agent's team declares the preferences it owns, as a schema. There are three
models:

| Agent | Model | What it does |
|---|---|---|
| KSA | Private | Keeps its own preferences; shares nothing unless approved |
| Cooklist | Hybrid | Keeps its own, and reads selected KSA preferences |
| Meal Planner | Consumer only | Keeps nothing; reads approved preferences only |

**Sharing by approval.** An agent requests specific preferences, to read or to read and write. The
owning team approves or denies **each preference**. An approved write saves into the owner's data,
so there is always one value and never a copy.

**Rules the platform enforces on every read and write:**
- **Sensitivity:** each preference is non-sensitive, sensitive or restricted. Sensitive data is
  saved only when the customer states it; restricted data is never stored.
- **Health data:** saved only after the customer confirms, with a consent record. It can't be
  written by another agent.
- **Purpose:** an agent can only use data for a purpose the schema allows; for example,
  advertising never gets health data.
- **Retention and deletion:** values expire by sensitivity, and a customer's memory can be deleted
  on request.
- **Audit:** every save or refusal is logged, with sensitive values masked.

**Schema changes** only add preferences, so existing approvals keep working. A new preference is
not shared until it is approved.

---

## Recommendation

| Criterion | Choice |
|---|---|
| Extraction | Agent-level, checked by the control plane; batch later for inferred, non-sensitive data |
| Storage | Memory Bank for memory values; PostgreSQL for governance data |
| Governance | Control plane: ownership, per-preference approvals, privacy rules, audit |

This gives us the managed storage features we would otherwise build, and keeps privacy and sharing
decisions in our hands.

## Next steps

1. Provision non-production infrastructure.
2. Load test at the real Memory Bank quota.
3. Build the MCP server for agents to access memory.
4. Finalize agent authentication and authorization for production.
5. Agree the privacy tier mapping and retention periods with the Privacy Office.
