# Memory Flow Test Examples

Examples to exercise the agent's **topics**, **sensitivity classification**, and **dynamic memory**
flows. Two ways to test: a runnable script (deterministic, covers everything) and a dev-UI prompt
matrix (agent behaviour).

## Prerequisites

- Stack up: control plane on `:8080`, Postgres, admin console.
- The `grocery` domain's dynamic-memory policy approves topics `shopping`, `fulfillment`, and
  `wellness:sensitive`. Configure in the admin console (Create Memory Setup → Memory step) or:
  ```bash
  docker exec geap-memory-postgres-1 psql -U shared_memory -d shared_memory -c "UPDATE dynamic_memory_policies SET memory_topics='[\"shopping\",\"fulfillment\",\"wellness:sensitive\"]'::json WHERE domain_id='grocery';"
  ```

## 1. Runnable script (recommended)

Deterministic; hits the runtime API directly, uses a throwaway user, and cleans up with `forget`:

```bash
python3 scripts/memory_flow_examples.py
```

It verifies 18 checks across: canonical writes, topic gating, restricted-content blocking, the
sensitive + source rule, per-topic sensitivity, resolve surfacing (`sensitivity`, `memorySource`,
`approvedTopicDetails`), and deletion. Options: `--base`, `--agent`, `--domain`.

## 2. Dev-UI prompt matrix (agent behaviour)

Start the dev UI and drive the chat:
```bash
cd apps/memory-agent && source .venv/bin/activate && \
CONTROL_PLANE_API_URL=http://localhost:8080 REFERENCE_AGENT_ID=grocery-agent PREFERENCE_DOMAIN=grocery \
SESSIONS_DATABASE_URL=postgresql+asyncpg://shared_memory:local-development-only@localhost:15432/shared_memory \
python -m memory_agent.serve
# open http://localhost:8000/dev-ui/?app=memory_agent
```

| # | Prompt | Flow | Expected (see the Events / trace panel) |
|---|---|---|---|
| 1 | "I always shop at Kroger." | canonical | `save_preference("grocery.preferred_store", …)` → 200 |
| 2 | "Remember I do a big shop early Sunday mornings." | dynamic · approved topic | `remember_dynamic_preference("shopping", …)` → 200 |
| 3 | "Remember to leave deliveries at the back door." | dynamic · approved topic | `remember_dynamic_preference("fulfillment", …)` → 200 |
| 4 | "Remember I walk daily for my wellness routine." | dynamic · **sensitive topic** | stored (user-directed) and tagged sensitive |
| 5 | "Remember I love gardening tomatoes." | dynamic · **unapproved topic** | declined — not an approved memory type |
| 6 | "Remember I'm training for a marathon." | no match | declined |
| 7 | "Remember my phone number is 555-123-4567." | **restricted (PII)** | tool returns 400 — blocked |
| 8 | "Remember I wish I could bring my guns into the store." | **restricted (weapons)** | tool returns 400 — blocked |
| 9 | New session → "What do you know about my shopping habits?" | recall | recalled from the resolved snapshot |
| 10 | "What are my preferences?" | read | answered from the injected snapshot (no tool call) |

Note the agent always writes `source: user_directed`, so the **sensitive + inference → 403** path
is not reachable from the chat — use the API for it (below).

## 3. API one-liners (the paths the UI can't reach)

The **sensitive + inference rejection** and **per-topic sensitivity** need an explicit `source`:

```bash
# protected-class inferred -> 403 (would be stored if user-directed)
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/dynamic -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"ex1","appName":"a","domain":"grocery"},"topic":"shopping","value":"user is Muslim","source":"inference"}'

# sensitive topic (wellness) + inferred -> 403
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/dynamic -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"ex1","appName":"a","domain":"grocery"},"topic":"wellness","value":"walks daily","source":"inference"}'

# resolve — see sensitivity, memorySource, and approvedTopicDetails (topic meanings)
curl -s -X POST http://localhost:8080/api/v1/runtime/preferences/resolve -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"ex1","appName":"a","domain":"grocery"},"sessionId":"s","agentId":"grocery-agent"}'
```

## 4. Load & cost benchmark

`scripts/memory_load_test.py` runs a configurable number of inserts (writes) and reads, reports
throughput + latency (avg/p50/p95/p99), and computes a cost estimate from unit prices you supply.
Stdlib only; it forgets its test users at the end.

```bash
# 500 writes + 500 reads across 50 users, 16 concurrent, with sample unit prices
python3 scripts/memory_load_test.py --writes 500 --reads 500 --users 50 --concurrency 16 \
  --price-per-write 0.00002 --price-per-read 0.000005

# canonical write path (discovers a writable attribute if --attribute is omitted)
python3 scripts/memory_load_test.py --write-mode canonical --writes 200
```

Key flags: `--writes`, `--reads`, `--users`, `--concurrency`, `--rate` (ops/sec throttle),
`--write-mode dynamic|canonical`, `--topic`/`--attribute`, flat `--price-per-write`/`--price-per-read`,
token `--price-in-per-m`/`--price-out-per-m` + `--tokens-in-*`/`--tokens-out-*`, `--no-cleanup`, and
`--base`/`--agent`/`--domain`.

**Apply a model price (e.g. gemini-3.5-flash = $1.50/1M in, $9.00/1M out):**
```bash
python3 scripts/memory_load_test.py --writes 100 --reads 200 --rate 1 \
  --price-in-per-m 1.50 --price-out-per-m 9.00 --tokens-in-write 1000 --tokens-out-write 150
```

⚠️ **Vertex Memory Bank enforces a "Memory Bank Read Requests per minute per region" quota.** High
concurrency trips `429 RESOURCE_EXHAUSTED` (surfaced today as HTTP 500). Use `--rate` to stay under
it — e.g. `--rate 1` ran 40 reads cleanly at ~770 ms avg, while `--concurrency 16` (~490 reads/min)
was rate-limited. Note **writes also consume read quota** (each write does a `retrieve` first).

Cost note: prices are **not** hardcoded — supply them from current Vertex AI Memory Bank / Agent
Engine pricing. With managed generation disabled (this deployment) a write is `memories.create` and a
read is `memories.retrieve`, so cost is modelled per operation (no per-op Gemini generation tokens).
To model the managed-generation path instead, price writes by generation tokens (see the build-vs-buy
cost calculator).

## 5. Observe and clean up

Watch the audit log while testing:
```bash
docker logs -f geap-memory-control-plane-api-1 2>&1 | grep -E "memory_write|memory_deletion"
```

Remove a test user's memories:
```bash
curl -s -X POST http://localhost:8080/api/v1/runtime/memory/forget -H "Content-Type: application/json" -H "X-Agent-ID: grocery-agent" \
  -d '{"scope":{"userId":"ex1","appName":"a","domain":"grocery"}}'
```

Memory Bank reads are eventually consistent, so an immediate resolve after a write or delete can lag;
the end state is correct.
