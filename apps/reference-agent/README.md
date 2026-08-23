# Reference ADK Agent

Grocery Preference Assistant demonstrates consumption of the Shared Memory API without importing
Vertex AI Memory Bank SDKs or platform service implementations.

```bash
cd apps/reference-agent
python -m pip install -e '.[dev]'
export MEMORY_API_URL=http://localhost:8080
adk web app
```

The first tool call resolves a snapshot through the API and stores it in ADK Session state.
Subsequent turns reuse the snapshot until `refresh_user_preferences` is called.

`MEMORY_API_TOKEN` is a development transport option in this first slice. It will be replaced by a
pluggable workload-identity token provider before production authentication is enabled.
