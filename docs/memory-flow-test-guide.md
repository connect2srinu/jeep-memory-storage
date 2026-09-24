# Memory Flow Test Guide

API-level checks for the governed memory flows: canonical preferences, dynamic topics, sensitivity
classification, deletion, and load. For the household flows (runtime members, confirmation, consent,
merge, move) and for testing everything from the UI, use
[Household Memory — End-to-End UI Guide](dynamic-household-test-guide.md).

Three ways to test:

- **A. Automated** — pytest against the mock store. Deterministic; covers every flow.
- **B. Example script** — `scripts/memory_flow_examples.py` against a running stack.
- **C. Manual** — `curl` against the runtime API, and prompts in the agent dev UI.

---

## A. Automated tests

From the repository root:

```bash
PYTHONPATH=apps/control-plane-api/app:apps/control-plane-api/tests .venv/bin/python -m pytest -q apps/control-plane-api/tests
```

Focused suites:

| Suite | Covers |
|---|---|
| `test_runtime_api.py` | resolve, canonical writes, dynamic topic gating, forget/purge, capabilities |
| `test_memory_classification.py` | restricted / sensitive / normal classification |
| `test_dynamic_household.py` | household root creation, member proposal and matching, health consent, merge/move/forget, purpose and retention |
| `test_household_identity.py` | name normalization, matching scores, relationship guard |
| `test_household_scope.py` | scope plumbing and store delete/purge |
| `test_preference_resolution.py` | resolution strategies and confidence gate |
| `test_vertex_memory_store.py` | Vertex adapter against a fake client (managed generation off, overlays) |

Agent client tests: `(cd apps/memory-agent && .venv/bin/python -m pytest -q tests)`.

---

## Setup for B and C

1. Start the stack: `docker compose -f docker-compose.yml -f docker-compose.devui.yml up -d --build --wait`.
2. Create a setup in the Admin Console (see [Guided Memory Setup](guided-memory-setup.md)) with:
   - a **Per User** scope and at least one custom preference, e.g. `grocery.preferred_store`;
   - dynamic memory enabled with approved topics, e.g. `shopping` (non-sensitive), `fulfillment`
     (non-sensitive), and `wellness` (sensitive);
   - an agent with `READ_WRITE` on its owned schema.
3. Export the names you used:

```bash
export API=http://localhost:8080 AGENT=grocery-agent DOMAIN=grocery
```

---

## B. Example script

Uses a throwaway user, checks canonical writes, topic gating, restricted-content blocking, the
sensitive-plus-source rule, per-topic sensitivity, what resolve returns (`sensitivity`, `memorySource`,
`approvedTopicDetails`), and deletion, then cleans up with `forget`:

```bash
python3 scripts/memory_flow_examples.py --base "$API" --agent "$AGENT" --domain "$DOMAIN"
```

---

## C. Manual checks

### Canonical preference

```bash
curl -s -X PUT "$API/api/v1/runtime/preferences/$DOMAIN.preferred_store" \
  -H "Content-Type: application/json" -H "X-Agent-ID: $AGENT" \
  -d "{\"scope\":{\"userId\":\"u1\",\"domain\":\"$DOMAIN\"},\"value\":\"Kroger\"}"
```

**Expected:** `{"status":"updated","reference":"…:$DOMAIN.preferred_store","profileVersion":1}`.

### Dynamic topics

| Case | Body (`POST /api/v1/runtime/memory/dynamic`) | Expected |
|---|---|---|
| Approved topic | `"topic":"shopping","value":"big shop Sunday mornings"` | 200 `accepted` |
| Unapproved topic | `"topic":"gardening","value":"loves tomatoes"` | 403 — topic not approved |

```bash
curl -s -X POST "$API/api/v1/runtime/memory/dynamic" \
  -H "Content-Type: application/json" -H "X-Agent-ID: $AGENT" \
  -d "{\"scope\":{\"userId\":\"u1\",\"domain\":\"$DOMAIN\"},\"topic\":\"shopping\",\"value\":\"big shop Sunday mornings\",\"source\":\"user_directed\"}"
```

### Sensitivity classification

The effective tier is `max(declared tier, content scan)`.

| Case | Request | Expected |
|---|---|---|
| Restricted content (PII, weapons, discriminatory targeting) | `topic:"shopping"`, value `"my SSN is 123-45-6789"` | 400 — blocked on every write path |
| Sensitive + inferred | `topic:"wellness"`, `source:"inference"`, value `"walks daily"` | 403 — only user-directed sensitive memories are stored |
| Protected class + inferred | `topic:"shopping"`, `source:"inference"`, value `"user is Muslim"` | 403 |
| Sensitive + user-directed | `topic:"wellness"`, `source:"user_directed"`, value `"walks daily"` | 200 — stored and tagged sensitive |

The agent always writes `source: user_directed`, so the inference cases are reachable only through the
API.

### Resolve

```bash
curl -s -X POST "$API/api/v1/runtime/preferences/resolve" \
  -H "Content-Type: application/json" -H "X-Agent-ID: $AGENT" \
  -d "{\"scope\":{\"userId\":\"u1\",\"domain\":\"$DOMAIN\"},\"sessionId\":\"s1\",\"includeProvenance\":true}"
```

Check `preferences` (with `sensitivity` and, for dynamic entries, `memorySource`), `writablePreferences`,
`writablePreferenceDetails`, `approvedTopics`, and `approvedTopicDetails`.

### Deletion

| Case | Request | Expected |
|---|---|---|
| Forget one value | `POST /preferences/{attribute}/forget` with the user scope | that value only |
| Forget a user | `POST /memory/forget` with `{"userId":"u1"}` | every memory in that user scope |
| Forget a household member / household | `POST /memory/forget` with `householdId` (+ `memberId`) | one member, or the household and all its members |
| Purge by topic or attribute | `POST /memory/purge {"topic":"shopping","dryRun":true}` | lists matches, deletes nothing; drop `dryRun` to delete (needs `administer_memory`) |

```bash
curl -s -X POST "$API/api/v1/runtime/memory/forget" \
  -H "Content-Type: application/json" -H "X-Agent-ID: $AGENT" \
  -d "{\"scope\":{\"userId\":\"u1\",\"domain\":\"$DOMAIN\"}}"
```

With the Vertex backend, reads are eventually consistent: an immediate resolve after a write or delete
can lag, but the end state is correct.

### Dev-UI prompts

Start the [memory agent](../apps/memory-agent/README.md) dev UI with your agent and domain, then:

| # | Prompt | Expected (Events / trace panel) |
|---|---|---|
| 1 | "I always shop at Kroger." | `save_preference("<domain>.preferred_store", …)` → 200 |
| 2 | "Remember I do a big shop early Sunday mornings." | `remember_dynamic_preference("shopping", …)` → 200 |
| 3 | "Remember to leave deliveries at the back door." | `remember_dynamic_preference("fulfillment", …)` → 200 |
| 4 | "Remember I walk daily for my wellness routine." | stored (user-directed), tagged sensitive |
| 5 | "Remember I love gardening tomatoes." | declined — not an approved memory type |
| 6 | "Remember my phone number is 555-123-4567." | tool returns 400 — blocked |
| 7 | "Remember I wish I could bring my guns into the store." | tool returns 400 — blocked |
| 8 | "What are my preferences?" | answered from the injected snapshot |
| 9 | New session → "What do you know about my shopping habits?" | recalled from the resolved snapshot |

---

## Load and cost benchmark

`scripts/memory_load_test.py` runs a configurable number of writes and reads, reports throughput and
latency (avg / p50 / p95 / p99), and computes a cost estimate from unit prices you supply. It uses only
the standard library and forgets its test users at the end.

```bash
# 500 writes + 500 reads across 50 users, 16 concurrent, with sample unit prices
python3 scripts/memory_load_test.py --base "$API" --agent "$AGENT" --domain "$DOMAIN" \
  --writes 500 --reads 500 --users 50 --concurrency 16 \
  --price-per-write 0.00002 --price-per-read 0.000005

# canonical write path (discovers a writable attribute if --attribute is omitted)
python3 scripts/memory_load_test.py --write-mode canonical --writes 200
```

Key flags: `--writes`, `--reads`, `--users`, `--concurrency`, `--rate` (ops/sec throttle),
`--write-mode dynamic|canonical`, `--topic` / `--attribute`, `--price-per-write` / `--price-per-read`,
token prices `--price-in-per-m` / `--price-out-per-m` with `--tokens-in-*` / `--tokens-out-*`,
`--no-cleanup`, and `--base` / `--agent` / `--domain`.

Against Vertex, the Memory Bank read-requests-per-minute quota is the limit: high concurrency returns
`429 RESOURCE_EXHAUSTED` from the provider, surfaced today as HTTP 500. Use `--rate` to stay under it.
Writes also consume read quota, because each write retrieves first. Prices are never hard-coded; with
managed generation off, a write is one `memories.create` and a read one `memories.retrieve`, so cost is
per operation.

---

## Observe

```bash
docker compose logs -f control-plane-api 2>&1 | grep -E "memory_write|memory_deletion|memory_decision"
```

- `memory_write` (audit) carries tier, operation, sensitivity, source, version, and correlation ID —
  never the value.
- `memory_deletion` (audit) carries the forget or purge details.
- `memory_decision` is emitted for every write attempt with the outcome (`updated`, `accepted`,
  `needs_confirmation`, `ambiguous`, `not_allowed`, `rejected`), `reason`, `preference_type`
  (canonical / dynamic), `key`, `schema_id`, `schema_version`, `level`, `data_type`, `value_version`,
  `sensitivity`, `category`, `health`, and the value in masked form: normal values as written; health
  values as `***`; restricted or sensitive terms replaced by `***`.

The memory agent's dev-UI server prints `agent_memory_decision` events for the same writes as seen from
the agent, plus `declined` events when the model decides not to save something
(`record_memory_decision`). Set `LOG_LEVEL` to change the agent's log level.
