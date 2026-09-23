# Guided Memory Setup

The Admin Console's **Create Memory Setup** flow is the preferred way to onboard a domain. Open
`http://localhost:3000`, create or select the owning organization and project under
**Organizations**, then choose **Create Memory Setup**.

For a complete worked example (a household grocery setup, tested end to end), follow
[Household Memory — End-to-End UI Guide](dynamic-household-test-guide.md). This page is the reference
for each step.

The flow opens on an **overview page** that explains what a setup configures and shows the
organizations, projects, schemas, and agents that already exist. **Start setup** enters the wizard:

```text
Use Case -> Preferences -> Scope -> Memory -> Agents -> [Sharing] -> [Resolution] -> Review -> Activate
```

**Sharing** appears when you turn on *Discover shared schemas* on the Agents step. **Resolution**
appears when the agent will read more than one schema.

## Steps

| Step | What you enter |
|---|---|
| **Use Case** | Name, description, owning team, organization, project, and domain. The Domain field lists existing domains in the selected project; type a new DNS-style name (e.g. `travel`) to create one. |
| **Preferences** | Reusable catalog preferences (recommended ones are preselected) and **+ Create custom preference**: attribute ID, display name, description, datatype, allowed values, sensitivity (non-sensitive / sensitive / restricted), and **Health data**. Health data is treated as at least sensitive. |
| **Scope** | Who the memory belongs to (see below). For **Household + members**, assign each preference to the **Household (shared)** or **Member (per person)** tier. |
| **Memory** | Canonical preferences on/off; **Preference retention (days)**; dynamic memory with confidence threshold, retention, approved topics (each with a sensitivity and a description), and *Require user confirmation*. |
| **Agents** | Register a new agent (ID, display name) or select an existing one in the domain; owned schema access (`READ`, `WRITE`, `READ_WRITE`); optionally discover shared schemas. |
| **Sharing** | Pick schemas owned by other teams; each selection submits a `READ` access request that stays pending until the owner approves it. |
| **Resolution** | Order the readable schemas. See the known limitation below. |
| **Review** | The non-mutating preview: generated schemas, scopes, grants, policies, and warnings. |
| **Activate** | Applies everything in one transaction. |

Custom preference IDs must use the domain prefix and a non-empty suffix, e.g.
`travel.seat_preference`; `travel.` is rejected.

### Scope choices

| Choice | Scope keys | Runtime support |
|---|---|---|
| Per User | `organization_id + user_id` | Supported |
| Per Household | `organization_id + household_id` | Supported |
| Household + members | two schemas: `organization_id + household_id` and `organization_id + household_id + member_id` | Supported; recommended for families |
| Per User + Store | `organization_id + user_id + store_id` | **Not supported at runtime** — activation succeeds but agent reads and writes fail |
| Custom | the keys you enter | **Not supported at runtime** unless they equal one of the three supported shapes |

### Retention and purpose

- **Preference retention** must stay within the platform limits: 1095 days for normal data, 730 days
  for sensitive or health data. The preview rejects a larger value. Leave it empty to keep values until
  deleted. The limits are placeholders pending Legal review.
- Schemas created by the wizard allow the `personalization` purpose. Agents declare a purpose
  (default `personalization`); an agent whose purpose a schema does not allow gets no access to it.

## Preview and activation

The browser calls:

```text
POST /api/v1/admin/memory-setups/preview
POST /api/v1/admin/memory-setups/activate
```

Preview validates cross-references and returns a summary and review representation without changing
state. Activate, in one transaction:

1. validates the organization/project and creates or reuses the domain and scope(s);
2. creates the custom catalog preferences;
3. creates and activates the schema(s): `<domain>-preferences-v1`, or for **Household + members**
   `<domain>-household-preferences-v1` and `<domain>-member-preferences-v1`;
4. registers or selects the agent and approves its owned-schema grants;
5. creates pending access requests for schemas owned by other teams;
6. creates a resolution policy when more than one schema is readable;
7. creates a dynamic-memory policy when dynamic memory is enabled;
8. registers the schemas with the memory backend;
9. writes audit events.

Choose `READ_WRITE` for the owned schema when the agent must save preferences. `READ` allows resolve
but makes the schema ineligible for writes.

## Backend result

| Result | Meaning |
|---|---|
| `REGISTERED_LOCAL` / `MockMemoryStore` | Local, process-only registration; no Google Cloud change |
| `PROVISIONED` / `VertexMemoryBankStore` | Active schemas applied to the Agent Engine `context_spec` |

No customer profile is created during activation; `profileInstancesCreated: 0` is expected. The first
authorized write creates the customer's memory.

## Changing a live schema

The wizard reuses an active schema only when its scope and mappings already match, and never adds
fields to it. To add a preference later:

1. **Govern & manage → Preference Catalog**: create the preference (or create it inside the next step).
2. With the organization selected, **Govern & manage → Schemas** → select the schema → **Create new
   version** → add the preference → **Review version** → **Submit version for approval**.
3. **Govern & manage → Approvals** → **Approve**.

The new version replaces the previous one immediately; start a new agent session to see it. Step-by-step
navigation is in section 6 of the [end-to-end guide](dynamic-household-test-guide.md). The Schemas tab
under Organization → Project → Domain is read-only.

## Use from ADK

Point the [memory agent](../apps/memory-agent/README.md) at the agent ID and domain created by the
wizard. The agent receives `writablePreferences` in the snapshot, sends only the chosen attribute and
value, and never asks for a schema ID or a member ID.

## Validation

After activation:

1. check the backend result;
2. check the agent has `resolve_context` and `submit_candidates`
   ([capability contract](agent-memory-setup.md#capabilities)) and its owned grant is `READ_WRITE`;
3. start the agent and confirm the new attributes appear in the snapshot's `writablePreferences`;
4. save a value from the dev UI without a schema ID;
5. open a new Session for the same user and confirm it is recalled;
6. confirm a shared read-only attribute cannot be written.

## Known limitations

- **Schema precedence from the Resolution step is stored but not applied at runtime.** The runtime
  loads a policy's default rules and per-attribute overrides, not its schema-priority list. Express
  precedence as an attribute override (Govern & manage → Resolution Policies) until this is fixed.
- **Per User + Store** and **Custom** scopes are offered but not supported by the runtime.
- The Scope step's "Organization isolation" callout still mentions only `organization_id + user_id`.
