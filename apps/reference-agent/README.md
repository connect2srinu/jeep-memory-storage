# Reference ADK Agent

Grocery Preference Assistant demonstrates consumption of the Shared Memory API without importing
Vertex AI Memory Bank SDKs or platform service implementations.

```bash
cd apps/reference-agent
python -m pip install -e '.[dev]'
export MEMORY_API_URL=http://localhost:8080
export REFERENCE_AGENT_ID=grocery-agent
adk web app
```

The first tool call resolves a snapshot through the API and stores it in ADK Session state.
Subsequent turns reuse the snapshot until `refresh_user_preferences` is called.

When the API runs with local authentication disabled, the client sends `REFERENCE_AGENT_ID` through
`X-Agent-ID`. When `MEMORY_API_TOKEN` is set, it sends that Google ID token as a bearer token and the
API maps the verified service-account email to the registered agent. A request-body agent ID cannot
establish identity.
