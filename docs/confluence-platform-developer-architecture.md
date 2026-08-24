# Shared Memory Platform: Developer Architecture and Implementation Guide

## Audience and outcome

This page is for platform developers implementing or reviewing the shared-memory service. The
platform gives ADK agents canonical preference context while keeping provider SDKs, schema
identifiers, authorization, and conflict resolution out of agent prompts and tools.

## Architecture

```text
Admin Console -> Admin API -> PostgreSQL control plane
                         \-> Vertex context_spec provisioning

ADK Agent -> Runtime API -> identity/capabilities/grants -> MemoryStore -> Vertex Memory Bank
                        \-> deterministic resolver -> Effective Preference Snapshot
```

PostgreSQL is authoritative for ownership and policy. Memory Bank is authoritative for managed
user-scoped memory. The effective snapshot is derived Session context.

## Onboarding implementation

The guided endpoint compiles one business request into domain, scope, catalog entries, schema and
field mappings, agent registration, owned grant, shared access requests, resolution policy,
dynamic-memory policy, and audit events. Vertex mode then compiles every active schema version into
the Agent Engine `context_spec`.

Activation is schema provisioning, not user profile creation. Profiles remain lazy.

## Runtime read implementation

1. Map the verified caller to an active agent.
2. Require `resolve_context` and exact consumer domain.
3. Load readable grants and active mappings.
4. Retrieve each owner-domain profile at exact scope.
5. Normalize profile fields to canonical attributes.
6. resolve deterministically using policy.
7. Return values, explanations, provenance, schema versions, and `writablePreferences`.

## Runtime write implementation

Model-facing tools accept no schema ID. The runtime matches the submitted attribute against active
grants and selects only a same-domain `WRITE` or `READ_WRITE` grant. Exactly one match is required.
Read-only, cross-domain, unknown, and ambiguous routes fail before persistence.

This removes a non-deterministic LLM decision from the security boundary and prevents a domain
agent from accidentally choosing a readable shared schema.

## Vertex adapter

Structured profiles are retrieved with the provider profile API. Explicit changes are stored as
typed exact-scope memory facts and overlaid during reads because direct field-level profile updates
are not available. Natural-language events are additionally ingested for asynchronous provider
generation and consolidation.

## Capabilities and grants

Capabilities authorize operation classes; grants authorize data:

| Capability | Operation |
|---|---|
| `resolve_context` | Resolve effective preferences |
| `submit_candidates` | Submit explicit/event writes |
| `inspect_provenance` | See provenance and raw authorized profiles |
| `administer_memory` | Perform privileged administration |

An agent needs both the capability and the appropriate active schema grant.

## Invariants

- canonical attribute owner is unique;
- schema domain, scope domain, and attribute owner agree;
- user and application scope are exact;
- read does not imply write;
- automatic writes never cross domains;
- resolution is deterministic and explainable;
- failures never fabricate a saved preference.

## Testing

Use unit/API tests for routing and authorization, frontend tests for wizard validation, and a live
multi-Session Vertex scenario for release acceptance. LLM response behavior belongs in ADK evals;
pytest should verify deterministic code contracts.

## Current gaps

- schema evolution for active schemas requires a reviewed version workflow;
- managed profile convergence is asynchronous;
- production identity, alerting, retention/deletion, and live recall tests must be environment-gated.

Related: `agent-memory-setup.md`, `vertex-memory-bank.md`, and `adk-web-demo.md`.
