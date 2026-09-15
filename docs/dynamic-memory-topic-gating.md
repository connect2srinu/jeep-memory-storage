# Dynamic Memory Topic Gating

Dynamic memory is **not** an open store for arbitrary user information. Canonical preferences stay
structured and governed; non-canonical facts may be retained **only within explicitly approved
topics** configured per agent/domain. The **control plane**, not the agent, enforces this.

## The two long-term tiers

| Tier | What it is | Written via | In `resolve` |
|---|---|---|---|
| **Canonical** | A value bound to a defined schema attribute (`writablePreferences`) | `PUT /api/v1/runtime/preferences/{attribute}` | `source: MEMORY_PROFILE`, `resolutionReason: CANONICAL_MEMORY_PROFILE`/`DOMAIN_AUTHORITY`, confidence `1.0` |
| **Dynamic** | A non-canonical fact inside an approved topic | `POST /api/v1/runtime/memory/dynamic` | `source: DYNAMIC_MEMORY`, ranked below canonical, gated by the policy confidence threshold |

## Decision flow

When the user asks the agent to remember something:

1. **Canonical** — if it maps to a `writablePreferences` entry, write it canonically.
2. **Dynamic** — else if it belongs to one of the snapshot's `approvedTopics`, write it as dynamic
   memory tagged with that topic.
3. **Declined** — else it is not persisted. The agent never invents an attribute or a topic.

The agent may *propose* the topic; the platform *disposes*. All enforcement is server-side.

## Enforcement points (control plane)

- **Topic gate** — `POST /memory/dynamic` reads the domain's `dynamic_memory_policies` and:
  - rejects if no policy or the policy is disabled (`403`),
  - rejects a topic not in `memory_topics` (`403`),
  - blocks sensitive content — phone / SSN / card / email / secret — even inside an approved topic
    (`400`), as defense-in-depth (topics gate *categories*, not *content*),
  - applies `retention_policy.retention_days` as an expiry on the stored entry.
- **Managed generation disabled** — the Vertex backend no longer calls the provider's
  `ingest_events`, so Memory Bank cannot extract arbitrary, ungoverned memories. Only explicit
  writes (canonical attributes and topic-gated dynamic entries) are persisted.
- **Resolution** — approved dynamic memories are folded into `resolve` as `DYNAMIC_MEMORY`
  candidates: ranked **below** canonical via `source_priority`, dropped when below the policy's
  `confidence_threshold`, filtered on expiry. The snapshot exposes `approvedTopics` alongside
  `writablePreferences` so the agent knows the boundary.

## Where it runs

Entirely in the `control-plane-api` process. The `PreferenceResolver` is a pure deterministic
resolver; agents receive the already-resolved `EffectivePreferenceSnapshot` and apply no policy
logic. This is what makes the boundary governable, auditable, and consistent across agents. See
[Resolution policies](#resolution-policies) below.

## Configuration

Approved topics and the confidence threshold live on the domain's dynamic-memory policy
(`dynamic_memory_policies`), created in the admin console's Create Memory Setup:

| Field | Meaning |
|---|---|
| `enabled` | Dynamic memory is on for the domain |
| `memory_topics` | The authoritative list of approved topics. An entry may declare a sensitivity tier as `topic:tier` (e.g. `wellness:sensitive`); a bare `topic` defaults to `normal`. |
| `confidence_threshold` | Minimum confidence for a dynamic entry to survive resolution (default `0.7`) |
| `confirmation_required` | Whether entries should be staged for user confirmation (see limitations) |
| `retention_policy.retention_days` | Applied as expiry on stored entries |

No schema migration is required — `memory_topics` is reused as the approved-topic authority.
(`allowed_dynamic_categories` remains in the model but is unused.)

## Resolution policies

A resolution policy such as:

```json
{"source_priority":["SESSION_OVERRIDE","EXPLICIT_PROFILE","MEMORY_PROFILE","DOMAIN_MEMORY","DYNAMIC_MEMORY","INFERRED_MEMORY","DEFAULT"],
 "strategies":["SOURCE_PRIORITY","DOMAIN_PRIORITY","EXPLICIT_OVER_INFERRED","MOST_RECENT","HIGHEST_CONFIDENCE"],
 "minimum_confidence":0.85}
```

is **data** stored in the control plane and evaluated by control-plane code (`PreferenceResolver`),
never by the agent. Per attribute/topic: gate by `minimum_confidence` (affects `DYNAMIC_MEMORY` /
`INFERRED_MEMORY`; canonical is confidence `1.0`), group candidates by key, sort by the `strategies`
ladder using `source_priority`, and select the winner. `DYNAMIC_MEMORY` sits below `MEMORY_PROFILE`
in `source_priority`, so a canonical value always outranks a dynamic one for the same key.

## API surface

- `POST /api/v1/runtime/memory/dynamic` — body `{scope, topic, value, confidence?}`; returns
  `accepted` or a `403`/`400` rejection.
- `POST /api/v1/runtime/preferences/resolve` — now returns `approvedTopics` and `DYNAMIC_MEMORY`
  entries (keyed `topic:<name>`) alongside canonical preferences.
- `POST /api/v1/runtime/memory/forget` — right-to-be-forgotten; deletes every memory for a user
  scope (gated by `SUBMIT_CANDIDATES`).
- `POST /api/v1/runtime/memory/purge` — operator on-demand deletion across the organization by
  `tier`/`attribute`/`topic` (gated by `ADMINISTER_MEMORY`; `dryRun` defaults true to preview).

## Deletion (governance / CCPA)

Both tiers are deletable through the governed endpoints above, wrapping Memory Bank's native
`delete`/`list`:

- **User forget** enumerates the user's memories (via `list`, isolated by the memory's immutable
  scope) and deletes each by resource name.
- **Operator purge** lists org memories, matches by tier/attribute/topic on the stored fact, and
  deletes matches; `dryRun` previews without deleting.

Both emit a structured `memory_deletion` audit event (`op: forget | purge_preview | purge`). Note
Memory Bank reads are **eventually consistent**, so an immediate `deleted`/`matched` count can lag a
just-written value; the end state is correct.

## Agent integration

Both the `reference-agent` and the `memory-agent` implement the decision flow. Clients expose
`write_dynamic_memory`; agents add a `remember_dynamic_preference` tool and receive `approvedTopics`
in the injected snapshot. See [Memory Agent](../apps/memory-agent/README.md).

## Limitations / follow-ups

- `confirmation_required` is read and retention is applied, but staging dynamic entries through the
  approvals flow before they become visible is not yet wired.
- The sensitive-content denylist is pattern-based (defense-in-depth), not a guarantee.
- Enforcement holds only while **all writes route through the control plane**; an agent writing to
  Vertex Memory Bank directly would bypass the gate. Managed generation is disabled to remove the
  provider's own auto-extraction path.
- Deletion is eventually consistent at the provider (see above); for hard-delete SLAs the delete
  operations could be awaited to completion.

## Code map

- Write gate + resolution: `apps/control-plane-api/app/control_plane_api/services/runtime_service.py`
- Resolver: `apps/control-plane-api/app/control_plane_api/services/preference_resolver.py`
- Policy read: `apps/control-plane-api/app/control_plane_api/persistence/runtime_repository.py`
- Storage + managed-generation switch: `apps/control-plane-api/app/control_plane_api/integrations/vertex_memory_store.py`
- Route + models: `apps/control-plane-api/app/control_plane_api/api/runtime/`
