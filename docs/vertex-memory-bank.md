# Vertex Memory Bank Integration

## Configuration

The Memory API uses Vertex when these settings are present and `MEMORY_BACKEND=vertex`:

```text
GOOGLE_CLOUD_PROJECT
GOOGLE_CLOUD_LOCATION
AGENT_PLATFORM_MEMORY_BANK_ID (or GOOGLE_CLOUD_AGENT_ENGINE_ID)
GOOGLE_APPLICATION_CREDENTIALS
```

Use `docker-compose.vertex.yml` for the local cloud-backed stack.

## Schema provisioning

Guided activation compiles every active profile schema version, groups schemas by scope-key
signature, and updates the configured Agent Engine with:

```text
context_spec.memory_bank_config.structured_memory_configs
```

Success returns `PROVISIONED`. This changes schema configuration only; it does not create any user
profile instance.

## Runtime reads

For each readable grant, the adapter retrieves structured profiles and memories at exact scope:

```text
user_id + app_name + owner domain
```

Provider fields are admitted only when they exist in the active schema mapping. The runtime then
normalizes them to canonical attributes and applies resolution policy.

## Runtime writes

The provider currently lacks a direct field-level structured-profile update API. The platform
therefore stores an explicit preference as a typed JSON memory fact containing schema, version,
domain, field, value, and timestamp. On read, this explicit fact overlays the managed profile.

For natural-language event writes, the adapter also calls event ingestion. Memory Bank may then
extract and consolidate structured profile data asynchronously.

## Lazy profiles

`profileInstancesCreated: 0` after activation is correct. A profile/value appears only after an
authorized user interaction. Provisioning and population are separate operations.

## Isolation

Automatic write routing happens before the provider call and permits only one same-domain writable
grant. A shared read grant cannot be used for a write. Scope domain, schema owner, and canonical
attribute owner remain aligned.

## Verification

1. activate a new schema and confirm `PROVISIONED`;
2. resolve the agent snapshot and inspect `writablePreferences`;
3. write from ADK Web without a schema ID;
4. resolve again and in a later Session;
5. inspect provider state only as a diagnostic, allowing for asynchronous consolidation;
6. verify another user and another domain cannot see or update the value.

Do not treat unit tests or a `REGISTERED_LOCAL` activation as proof of a live Memory Bank flow.
