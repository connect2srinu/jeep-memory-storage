# Guided Memory Setup

The Admin Console provides the preferred onboarding path for a new domain. Open
`http://localhost:3000`, create or select the owning organization and project, and choose **Create
Memory Setup**.

The flow opens on a short **overview page** that explains what a setup configures — domain, scope,
schemas, preferences, agents, and sharing — and shows a live inventory of the organizations,
projects, schemas, and agents that already exist. Select **Start setup** to enter the wizard:

```text
Use Case -> Preferences -> Scope -> Memory -> Agent -> Sharing -> Resolution -> Review -> Activate
```

Sharing and Resolution appear only when external schemas are selected.

On the **Use Case** step, the **Domain** field is populated from the domains that already exist in
the selected organization and project; choosing a different project updates the list. Type a new
name to create a new domain, or pick an existing one to extend it.

## Information to prepare

- organization and project IDs; create them from the **Organizations** directory if needed;
- domain ID, name, description, and owning team;
- canonical preferences owned by the domain;
- data type, allowed values, sensitivity, and description for each custom preference;
- user/profile scope;
- agent ID, runtime type, identity, and owned-schema permission;
- shared schemas the agent may read;
- resolution precedence when more than one schema is readable;
- confidence, confirmation, retention, and dynamic-memory settings.

Custom preference IDs must be complete and use the domain prefix, for example
`travel.seat_preference`. A blank suffix such as `travel.` is invalid and prevents activation.

## Preview and activation

The browser calls:

```text
POST /api/v1/admin/memory-setups/preview
POST /api/v1/admin/memory-setups/activate
```

Preview validates cross-references and returns a summary plus an exportable review representation
without changing database state. It does not create repository contracts or generated runtime
files. Activate transactionally:

1. validates the active organization/project relationship and creates or reuses the domain/scope;
2. creates custom catalog preferences;
3. creates and activates `<domain>-preferences-v1`;
4. registers or selects the domain agent;
5. approves the owned-schema grant;
6. creates pending requests for externally owned schemas;
7. creates a resolution policy when multiple schemas are available;
8. creates a dynamic-memory policy when enabled;
9. registers the schema with the selected backend;
10. writes audit metadata.

Organizations are immediately `ACTIVE` in the current POC. The organization directory and its
project/member forms are control-plane operations separate from Memory Setup activation.

Choose `READ_WRITE` for the owned schema if the agent must save preferences. `READ` permits resolve
but makes the schema ineligible for automatic write routing.

## Backend result

| Result | Meaning |
|---|---|
| `REGISTERED_LOCAL` / `MockMemoryStore` | Local process-only schema; no GCP change |
| `PROVISIONED` / `VertexMemoryBankStore` | Active schemas applied to Agent Engine `context_spec` |

No user profile is created during activation. `profileInstancesCreated: 0` is expected. The first
authorized write or provider generation event creates user-scoped memory lazily.

## Use from ADK

Configure the reference agent with the agent ID and domain created by the wizard. The agent receives
`writablePreferences` during snapshot resolution, sends only the chosen canonical attribute and
value, and never asks for a schema ID. See the [reference ADK agent](../apps/reference-agent/README.md).

## Existing schemas

The wizard safely reuses an active schema only when the requested scope and mappings already match.
It does not mutate an active schema to add fields. Create and approve a new schema version through
the advanced Admin API process before adding attributes.

## Validation

After activation:

1. verify the result backend;
2. verify the agent has `resolve_context` and `submit_candidates` as described in the
   [capability contract](agent-memory-setup.md#capabilities);
3. verify its owned schema grant is `READ_WRITE`;
4. resolve a snapshot and confirm the new attribute appears in `writablePreferences`;
5. write a value from ADK Web without a schema ID;
6. open a new Session for the same user and confirm recall;
7. verify a shared read-only attribute cannot be written.
