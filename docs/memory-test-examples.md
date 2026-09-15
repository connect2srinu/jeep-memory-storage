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

## 4. Observe and clean up

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
