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

Agents must eventually authenticate with workload identity. The current compatibility routes retain
the POC request model and are not a production authentication boundary.
