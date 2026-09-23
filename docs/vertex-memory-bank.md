# Vertex Memory Bank Integration

## Configuration

The Control Plane API uses Vertex when `MEMORY_BACKEND=vertex` and these settings are present:

```text
GOOGLE_CLOUD_PROJECT
GOOGLE_CLOUD_LOCATION
AGENT_PLATFORM_MEMORY_BANK_ID (or GOOGLE_CLOUD_AGENT_ENGINE_ID)
GOOGLE_APPLICATION_CREDENTIALS
MEMORY_BANK_GENERATION_MODEL   optional; Google-published Gemini models only
```

Use `docker-compose.vertex.yml` for the local cloud-backed stack. The adapter uses the `agentplatform`
2.x SDK surface (`client.memory_banks.memories` for data, `client.runtimes.update` for provisioning).

## Schema provisioning

Guided activation compiles every active schema version, groups schemas by scope-key signature, and
updates the configured Agent Engine:

```text
context_spec.memory_bank_config.structured_memory_configs
```

Success returns `PROVISIONED`. This changes configuration only; it creates no customer profile.

## Runtime reads

For each readable grant the adapter calls `retrieve_profiles` and `retrieve` at the schema's exact
scope — one of:

```text
organization_id + user_id
organization_id + household_id
organization_id + household_id + member_id
```

Provider fields are admitted only when they exist in the active schema version's mappings. Explicit
overlay facts (below) are merged over retrieved profiles, newest write per field winning, then the
runtime normalizes fields to canonical attributes and applies the resolution policy. Per-member schemas
are read only when a turn names a member.

Organizations, projects, and domains are authorization metadata in PostgreSQL, not scope keys. The
legacy request fields `appName` and `domain` are still accepted but do not select the provider scope.

## Runtime writes

Memory Bank has no field-level structured-profile update, so the platform stores each explicit value as
a typed JSON memory fact created with `CreateMemory`:

```json
{"schema": "shared-memory-explicit-preference/v1", "schema_id": "...", "schema_version": "2",
 "domain": "...", "attribute": "...", "value": "...", "version": 7, "updated_at": "..."}
```

`schema_version` records the version active at write time (a label; reads do not filter on it), and
`version` is a per-schema write counter. Each write first retrieves the scope's facts to compute the next
counter, so writes also consume read quota.

Dynamic (topic) memories are stored the same way with their topic, sensitivity, source, and expiry.
Event submissions store the event text as a fact.

**Managed generation is off.** The platform never calls `ingest_events` or `GenerateMemories`, so
Memory Bank does not extract memories on its own; only governed writes are stored.
`MEMORY_BANK_GENERATION_MODEL` is still written into the provisioned config for completeness.

## Deletion

- **Forget** (`POST /runtime/memory/forget`) lists memories with the authoritative `list` call,
  filters by each memory's immutable scope, and deletes them one by one. A household forget cascades
  to every member under it.
- **Forget one value** deletes every stored version of one attribute at exactly one scope.
- **Purge** (`POST /runtime/memory/purge`) matches organization memories by tier, attribute, or topic;
  `dryRun` (default) previews.
- The admin **retention sweep** deletes canonical values whose newest write is older than the schema
  version's `retentionDays`.

Every deletion emits a `memory_deletion` audit event. Reads are eventually consistent, so an immediate
count can lag a just-written value; the end state is correct.

## Lazy profiles

`profileInstancesCreated: 0` after activation is correct. A value appears only after an authorized
customer interaction.

## Quotas

Memory Bank enforces per-project, per-region request quotas (read requests per minute are the usual
limit). Exceeding them returns `429 RESOURCE_EXHAUSTED` from the provider, which the API currently
surfaces as HTTP 500. Resolve-once-per-session caching and lazy per-member reads keep steady-state load
low; use `scripts/memory_load_test.py --rate` to stay under the quota when load testing.

## Verification

1. Activate a new schema and confirm `PROVISIONED`.
2. Resolve the agent snapshot and inspect `writablePreferences`.
3. Save a value from the agent dev UI without a schema ID.
4. Resolve again, and in a later Session.
5. Confirm another user or household cannot see or update the value.

Unit tests and a `REGISTERED_LOCAL` activation do not prove a live Memory Bank flow. The opt-in contract
test `test_vertex_memory_store_gcp.py` runs against a real bank when `RUN_GCP_INTEGRATION_TESTS=1`.
