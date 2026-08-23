# Phase 9 governed-memory acceptance

This scenario proves the complete control-plane and runtime flow for user `1001` against whichever
backend the Memory API is configured to use.

## Scenario

1. Grocery writes `Store-A` and dietary preference `vegetarian` to its own schema.
2. Customer writes `Store-B` and fulfillment preference `pickup` to its own schema.
3. Inventory writes `Store-C` to its own schema.
4. The Grocery agent owner requests READ access to the Customer schema.
5. The Customer schema owner approves the request; the API records the grant and audit events.
6. Grocery resolves its snapshot. The Customer-first override selects `Store-B`; Grocery-owned
   dietary preference remains `vegetarian`; Customer fulfillment is `pickup`.
7. Grocery explicitly updates its dietary preference to `vegan` and refreshes.
8. The snapshot version changes, the profile version increments, and schema/policy provenance is
   retained.

Cross-domain writes are never used. Customer and Inventory seed data through their own registered
agents; Grocery receives only approved READ access.

## Run against local mock

Start the Compose stack, bootstrap the latest contracts, then run:

```bash
python scripts/run_phase9_acceptance.py --memory-api-url http://localhost:8080
```

The script uses local development identity headers when tokens are absent.

## Run against Vertex

Deploy the same Memory API with `MEMORY_BACKEND=vertex`, provision the compiled context spec, and
provide one ID token per registered workload plus an authorized administrator token:

```bash
export GROCERY_AGENT_TOKEN=<GROCERY_AGENT_ID_TOKEN>
export CUSTOMER_AGENT_TOKEN=<CUSTOMER_AGENT_ID_TOKEN>
export INVENTORY_AGENT_TOKEN=<INVENTORY_AGENT_ID_TOKEN>
export PHASE9_ADMIN_TOKEN=<ADMIN_ID_TOKEN>
python scripts/run_phase9_acceptance.py --memory-api-url <MEMORY_API_CLOUD_RUN_URL>
```

The authenticated token emails must match active agent principals in the registry, and the admin
email must be present in `ADMIN_ROLE_BINDINGS_JSON`. Use a disposable test user/scope in non-dev
environments.
