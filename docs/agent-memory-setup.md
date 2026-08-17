# Agent Memory Setup

| Document field | Value |
|---|---|
| Platform | Google ADK and Gemini Enterprise Agent Platform |
| Capability | Multi-domain preference memory and deterministic resolution |
| Reference consumer | Grocery agent |
| Configuration model | Reviewed YAML contracts compiled into runtime artifacts |
| Status | Production-structured proof of concept |

## 1. Purpose

The Shared Memory Platform allows registered domain agents to use Session state, authoritative
profiles, structured Memory Profiles, and dynamic Memory Bank facts through one authorized,
deterministic facade.

Agents do not query those backends directly and do not decide which conflicting value wins. The
platform authenticates the consumer, enforces domain ownership, normalizes source records, applies
resolution policy, and returns one `EffectivePreferenceContext`.

This document is the central setup and flow guide. Detailed audience-specific material is available
in:

- [Platform developer architecture](confluence-platform-developer-architecture.md)
- [DevOps resources and lifecycle](confluence-devops-resource-lifecycle.md)
- [New-domain onboarding demo](confluence-domain-onboarding-demo.md)
- [Interactive ADK Web demo](adk-web-demo.md)
- [Domain onboarding reference](domain-onboarding.md)

The accompanying [draw.io flow diagrams](agent-memory-flows.drawio) contain seven pages covering
contracts, reads, writes, profile generation, contextual overrides, deployment, and production
controls.

## 2. Architecture summary

```text
Configuration plane

Domain YAML contracts
  -> Pydantic and cross-reference validation
  -> deterministic compiler
  -> runtime JSON + JSON Schemas + profile manifest
  -> pull request / CI / approvals
  -> Agent Runtime deployment

Runtime plane

ADK domain agent
  -> thin platform tool/API
  -> consumer capability check
  -> domain and preference authorization
  -> Session + profile + Memory Profile + dynamic-memory retrieval
  -> normalization and schema-owner admission guard
  -> deterministic resolution
  -> EffectivePreferenceContext
```

The platform owns storage integration, authorization, resolution, provenance, and lifecycle.
Domain teams own preference meaning, valid values, ownership, readers/writers, profile fields, and
attribute-level resolution intent.

## 3. Repository structure

| Path | Use |
|---|---|
| `config/contracts/<domain>/` | Source-of-truth YAML for domain onboarding |
| `config/templates/domain-onboarding/` | Five-file starter bundle |
| `app/shared_memory/contracts/` | Contract models, validation, and compiler |
| `app/shared_memory/catalog/` | Canonical preference keys and metadata |
| `app/shared_memory/policies/` | Domain permissions and resolution policies |
| `app/shared_memory/auth/` | Consumer capabilities and read/write authorization |
| `app/shared_memory/adapters/` | Session, explicit-profile, Memory Profile, and Memory Bank adapters |
| `app/shared_memory/services/` | Context assembly and update routing |
| `app/shared_memory/resolver/` | Pure deterministic conflict selection |
| `app/tools/preference_tools.py` | ADK-facing platform tools |
| `scripts/validate_memory_contract.py` | Read-only YAML validation |
| `scripts/compile_memory_contract.py` | Runtime artifact generation and drift check |
| `scripts/deploy.py` | Agent Runtime and Memory Profile configuration deployment |
| `scripts/generate_profile.py` | Explicit profile-generation event submission |
| `scripts/inspect_state.py` | Managed Session inspection |
| `scripts/inspect_memory.py` | Normalized Memory Profile and dynamic-memory inspection |

## 4. Domain contracts

Each domain supplies five YAML documents.

| File | Defines |
|---|---|
| `domain.yaml` | Owner, scope keys, isolation, read/write domains, and dynamic-memory policy |
| `preferences.yaml` | Canonical keys, types, values, owner, sensitivity, scope, lifecycle, and access |
| `resolution-policies.yaml` | Strategy order, source priority, domain priority, and confidence |
| `memory-profiles.yaml` | Canonical structured profile fields and generation intent |
| `consumers.yaml` | Agent identity, required preferences, and platform capabilities |

Validate and compile them with:

```bash
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py
python scripts/compile_memory_contract.py --check
```

The compiler generates:

```text
app/shared_memory/catalog/catalog.json
app/shared_memory/policies/domain_policy.json
app/shared_memory/policies/resolution_policy.json
app/shared_memory/profiles/memory_profiles.json
app/shared_memory/contracts/consumers.json
config/generated/profile_manifest.json
config/schemas/*.schema.json
```

Generated files are reviewed in pull requests but must not be edited directly.

## 5. Authorization model

Authorization is intentionally layered.

### 5.1 Consumer capabilities

| Capability | Meaning |
|---|---|
| `resolveContext` | Request an authorized resolved preference context |
| `submitCandidates` | Propose a value for validation and routing; not a direct write permission |
| `inspectProvenance` | Receive safe source, owner, policy, and resolution details |
| `administerMemory` | Reserved for governed lifecycle operations; not implemented in this POC |

### 5.2 Data authorization

A read requires both:

```text
preference owner is in consumer-domain permissions.read
AND
consumer domain is in preference allowedReaders
```

A write requires both:

```text
preference owner is in consumer-domain permissions.write
AND
consumer domain is in preference allowedWriters
```

For example, Grocery may read `customer.diet` because Customer explicitly allows Grocery to read it.
Grocery cannot update that key because Customer is the owner and only Customer is an allowed writer.

Production must bind `agentId` to a verified Agent Identity or workload identity. Request content is
not an identity boundary.

## 6. Read and resolve flow

1. The agent calls `get_effective_preferences` or the resolve-context API.
2. Native ADK context supplies `user_id` and `session_id`.
3. The platform authenticates the consumer and checks `resolveContext`.
4. Domain policy returns the consumer's readable domains.
5. The platform concurrently retrieves:
   - structured Session overrides;
   - explicit authoritative profiles;
   - structured Memory Profiles;
   - domain-scoped dynamic Memory Bank facts;
   - application defaults.
6. Source adapters normalize values into `Preference` records.
7. The platform rejects invalid, expired, unauthorized, low-confidence, or schema-owner-mismatched
   candidates.
8. Candidates are grouped by logical resolution policy.
9. The pure resolver ranks them using the configured strategy order.
10. The agent receives an `EffectivePreferenceContext` with selected values and safe explanations.

Gemini formats or applies the already-resolved context. It does not choose source or domain
precedence.

## 7. Resolution policy

The default source order is:

```text
SESSION_OVERRIDE
> EXPLICIT_PROFILE
> MEMORY_PROFILE
> DOMAIN_MEMORY
> DYNAMIC_MEMORY
> INFERRED_MEMORY
> DEFAULT
```

Supported strategies are applied lexicographically in the declared order:

1. `SOURCE_PRIORITY`
2. `DOMAIN_PRIORITY`
3. `EXPLICIT_OVER_INFERRED`
4. `MOST_RECENT`
5. `HIGHEST_CONFIDENCE`

Later strategies break ties created by earlier strategies. Domain priority is attribute-specific:
Customer can be authoritative for diet while Grocery is authoritative for substitutions and
Delivery is authoritative for delivery windows.

Every winner includes `policy_id` and `resolution_reason` so the decision can be tested and
explained.

## 8. Update routing

The agent submits a `PreferenceCandidate`; it never selects the storage destination.

```text
Candidate
  -> capability check
  -> canonical key and owner lookup
  -> type, value, and scope validation
  -> write authorization
  -> disposition
```

| Situation | Disposition | Result |
|---|---|---|
| Authorized Session preference | `STORED_IN_SESSION` | Structured Session state only |
| Authorized long-term preference | `STORED_IN_DYNAMIC_MEMORY` | Domain-scoped Memory Bank fact |
| Foreign owner domain | `CROSS_DOMAIN_CANDIDATE` | Queued for owner validation; no preference write |
| Invalid value or scope | `REJECTED` | No write |
| Storage failure | `NOT_PERSISTED` | No success claim |

Grocery attempting to update `customer.diet` becomes a Customer-owned candidate. The current POC
stores candidates only in process memory. Production requires a durable, idempotent queue, an
owner/user approval flow, an authoritative profile writer, and a complete audit record.

## 9. Temporary contextual directives

A domain-specific task instruction must not overwrite another domain's authoritative profile.

Example:

```text
customer.diet = vegetarian                  owner: customer, long term
grocery.diet_override = none                owner: grocery, current session
```

The current resolver keeps these as separate logical keys. The Grocery consumer must interpret the
contextual directive, or a future policy must explicitly model how it suppresses diet application.
Creating a new session removes the Grocery override but retains the Customer profile.

## 10. Memory Profiles and dynamic memory

| Memory type | Purpose |
|---|---|
| Memory Profile | Structured, schema-backed canonical preferences |
| Dynamic memory | Open-ended domain facts stored in a versioned envelope |

The current dynamic-memory envelope is `shared-memory-preference/v2`. New writes use exact domain
scope:

```json
{
  "user_id": "USER_ID",
  "app_name": "APPLICATION_NAME",
  "domain": "OWNER_DOMAIN"
}
```

The same scope must be used for generation and retrieval.

### 10.1 Profile schema deployment

The contract compiler generates per-profile schemas and a profile manifest. When
`ENABLE_MEMORY_PROFILES=true`, `scripts/deploy.py` attaches them under:

```text
context_spec.memory_bank_config.structured_memory_configs
```

Deploying a schema does not create profile values. An authorized generation or profile-sync process
must submit confirmed events afterward.

### 10.2 Schema-owner admission guard

Structured-memory configurations are selected by the presence of scope keys. The provider does not
choose a schema using a predicate such as `domain == grocery`. Because the current compiler groups
schemas with identical scope-key signatures, one Grocery event can be evaluated against Customer,
Store, and Delivery schemas.

This can produce invalid cross-schema values such as:

```text
customer.diet = Organic
```

That value must not be trusted merely because it was returned by a profile API.

The production implementation must:

1. map `schema_id` to its owner using `config/generated/profile_manifest.json`;
2. accept a schema only when its owner matches the requested scope domain;
3. resolve fields through the schema manifest before consulting aliases;
4. require schema owner, scope domain, canonical namespace, and catalog owner to agree;
5. reject and monitor every mismatch;
6. use narrow enumerations and unambiguous descriptions for sensitive attributes;
7. use separate Memory Bank resources or independently selectable scope signatures for strict
   isolation where appropriate.

Prompt wording is not an authorization or data-quality control.

## 11. Cloud resources and creation timing

| Resource | How it is created |
|---|---|
| Google Cloud project, APIs, IAM, and organization controls | Provisioned before this repository's deployment |
| Staging bucket | Created by `scripts/deploy.py` if absent |
| Agent Runtime | Created when no runtime ID is configured; updated when an ID is supplied |
| Agent Identity | Requested by Agent Runtime deployment configuration |
| Sessions and Memory Bank | Accessed through configured Agent Platform resource IDs |
| Memory Profile schemas | Compiled locally and applied during Agent Runtime deployment |
| Profile values | Created later by generation or profile synchronization |
| Candidate approval store and managed snapshot cache | Not implemented in the POC |

Contract validation, compilation, and CI tests make no cloud changes. `scripts/deploy.py` is the
first standard cloud-mutating deployment step.

## 12. Local setup

```bash
cd geap-memory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp -n .env.example .env
gcloud auth application-default login
```

Configure `.env` with the Google Cloud project, region, staging bucket, model, and Agent Platform
resource IDs. Keep Runtime, Sessions, Memory Bank, and model access in compatible supported regions.

## 13. Deploy or update

Before deployment:

```bash
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py --check
python -m pytest -q
```

Deploy:

```bash
set -a
source .env
set +a
python scripts/deploy.py
```

If `GOOGLE_CLOUD_AGENT_ENGINE_ID` is empty, the script creates a new runtime. Preserve the printed
resource ID in managed environment configuration before the next deployment. With an existing ID,
the script updates that runtime.

## 14. Generate and inspect a demo profile

Profile generation is cloud-mutating. Use a synthetic user:

```bash
python scripts/generate_profile.py \
  --user-id demo-user-123 \
  --domain grocery \
  --text "I prefer organic groceries and usually allow substitutions."
```

Inspect normalized output:

```bash
python scripts/inspect_memory.py \
  --user-id demo-user-123 \
  --domains grocery
```

Validate that every Memory Profile entry has a consistent scope domain, owner domain, canonical key,
and schema ID. Treat any mismatch as rejected data, not as a resolver winner.

## 15. Run ADK Web

```bash
source .venv/bin/activate
./scripts/start_adk_web.sh
```

Open `http://localhost:8000`, select `app`, supply a user ID, and create a new session. The complete
interactive script is in [ADK Web Shared Memory demo](adk-web-demo.md).

Useful inspection commands are:

```bash
python scripts/inspect_state.py --user-id USER_ID --session-id SESSION_ID
python scripts/inspect_memory.py --user-id USER_ID --domains grocery,customer,delivery
```

Creating a new session removes Session overrides. It does not delete Memory Bank memories or Memory
Profiles.

## 16. Onboard another domain

```bash
cp -R config/templates/domain-onboarding config/contracts/loyalty
```

Fill all five YAML files, validate, compile, review generated changes, implement/register the domain
agent and extractor, add authorization/resolver tests, and then deploy the updated runtime.

```bash
python scripts/validate_memory_contract.py
python scripts/demo_memory_contract.py --domain loyalty
python scripts/compile_memory_contract.py
python scripts/compile_memory_contract.py --check
python -m pytest -q
```

YAML registration does not automatically create an ADK agent. The domain developer must add an agent
entry point and thin tools that use the Shared Memory Platform facade.

See [New Domain Onboarding and Demo Runbook](confluence-domain-onboarding-demo.md) for a complete
Loyalty example.

## 17. Failure behavior

Read sources degrade independently. A failed source contributes no values and adds a warning; the
resolver continues with remaining authorized sources and defaults.

Writes are fail-closed:

- authorization failure becomes a routed candidate or denial;
- validation failure becomes `REJECTED`;
- storage failure becomes `NOT_PERSISTED`;
- the agent must never convert either status into a success claim.

## 18. Production gaps

The following are required before production:

- schema-owner admission filtering and domain-aware alias resolution;
- durable candidate and immutable audit stores;
- owner approval and authoritative profile update workflows;
- verified service-identity binding and tenant isolation;
- revisioning, idempotency, migration, retention, correction, and deletion;
- managed snapshots/cache with safe invalidation;
- Cloud Logging, Monitoring, Trace, SLOs, alerts, and incident runbooks;
- load, quota, cost, failure, regional recovery, and adversarial isolation testing.

## 19. Validation commands

Run the complete current validation set:

```bash
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py --check
python -m pytest -q
python scripts/validate_platform.py
```

Expected final acceptance line:

```text
Shared Memory Platform final scenario: PASS
```
