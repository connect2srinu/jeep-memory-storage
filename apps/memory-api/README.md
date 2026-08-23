# Shared Memory API

This application is the runtime-independent API boundary for agents and the Admin Console. During
the first migration slice its entry point reuses the tested legacy platform services. Subsequent
slices move those services into this package without changing the HTTP boundary.

Run from the repository root:

```bash
PYTHONPATH=apps/memory-api/app uvicorn memory_api.main:app --reload --port 8080
```

Health check:

```bash
curl http://localhost:8080/healthz
```

Create or upgrade the control-plane schema and import the validated YAML contracts:

```bash
docker compose exec memory-api alembic -c apps/memory-api/alembic.ini upgrade head
docker compose exec memory-api \
  sh -c 'PYTHONPATH=apps/memory-api/app:. python apps/memory-api/scripts/bootstrap_contracts.py'
```

The Docker image runs Alembic before starting Uvicorn. The importer is idempotent and preserves the
YAML contracts as the initial GitOps source. Runtime resolution continues to use the compatibility
core until the database-backed authorization and policy repositories pass their later migration
gates.

Agents must eventually authenticate with workload identity. The current compatibility routes retain
the POC request model and are not a production authentication boundary.
