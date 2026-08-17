# Shared Memory Platform Service

| Document field | Value |
|---|---|
| Platform | Gemini Enterprise Agent Platform / Google ADK |
| Capability | Multi-domain preference memory and deterministic resolution |
| Reference consumer | Grocery ADK agent |
| Additional consumers | Store and Delivery examples |
| Status | Production-structured POC |

> Attach `shared-memory-platform.drawio` to the Confluence page and insert it with the
> draw.io/diagrams.net macro. Use `agent-memory-flows.drawio` for the detailed read, session,
> long-term, and degradation subflows.

## Executive summary

The Shared Memory Platform gives authorized business agents one resolved preference context. It
separates platform orchestration from domain semantics and prevents agents from querying or writing
memory sources directly.

```text
Platform: storage + security + sharing + resolution + governance + scale
Domain:   meaning + schema + ownership + policy configuration + usage
```

## Architecture decisions

| Decision | Rationale |
|---|---|
| One platform facade | Agents remain independent of backend and SDK changes |
| Exact user/application/domain scopes | Avoid cross-user and cross-domain leakage |
| Explicit domain allowlists | Default-deny isolation, including future Pharmacy workloads |
| Catalog plus dynamic keys | Stable enterprise fields without blocking open-ended memory |
| Attribute-level resolver policies | No invalid global Grocery-over-everything rule |
| Pure deterministic resolver | Repeatable, testable decisions outside Gemini |
| Derived snapshot | Low-latency reuse without becoming another source of truth |
| Cross-domain candidate routing | Discoveries cannot bypass owner-domain governance |

## Platform components

| Component | Responsibility |
|---|---|
| Shared Memory Platform API | Stable HTTP and Python service contract |
| Authorization Service | Identity presence and domain/catalog read-write enforcement |
| Session Context Service | Structured overrides separate from conversation history |
| Profile Preference Service | Replaceable authoritative profile adapters |
| Long-Term Memory Service | Memory Profiles plus dynamic Memory Bank memories |
| Preference Catalog | Canonical keys, types, scopes, owners, sensitivity, readers, writers |
| Policy Registry | Domain access and attribute-level resolution strategies |
| Preference Resolver | Eligibility, ranking, conflict selection, explanation |
| Snapshot Service | Derived context cache keyed by user/domain/context/version |
| Observability | Redacted IDs, counts, decisions, latency, cache, and failure metadata |

## Domain model

The POC configures `customer`, `grocery`, `store`, `delivery`, and strictly isolated `pharmacy`.
All access is allowlisted. Grocery can read Customer, Store, and Delivery preferences needed for a
shopping task but can write only Grocery preferences.

If Grocery detects `delivery.preferred_window`, the platform records a candidate event for Delivery
instead of writing Delivery memory.

## Canonical profiles and dynamic memory

Memory Profiles provide structured, schema-backed canonical fields. The deployment configures the
`canonical-preferences-v1` schema when `ENABLE_MEMORY_PROFILES=true`. Profile retrieval uses the
documented `retrieve_profiles` Agent Platform SDK method.

Dynamic keys such as `grocery.banana_ripeness` remain Memory Bank facts under the exact scope:

```json
{
  "user_id": "U123",
  "app_name": "grocery_shared_preferences",
  "domain": "grocery"
}
```

Dynamic facts use the `shared-memory-preference/v2` envelope and retain confidence, confirmation,
schema version, owner domain, and provenance.

## Resolve flow

1. Authenticate the user and agent identity.
2. Load the consumer domain's readable-domain allowlist.
3. Check the derived snapshot.
4. Concurrently retrieve session overrides, explicit profiles, Memory Profiles, and dynamic memory.
5. Normalize all source data into the platform `Preference` model.
6. Enforce catalog and domain read policy.
7. Filter invalid, expired, unauthorized, and low-confidence values.
8. Load the attribute resolution policy.
9. Invoke the pure resolver.
10. Materialize and return an explainable `EffectivePreferenceContext`.

## Update flow

1. The domain extractor proposes a `PreferenceCandidate`.
2. The catalog resolves its canonical key and owner domain.
3. Strict type and scope validation runs.
4. The authorization service evaluates the consumer's write policy.
5. A Session candidate writes structured ADK state only.
6. An authorized long-term candidate writes a domain-scoped Memory Bank fact.
7. A cross-domain candidate enters the owner-validation queue without a memory write.
8. Derived snapshots are invalidated.

No LLM output can override steps 2–7.

## Resolution explanation

Each selected preference includes:

- source and owner domain;
- confidence and confirmation;
- timestamps and expiration;
- provenance;
- policy ID;
- resolution reason such as `SESSION_OVERRIDE`, `DOMAIN_AUTHORITY`, or
  `EXPLICIT_PROFILE_PRIORITY`.

## Final validation scenario

Run:

```bash
python scripts/validate_platform.py
```

Expected Grocery context:

| Preference | Value | Owner/source result |
|---|---|---|
| preferred_store | Store-084 | Customer explicit profile |
| preferred_product_type | organic | Grocery domain authority |
| preferred_window | 6PM-8PM | Delivery domain authority |
| banana_ripeness | slightly_green | Grocery dynamic memory |
| allow_substitutions | true | Session override |

## Failure behavior

Remote sources degrade independently. A failed source contributes no values and adds a warning;
the resolver continues with other authorized sources and defaults. A failed write returns an
explicit non-persisted disposition. The agent must never claim persistence from natural-language
output alone.

## Production extensions

- Verified user and agent identity, IAM Conditions, and tenant claims
- Durable candidate/audit workflow with owner approval
- Writable authoritative profile adapters
- Consent and sensitive-preference classification
- Idempotency, revisions, concurrency, retention, and right-to-forget
- Distributed snapshot/cache implementation
- Gemini structured-output extraction constrained by catalog schema
- Cloud Logging, Monitoring, Trace, SLOs, and security alerting

## Official references

- [Agent Platform overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents)
- [Agent Platform Sessions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/sessions)
- [Memory Bank](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank)
- [Memory Profiles](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/profiles)

