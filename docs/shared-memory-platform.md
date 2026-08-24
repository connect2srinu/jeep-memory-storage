# Shared Memory Platform Service

## Executive summary

The platform gives multiple ADK agents governed access to reusable user preferences without sharing
provider credentials or embedding schema knowledge in prompts. The Memory API authenticates the
agent, enforces domain ownership and grants, reads Memory Bank, resolves conflicts deterministically,
and returns one effective snapshot.

## Control plane

PostgreSQL stores domains, scopes, canonical preferences, schema versions and mappings, registered
agents, access requests/grants, resolution policies, dynamic-memory policies, and audit records.
The Admin Console is a client of this API; it is not a provider administration client.

## Data plane

The runtime API provides resolve, refresh, raw-profile inspection, event ingestion, and explicit
preference update operations. Agents see canonical attributes and `writablePreferences`; schema IDs
remain an internal platform concern.

## End-to-end flow

```text
Admin creates setup -> platform activates controls -> Vertex context_spec updated
User states preference -> ADK chooses writable attribute -> API resolves schema
API writes exact-scope memory + ingests event -> snapshot refreshes
Later Session -> API retrieves and resolves -> ADK receives preference
```

## Sources and resolution

The normalized resolver can compare Session overrides, explicit profiles, managed Memory Profiles,
domain/dynamic memories, inferred memories, and defaults. Policy—not Gemini—chooses the winner using
source priority, schema/domain priority, explicit-over-inferred, recency, and confidence.

## Ownership rules

- one canonical owner per attribute;
- schema owner, scope domain, and key owner must agree;
- shared readers require approved grants;
- consumer agents cannot update foreign schemas;
- one same-domain writable mapping is required for automatic write routing.

## Local and cloud modes

The default Compose file uses a deterministic mock store. The Vertex override connects the same API
to an existing Agent Engine Memory Bank and provisions active schemas through its `context_spec`.
Profile instances remain lazy in both modes.

## Release acceptance

A release needs code tests plus a live Vertex scenario proving onboarding, schema provisioning,
schema-less ADK write, later-Session recall, user isolation, and cross-domain denial.
