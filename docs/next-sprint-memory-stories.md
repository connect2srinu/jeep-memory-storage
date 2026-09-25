# Next Sprint — Governed Memory Stories

Stories for the next sprint, checked against the current code on `feature/dynamic-household-members`.
Each item is tagged:

- **Verify** — already built; the story is to run the flow and confirm it.
- **Gap** — partly built; the story closes a specific gap.
- **Design** — not built; needs a design discussion before implementation stories are written.

| # | Area | Verify | Gap | Design |
|---|---|---|---|---|
| 1 | Privacy alignment — collect / don't-collect | 1.1 | 1.2, 1.3 | 1.4 |
| 2 | Adding a new attribute | 2.1 | 2.2, 2.3 | — |
| 3 | Cost and performance: extraction in vs outside the agent | — | — | 3.1 |
| 4 | Edge cases: restricted and irrelevant memory | 4.1 | 4.2, 4.3 | — |
| 5 | Evals and observability | 5.1 | — | 5.2, 5.3 |
| 6 | Confidence score for conflicts | 6.1 | 6.2 | 6.3 |
| 7 | Memory Bank load testing | — | 7.1, 7.2 | — |

---

## 1. Privacy alignment

### 1.1 Verify the current privacy controls — *Verify*

Built today:

- **Restricted content is blocked (400):** SSN (dashed), card, phone, email, credential words,
  weapons, discriminatory targeting.
- **Sensitive content must be user-directed (403 otherwise):** religion and health terms.
  - Code: `services/memory_classification.py`.
- **Topics:** dynamic memory only saves under approved topics, each with a sensitivity.
- **Health data:**
  - needs confirmation;
  - needs consent for a minor;
  - is refused for another adult.
- **Purpose limitation and retention:** an agent's purpose must be allowed by the schema; retention
  sweeps remove expired values.
- **Agent side:** the save order and "do not save" rules are in the memory agent's `INSTRUCTION`.

**Acceptance criteria**

- `python3 scripts/privacy_controls_demo.py --with-purpose-check` passes (26 checks at time of writing).
- The walkthrough in
  [privacy-controls-briefing.md](presentations/privacy-legal-review/privacy-controls-briefing.md)
  Part C is run once in the UI and matches the briefing.

### 1.2 Agree the include / exclude list with Legal — *Gap*

Today the "don't collect" rules are fixed patterns in code plus wording in each agent's instruction.
There is no signed-off list. The Legal briefing lists 7 open decisions, including whether normal
values may appear in decision logs and for how long those logs are kept.

**Acceptance criteria**

- A written list of what may be collected, what needs consent, and what must never be collected, approved by Legal.
- Each item says how it is enforced: platform rejection, agent instruction, or schema design.
- The 7 open decisions in the briefing are answered.

### 1.3 Close the screening gaps — *Gap* (after 1.2)

Each of these was run through `classify_content` and came back `normal` (accepted):

| Missed | Example |
|---|---|
| SSN without dashes | `my ssn is 123456789`, `123 45 6789` |
| Address, date of birth | `lives at 12 Main St`, `born 01/02/1990` |
| Government IDs | `passport X1234567`, `driver license D1234567` |
| Financial | `account number 12345678`, `pin 4821`, `credit score 550`, `earns 200k a year` |
| Credentials | `my pwd is hunter2` |
| Spelled-out numbers | `call me at five five five one two three four` |
| Sexual orientation, mental health, medication | `I'm gay`, `I have depression`, `on insulin` |
| Political views, immigration status | `votes republican`, `is undocumented` |

**Acceptance criteria**

- Every category on the agreed list (1.2) has a pattern or rule.
- There is a parametrized test per category, with positive and negative examples.
- The false-positive check still passes for ordinary preferences (e.g. `likes oat milk`).

### 1.4 Configurable exclusion list per domain — *Design*

Should the exclusion list be data (managed per domain in the admin console) instead of code? To
decide:

- who owns it;
- how changes are reviewed;
- whether a domain can loosen the platform-wide list, or only tighten it.

---

## 2. Adding a new attribute

### 2.1 Verify the new-attribute flow — *Verify*

Built today: **Govern & manage → Schemas → Create new version** → approve in **Approvals**. The agent
sees the new attribute in `writablePreferences` in its next session with no code change. Existing
values are kept.

**Acceptance criteria**

- Add an attribute to an existing schema.
- Start a new agent session, save a value to the new attribute, and resolve it in a later session.
- Earlier values are still returned.

### 2.2 Write the process and downstream-impact checklist — *Gap*

Today the guidance is one paragraph in [domain-onboarding.md](domain-onboarding.md#adding-preferences-later).
It does not cover:

- renaming, removing, or changing an attribute's data type (there is no migration);
- saved values keeping their original `schema_version` label;
- which schema wins when two schemas map the same attribute (no runtime precedence rule today);
- when a new attribute needs a privacy review (health or sensitive);
- that the agent picks up the new attribute from the snapshot, while evals (5.2) need updating.

**Acceptance criteria**

- A "Changing a schema" section or guide covering each point above.
- A checklist that a domain owner can follow.

### 2.3 Review new sensitive fields for existing read grants — *Gap*

Read access approved for another team covers the whole schema, including fields added later
(from the Shopping V1 → V2 analysis). A new health or sensitive attribute becomes readable by those
teams without anyone re-approving it.

**Acceptance criteria**

- Adding a health or sensitive attribute to a schema that has other teams' read grants requires those grants to be re-approved, or excludes the new field until they are.
- Covered by a test.

---

## 3. Cost and performance: extraction in vs outside the agent

### 3.1 Measure both approaches — *Design / spike*

Today extraction happens inside the agent: the model picks the tool and the value, and the Control
Plane validates. The written comparison recommends a hybrid:
[agent-flow.md](architecture/agent-flow.md) and slide 08 of the build-vs-buy deck.

There are no measured numbers.

**Acceptance criteria**

- Measured extra model tokens and latency per turn for:
  - (a) in-agent extraction (today);
  - (b) extraction outside the agent, e.g. managed generation or an async extractor after the session.
- Cost per 1,000 conversations for each.
- Includes the monitoring and eval cost that (a) needs (depends on 5.2 / 5.3).
- A recommendation with the numbers.

---

## 4. Edge cases: restricted and irrelevant memory

### 4.1 Verify existing edge-case coverage — *Verify*

Built today: tests for restricted, sensitive, health, another adult, and unapproved topics.

- `apps/control-plane-api/tests/test_memory_classification.py`
- `test_dynamic_household.py`
- `test_runtime_api.py`
- the privacy demo

**Acceptance criteria**

- All pass in CI.
- The memory-agent tests are added to CI (today they are not; see the reference architecture's gap list).

### 4.2 Tests for the screening gaps — *Gap*

Same cases as 1.3, tracked as tests. Can be merged into 1.3.

### 4.3 Irrelevant memory — *Gap*

Whether something belongs in memory is decided only by the model. The platform checks that the topic
is approved, not that the value fits it. For example, "training for a marathon" saved under the
approved topic `shopping` is accepted.

**Acceptance criteria**

- A set of irrelevant statements, run through the agent, that must not be saved.
- The run uses the eval harness (5.2).
- The rate of wrong saves is reported.

---

## 5. Evals and observability

### 5.1 Verify decision logging — *Verify*

Built today:

- **Control Plane:** logs a `memory_decision` event for every write. It includes key, schema version,
  level, data type, value version, sensitivity, reason, and a masked value.
- **Memory agent:**
  - logs `agent_memory_decision` for each save and for statements it chose not to save
    (`record_memory_decision`);
  - sends an `X-Correlation-ID`, so both lines share one `correlation_id`.
- **Audit and metrics:** audit events for writes and deletes; request counts by endpoint (in memory only).

**Acceptance criteria**

- For one save in the dev UI, the agent and Control Plane lines are found by the same `correlation_id`.
- Health and restricted values show as `***`.

### 5.2 Memory eval harness — *Design*

Nothing exists. Proposal to discuss:

- a set of test conversations with the expected outcome per statement: save (which key / topic),
  don't save, or reject;
- run against the agent, scoring accuracy, relevance, and rejection rate;
- rule-based checks vs an LLM judge;
- when it runs: per PR, nightly, or before a prompt or model change.

### 5.3 Metrics, dashboards, and alerts — *Design*

Log-based metrics built from the decision events:

- save, reject, decline, and needs-confirmation rates by domain and key;
- restricted-content hits;
- Memory Bank latency and errors.

To agree: dashboards, alert thresholds, and log retention (ties to 1.2).

---

## 6. Confidence score for conflicts

### 6.1 Verify confidence handling at read time — *Verify*

Built today: the resolver supports the `HIGHEST_CONFIDENCE` strategy. It drops dynamic and inferred
values below `minimum_confidence`, which defaults to 0.7 and is set per domain in memory setup.

- Code: `services/preference_resolver.py`.

**Acceptance criteria**

- Write two dynamic values with confidence 0.9 and 0.5 through the API.
- With threshold 0.7, only the first is returned.

### 6.2 Confidence is never set — *Gap*

- The memory agent never sends a confidence, so every dynamic value is 1.0 and the threshold never filters anything.
- Canonical saves (`ExplicitPreferenceUpdate`) have no confidence field; a new value overwrites the old one.

**Acceptance criteria**

- Depends on 6.3.
- The agent passes a confidence where the design says it should.
- A test shows a low-confidence value being filtered.

### 6.3 Where confidence comes from and what a conflict is — *Design*

To decide:

- **The source of the score.** The model's own estimate is unreliable. Alternatives: explicit vs
  inferred, confirmation, repetition.
- **What counts as a conflict:**
  - two agents saving different values;
  - the customer contradicting themself;
  - an inferred value against a stated one.
- **Whether canonical values should keep history** instead of being overwritten.

---

## 7. Memory Bank load testing

### 7.1 Load test against a real Memory Bank at target scale — *Gap*

What exists:

- **Script:** `scripts/memory_load_test.py` measures throughput, latency, and a cost estimate. It runs
  writes (dynamic or canonical) and resolves through the runtime API.
- **Runs so far:** only locally; the quota limits were observed.
- **Quota:** the default Vertex quota is 300 reads/min and 100 writes/min per project and region. A
  10× raise is agreed with Google.
- **Not covered by the script:** household scopes (a resolve that also reads member snapshots) and
  mixed read/write traffic.

**Acceptance criteria**

- Run in the landing-zone project against a real Memory Bank, with the raised quota.
- **Workload:**
  - a realistic read/write mix across many users;
  - household scopes included;
  - a ramp to the quota and past it;
  - a soak run of at least 1 hour.
- **Report:**
  - throughput at the quota;
  - p50 / p95 / p99 latency for resolve and write;
  - error rate by status;
  - billed cost per 1,000 operations from actual billing, not the price model.
- **Findings:** results added to [memory-bank-assumption-validation.md](memory-bank-assumption-validation.md)
  (MB-15, MB-18) and the build-vs-buy gap analysis.
- Fix the existing `BLE001` lint error in the script.

### 7.2 Handle quota exhaustion cleanly — *Gap*

A provider `429` currently surfaces as HTTP 500. The 7.1 run will hit it.

**Acceptance criteria**

- A Memory Bank `429` returns `503` with `Retry-After`.
- The agent's tools tell the customer the save did not happen and do not retry in a loop.
- Covered by a test with the mock store.
