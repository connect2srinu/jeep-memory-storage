# Deployment Placeholders

Complete these values before cloud deployment or a live Vertex validation:

```text
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
AGENT_PLATFORM_MEMORY_BANK_ID=
GOOGLE_ID_TOKEN_AUDIENCE=
MEMORY_API_SERVICE_ACCOUNT=
ADMIN_CONSOLE_SERVICE_ACCOUNT=
REFERENCE_AGENT_SERVICE_ACCOUNT=
DATABASE_INSTANCE=
DATABASE_NAME=shared_memory
ARTIFACT_REGISTRY_REPOSITORY=
MEMORY_API_IMAGE=
ADMIN_CONSOLE_IMAGE=
REFERENCE_AGENT_IMAGE=
ADMIN_ROLE_BINDINGS_JSON=
```

Local Vertex-backed Compose additionally needs Application Default Credentials at the standard
gcloud path mounted by `docker-compose.vertex.yml`.

For an ADK consumer created in the Admin Console:

```text
REFERENCE_AGENT_ID=
PREFERENCE_DOMAIN=
ADK_APP_NAME=
MEMORY_API_URL=
MEMORY_API_AUDIENCE=
```

Do not add schema IDs to agent environment variables or prompts. Schema selection is resolved by
the platform from registration and grants.
