# Shared Memory Platform: Developer Architecture and Implementation Guide

| Document field | Value |
|---|---|
| Audience | Shared Memory Platform developers and maintainers |
| Platform | Google ADK and Gemini Enterprise Agent Platform |
| Purpose | Explain the architecture, implementation boundaries, runtime flows, and production direction |
| Reference implementation | Grocery consumer with Customer, Store, Delivery, and Pharmacy domains |
| Status | Production-structured proof of concept; production gaps are called out explicitly |

## 1. Purpose

The Shared Memory Platform gives an authorized agent one deterministic, explainable preference
context without allowing the agent to access Session, Memory Profiles, Memory Bank, or profile
systems directly.

The platform owns storage integration, normalization, authorization, resolution, provenance, and
governance. Domain teams own the meaning of their preferences and express that meaning through
reviewed YAML contracts.

```text
Domain teams                         Shared Memory Platform
------------                         ----------------------
Preference meaning                   Source adapters
Owner domain                         Authentication and authorization
Allowed readers/writers              Canonical normalization
Resolution intent                    Deterministic resolution
Memory Profile fields                Session and long-term routing
Consumer requirements                Provenance and audit events
```

## 2. Design principles

1. Agents consume a platform facade and never resolve raw memories themselves.
2. User, application, tenant, and domain scope must be explicit at every storage boundary.
3. Both domain-level and preference-level authorization must allow an operation.
4. A preference has exactly one authoritative owner domain.
5. Cross-domain discoveries become candidates; they do not become direct writes.
6. Resolution is deterministic code, not model judgment.
7. Generated runtime JSON is compiled from reviewed YAML and is never edited directly.
8. Provenance is available only to consumers with the appropriate capability.
9. A derived snapshot is a cache, not a source of truth.
10. Failure of one memory source must not silently change into a successful write claim.

## 3. System context

```text
                         Configuration and deployment plane

 Domain YAML contracts --> validate --> compile --> generated runtime artifacts
          |                                              |
          +--> pull request / CI / approvals             +--> deploy context_spec
                                                               |
                                                               v
 Runtime plane                                            Agent Platform

 ADK domain agent --> thin tools/API --> Shared Memory Platform facade
                                           |
                +--------------------------+---------------------------+
                |                          |                           |
          Authorization               Normalization                Resolver
                |                          |                           |
                +------------+-------------+-------------+-------------+
                             |                           |
                 Session + profile sources       Memory Profiles + Memory Bank
```

The implementation has two separate planes:

- The configuration plane validates business-domain declarations and compiles deterministic
  runtime artifacts.
- The runtime plane authenticates a consumer, retrieves authorized sources, normalizes candidates,
  resolves conflicts, and routes updates.

## 4. Repository map

| Path | Responsibility |
|---|---|
| `config/contracts/<domain>/` | Source-of-truth YAML for each onboarded domain |
| `config/templates/domain-onboarding/` | Annotated five-file starter bundle |
| `app/shared_memory/contracts/models.py` | Strict Pydantic contract models |
| `app/shared_memory/contracts/loader.py` | YAML loading and cross-contract validation |
| `app/shared_memory/contracts/compiler.py` | Deterministic generation of runtime JSON and schemas |
| `app/shared_memory/catalog/` | Canonical keys, aliases, types, scopes, sensitivity, and ownership |
| `app/shared_memory/policies/` | Domain access and attribute resolution policy |
| `app/shared_memory/auth/` | Consumer capabilities and read/write decisions |
| `app/shared_memory/adapters/` | Session, explicit-profile, Memory Profile, and Memory Bank adapters |
| `app/shared_memory/services/` | Context assembly, profile aggregation, long-term storage, and write routing |
| `app/shared_memory/resolver/` | Pure deterministic conflict resolver |
| `app/tools/preference_tools.py` | Thin ADK-facing platform tools |
| `app/agents/` | Reference agent instructions and deterministic POC extraction rules |
| `scripts/validate_memory_contract.py` | Read-only contract validation |
| `scripts/compile_memory_contract.py` | Runtime artifact generation or stale-artifact checking |
| `scripts/deploy.py` | Agent Runtime and Memory Profile configuration deployment |
| `scripts/generate_profile.py` | Explicit demo event submission for profile generation |
| `scripts/inspect_state.py` | Managed Session state inspection |
| `scripts/inspect_memory.py` | Normalized dynamic-memory and Memory Profile inspection |

## 5. Contract model

Every domain supplies five documents.

| Contract | Question it answers |
|---|---|
| `domain.yaml` | What is the trust boundary, and which domains may it read or write? |
| `preferences.yaml` | What does each canonical preference mean, who owns it, and what values are valid? |
| `resolution-policies.yaml` | Which eligible candidate wins when sources or domains disagree? |
| `memory-profiles.yaml` | Which canonical fields are projected into structured Memory Profiles? |
| `consumers.yaml` | Which agents use the domain and which platform operations may they invoke? |

The loader rejects, among other conditions:

- duplicate domains, preference keys, policy IDs, profile IDs, or agent IDs;
- unknown domains and dangling policy/profile/preference references;
- a preference whose namespace or owner does not match its contract domain;
- an owner domain missing from `allowedWriters`;
- strict-isolation domains that reference another domain;
- a Memory Profile containing a dynamic or foreign-owned preference;
- a consumer requesting a preference it is not allowed to read;
- mismatched profile scope keys.

The compiler produces:

```text
app/shared_memory/catalog/catalog.json
app/shared_memory/policies/domain_policy.json
app/shared_memory/policies/resolution_policy.json
app/shared_memory/profiles/memory_profiles.json
app/shared_memory/contracts/consumers.json
config/generated/profile_manifest.json
config/schemas/*.schema.json
```

These files are build artifacts. CI uses `compile_memory_contract.py --check` to detect drift.

## 6. Normalized preference model

Every source adapter converts source-specific data into the same logical model:

| Field | Meaning |
|---|---|
| `key` | Canonical namespaced key, for example `customer.diet` |
| `value` | Validated scalar value |
| `source` | Session, explicit profile, Memory Profile, domain memory, dynamic memory, inferred memory, or default |
| `owner_domain` | Domain with authority over the preference |
| `scope` | `SESSION` or `LONG_TERM` |
| `confidence` | Source confidence when meaningful |
| `updated_at` / `expires_at` | Recency and lifecycle data |
| `confirmed` | Whether the user or trusted process confirmed the value |
| `canonical` | Whether the key is declared in the catalog |
| `schema_version` | Contract/schema compatibility version |
| `sensitivity` | `normal`, `sensitive`, or `restricted` |
| `provenance` | Safe source metadata retained for audit and explanations |

Adapters must not invent authority. The schema owner, requested domain scope, canonical key, and
catalog owner must agree before a structured profile value is admitted.

## 7. Read and resolution flow

```text
1. Agent calls resolve-context tool or API.
2. Platform authenticates user identity and registered agent identity.
3. Consumer registry checks resolveContext capability.
4. Domain policy determines readable domains.
5. Platform concurrently retrieves:
   - structured Session overrides;
   - explicit authoritative profiles;
   - structured Memory Profiles;
   - domain-scoped dynamic Memory Bank memories;
   - platform defaults.
6. Adapters normalize source records into Preference objects.
7. Catalog validates type, allowed values, lifecycle, and owner.
8. Authorization filters values not readable by both policy levels.
9. Resolver groups candidates by logical resolution policy.
10. Resolver applies ordered strategies and selects one winner.
11. Platform returns EffectivePreferenceContext and safe explanations.
```

### 7.1 Two-level read authorization

A read is allowed only if both conditions are true:

```text
candidate.owner_domain is in consumer-domain permissions.read
AND
consumer_domain is in preference.allowedReaders
```

This is why the Grocery agent may read `customer.diet` but Pharmacy remains isolated.

### 7.2 Resolution strategies

Strategies are evaluated lexicographically. The first configured strategy is the strongest; later
strategies break ties.

| Strategy | Behavior |
|---|---|
| `SOURCE_PRIORITY` | Ranks sources using `sourcePriority` |
| `DOMAIN_PRIORITY` | Ranks authoritative owners using `domainPriority` |
| `EXPLICIT_OVER_INFERRED` | Prefers confirmed/explicit evidence over inference |
| `MOST_RECENT` | Uses the latest valid update as a tie-breaker |
| `HIGHEST_CONFIDENCE` | Uses confidence only after earlier strategies tie |

The current default source order is:

```text
SESSION_OVERRIDE
> EXPLICIT_PROFILE
> MEMORY_PROFILE
> DOMAIN_MEMORY
> DYNAMIC_MEMORY
> INFERRED_MEMORY
> DEFAULT
```

Domain priority is attribute-specific. There must not be a global rule such as “Grocery always
wins,” because Customer owns diet, Delivery owns delivery windows, and Grocery owns substitution
behavior.

### 7.3 Resolution output

Every selected value includes a `policy_id` and `resolution_reason`. The agent receives only the
already-resolved context and must not reinterpret conflicts.

## 8. Update and candidate flow

```text
1. Domain-specific extraction proposes PreferenceCandidate.
2. Catalog canonicalizes the key and determines owner domain.
3. Catalog validates value type, allowed values, and requested scope.
4. Consumer registry checks submitCandidates capability.
5. Authorization checks domain write policy and preference allowedWriters.
6. Platform chooses one disposition:

   Same-domain SESSION    -> STORED_IN_SESSION
   Same-domain LONG_TERM  -> STORED_IN_DYNAMIC_MEMORY
   Other owner domain     -> CROSS_DOMAIN_CANDIDATE
   Invalid value/scope    -> REJECTED
   Storage failure        -> NOT_PERSISTED
```

For example, Grocery can read `customer.diet` but cannot update it. A Grocery attempt to set the
key becomes a Customer-owned candidate. Production implementation requires a durable workflow in
which the Customer owner or the user reviews the candidate before an authoritative profile write.

The current POC candidate repository is process memory only. It demonstrates the authorization
decision but is not a production workflow, is not queryable through an approval UI, and is lost on
restart.

## 9. Session, canonical, and dynamic preferences

| Category | Intended use | Storage path |
|---|---|---|
| Session override | Temporary task-specific behavior | Structured ADK Session state |
| Canonical preference | Stable governed business attribute | Authoritative profile and/or Memory Profile workflow |
| Dynamic preference | Open-ended domain fact not yet in catalog | Domain-scoped Memory Bank memory |
| Cross-domain candidate | Discovery awaiting owner decision | Durable approval queue in the production target |

A temporary Grocery instruction such as “do not apply my vegetarian preference today” should be a
Grocery-owned contextual directive. It must not overwrite the authoritative Customer diet.

## 10. Memory Profile implementation

The contract compiler converts each declared profile into a Google structured-memory schema. The
deployment script includes those schemas in:

```text
context_spec.memory_bank_config.structured_memory_configs
```

Generation and retrieval must use the same exact scope:

```json
{
  "user_id": "USER_ID",
  "app_name": "APPLICATION_NAME",
  "domain": "OWNER_DOMAIN"
}
```

Enabling a profile schema does not populate it. A separate, authorized process must submit
confirmed events or synchronize an explicit profile.

### 10.1 Required production guardrail

The current compiler groups profile schemas that share the same list of scope-key names. Google
selects a structured-memory configuration from the presence of scope keys, not from a condition
such as `domain == grocery`. Consequently, a Grocery-scoped generation event can be evaluated
against Customer, Store, and Delivery schemas when they share the same signature.

That behavior produced examples such as a Grocery event being interpreted as
`customer.diet = Organic`.

Before production, implement all of the following admission controls:

1. Use `config/generated/profile_manifest.json` to map `schema_id` to declared owner domain.
2. Admit a returned schema only when its owner equals the requested scope domain.
3. Resolve a profile field through its schema manifest before consulting global aliases.
4. Require `schema_id`, profile owner, requested domain, key namespace, and catalog owner to agree.
5. Reject and emit a security/quality metric for every mismatch.
6. Use constrained `allowedValues` and precise descriptions for ambiguous sensitive attributes.
7. Consider separate Memory Bank resources or distinct scope-key signatures for high-isolation
   domains.

Filtering only after deterministic validation is mandatory; prompt wording alone is not an
authorization or data-quality boundary.

## 11. Consumer capabilities

| Capability | Meaning |
|---|---|
| `resolveContext` | Request an authorized effective context |
| `submitCandidates` | Propose a value for validation and routing; not a write grant |
| `inspectProvenance` | Receive safe owner, source, policy, and resolution details |
| `administerMemory` | Reserved for lifecycle operations; not implemented in the current POC |

Capabilities authorize operations. Domain and preference policies authorize data. Both checks are
required.

## 12. Failure and consistency model

Read sources degrade independently. If one source fails, the platform continues with available
authorized sources and returns a warning. It must never silently transform a failed write into a
successful natural-language response.

Required production behavior includes:

- idempotency keys for candidate submission and generation jobs;
- optimistic concurrency or profile revision checks;
- bounded retries with dead-letter handling;
- snapshot invalidation after every accepted mutation;
- deterministic replay of approval events;
- retention and right-to-forget workflows;
- tenant-scoped encryption, logs, metrics, and audit records.

## 13. Security and privacy requirements

1. Bind `agentId` to a verified Agent Identity or workload identity; do not trust request text.
2. Keep policy default-deny and use explicit domain and preference allowlists.
3. Redact restricted provenance unless the consumer has `inspectProvenance`.
4. Treat sensitive preferences, such as diet, as governed personal data.
5. Log authorization decisions without logging raw sensitive values.
6. Prevent cross-tenant and cross-user scopes in adapters and caches.
7. Require approval and an auditable reason for deletion or correction.

## 14. Observability

At minimum, emit metrics and structured events for:

- context resolution latency and source latency;
- source availability and fallback warnings;
- candidates filtered for invalid type, expiration, confidence, or authorization;
- profile schema/owner mismatches;
- resolution winner source and reason counts;
- cross-domain candidate counts and approval age;
- write disposition and Memory Bank failures;
- snapshot hit, miss, and invalidation counts.

Use hashed or tokenized user/session identifiers in centralized logs.

## 15. Testing strategy

| Layer | Required validation |
|---|---|
| Contract models | Valid and invalid YAML tests |
| Cross-reference loader | Ownership, access, profile, consumer, and isolation tests |
| Compiler | Golden deterministic artifacts and `--check` drift detection |
| Catalog | Canonicalization, alias collision, type, value, and scope tests |
| Authorization | Read/write matrix and capability tests |
| Adapters | Exact scope, normalization, schema-owner mismatch, and partial failure tests |
| Resolver | Every strategy, tie-breaker, expiration, confidence, and stable output tests |
| Services | Session, long-term, cross-domain, failure, and cache invalidation tests |
| Cloud integration | Generate, retrieve, update, isolation, and deletion lifecycle tests |
| UI acceptance | Effective context, session isolation, persistence, and denied-write messaging |

Run the current local suite with:

```bash
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py --check
python -m pytest -q
python scripts/validate_platform.py
```

## 16. Production implementation sequence

1. Add schema-owner admission filtering and domain-aware field lookup.
2. Replace the in-memory candidate repository with a durable, idempotent approval workflow.
3. Add an owner-domain approval API and authoritative profile writer.
4. Bind registered consumers to verified service identities.
5. Add tenant-aware scopes and policy evaluation.
6. Add revisioning, migration, retention, correction, and deletion workflows.
7. Add managed snapshot/cache infrastructure.
8. Add Cloud Logging, Monitoring, Trace, SLOs, alerts, and audit exports.
9. Run adversarial cross-domain and cross-tenant integration tests.
10. Promote contracts and runtime artifacts through controlled environments.

## 17. Related project documents

- `docs/shared-memory-platform.md`
- `docs/agent-memory-setup.md`
- `docs/domain-onboarding.md`
- `docs/adk-web-demo.md`
- `docs/shared-memory-platform.drawio`
- `docs/agent-memory-flows.drawio`

