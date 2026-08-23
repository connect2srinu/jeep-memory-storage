# Vertex Memory Bank integration

The Memory API is the only application allowed to call Gemini Enterprise Agent Platform Memory
Bank. Set `MEMORY_BACKEND=vertex` in a deployed Memory API; agents and the Admin Console continue to
call the platform APIs and receive no Memory Bank IAM permissions.

## Runtime mapping

| Platform operation | Provider operation | Behavior |
|---|---|---|
| Retrieve profiles | `retrieve_profiles` | Uses the exact `user_id`, `app_name`, `domain` scope and filters to authorized active schemas. |
| Retrieve natural memories | `retrieve` | Uses the same exact scope. Typed internal explicit-write records are excluded from natural-memory results. |
| Submit event | `ingest_events` plus a typed event record | Triggers lazy provider generation and keeps an auditable event reference. |
| Explicit update | `create` typed memory | Overlays the latest explicit field value on provider profiles because the current SDK has no field-level profile update operation. |

The overlay record contains schema ID/version, domain, profile field, value, update time, and a
monotonic version. It is stored at the same exact scope as the provider profile. Runtime
authorization rejects cross-domain writes before the store is called, and the store repeats the
schema/domain guard.

## Provision approved schemas

The control-plane database is authoritative. Export only active schema definitions and versions:

```bash
PYTHONPATH=apps/memory-api/app:. python apps/memory-api/scripts/export_vertex_context.py \
  --output config/generated/vertex-context-spec.json
```

Review the generated file, then pass its `memory_bank_config` as the Agent Runtime `context_spec`
during the controlled deployment/update. Profile instances are never bulk-created: Memory Bank
creates them lazily after user events.

## Cloud-gated contract check

The test creates data under a unique test user and therefore runs only by explicit opt-in:

```bash
RUN_GCP_INTEGRATION_TESTS=1 \
GOOGLE_CLOUD_PROJECT=<PROJECT_ID> \
GOOGLE_CLOUD_LOCATION=<REGION> \
AGENT_PLATFORM_MEMORY_BANK_ID=<REASONING_ENGINE_ID> \
PYTHONPATH=apps/memory-api/app:. pytest -q \
  apps/memory-api/tests/test_vertex_memory_store_gcp.py
```

Provider generation is asynchronous. The immediate assertion validates submission and exact-scope
retrieval; profile population should be polled by the Phase 9 acceptance runner.

## Known provider constraints

- Memory Profile definitions are part of Agent Runtime context configuration rather than an
  independent per-schema CRUD surface.
- `retrieve_profiles` requires an exact, case-sensitive scope match.
- Event-driven profile generation is asynchronous and may be eventually consistent.
- The adapter keeps Google SDK objects behind `MemoryBankClient`; platform domain models remain
  provider-neutral and unit tests use a fake client.
