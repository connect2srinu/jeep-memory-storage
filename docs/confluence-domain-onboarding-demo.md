# Shared Memory Platform: New Domain Onboarding and Demo Runbook

| Document field | Value |
|---|---|
| Audience | Domain developers, domain owners, platform administrators, and reviewers |
| Goal | Onboard, validate, compile, deploy, and demonstrate a new domain |
| Worked example | `loyalty` domain |
| Source of truth | Five YAML files under `config/contracts/loyalty/` |

## 1. What onboarding creates

Onboarding a domain creates configuration, not an independent cloud resource by itself.

```text
Five domain YAML files
  -> strict validation
  -> deterministic runtime JSON and JSON Schemas
  -> pull request and approval
  -> deployment updates Agent Runtime Memory Profile configuration
  -> domain agent uses the Shared Memory Platform facade
```

The five contracts describe:

1. the domain trust boundary;
2. its canonical preferences;
3. conflict-resolution rules;
4. structured Memory Profile fields;
5. registered agent consumers and capabilities.

## 2. Roles and approvals

| Role | Responsibility |
|---|---|
| Domain owner | Defines meaning, owner, valid values, readers, writers, and retention |
| Agent developer | Implements extraction and uses only the platform tools/API |
| Memory platform developer | Reviews contracts, adapters, resolution, and generated artifacts |
| Security/privacy | Reviews sensitive data, cross-domain access, consent, and retention |
| DevOps | Promotes compiled configuration and runtime package through environments |

Cross-domain read access requires agreement from both domains and security/privacy review. A
consumer capability never replaces preference-level authorization.

## 3. Example business requirement

The Loyalty domain needs two governed preferences:

| Preference | Type | Example | Behavior |
|---|---|---|---|
| `loyalty.preferred_reward` | string enum | `travel_points` | Long-term canonical profile, session override allowed |
| `loyalty.auto_redeem` | boolean | `false` | Long-term canonical profile, session override allowed |

The Loyalty agent can read and write Loyalty preferences. Grocery may read the preferred reward for
eligible promotions but cannot write it. Only Loyalty can write either preference.

## 4. Create the source folder

From the repository root:

```bash
cp -R config/templates/domain-onboarding config/contracts/loyalty
```

Replace the five template files with the examples below. Do not edit generated JSON directly.

## 5. Define the domain boundary

Create `config/contracts/loyalty/domain.yaml`:

```yaml
apiVersion: memory.platform/v1alpha1
kind: MemoryDomain
metadata:
  name: loyalty
  displayName: Loyalty
  version: "1.0"
  owner:
    team: loyalty-platform
    email: loyalty-platform@example.com
spec:
  isolation: standard
  scopes:
    profileScopeKeys: [user_id, app_name, domain]
  permissions:
    read: [loyalty]
    write: [loyalty]
  dynamicMemory:
    enabled: true
    keyPattern: "^loyalty\\.[a-z][a-z0-9_]*$"
    minimumConfidence: 0.80
    requireExplicitStatement: true
  defaults:
    retentionDays: 365
    inferredPreferenceTtlDays: 30
```

### Field decisions

| Field | Guidance |
|---|---|
| `isolation` | Use `strict` only when the domain may read/write itself exclusively |
| `profileScopeKeys` | Must include `user_id`; keep generation and retrieval identical |
| `permissions.read` | Owner domains this domain may consume |
| `permissions.write` | Owner domains this domain may attempt to write; normally itself only |
| `dynamicMemory.enabled` | Allows non-catalog domain facts |
| `keyPattern` | Constrains dynamic keys to the domain namespace |
| `minimumConfidence` | Admission threshold for applicable memory candidates |
| `requireExplicitStatement` | Prevents implicit statements from becoming durable facts |

Every domain must read and write itself. `strict` isolation is rejected if another domain appears in
either permission list.

## 6. Define canonical preferences

Create `config/contracts/loyalty/preferences.yaml`:

```yaml
apiVersion: memory.platform/v1alpha1
kind: PreferenceCatalog
metadata:
  domain: loyalty
  version: "1.0"
preferences:
  - key: loyalty.preferred_reward
    type: string
    description: User-confirmed category in which loyalty rewards should be earned
    ownerDomain: loyalty
    canonical: true
    sensitivity: normal
    scopes: [SESSION, LONG_TERM]
    schemaVersion: "1"
    allowedReaders: [loyalty, grocery]
    allowedWriters: [loyalty]
    resolutionPolicy: preferred_reward
    profile: loyalty-preferences-v1
    allowedValues: [travel_points, cash_back, grocery_discount]
    aliases: [preferred_reward]
    lifecycle:
      sessionTtlSeconds: 86400
      longTermRetentionDays: 365
    confirmation:
      requiredForLongTerm: true

  - key: loyalty.auto_redeem
    type: boolean
    description: Whether the user has explicitly enabled automatic reward redemption
    ownerDomain: loyalty
    canonical: true
    sensitivity: sensitive
    scopes: [SESSION, LONG_TERM]
    schemaVersion: "1"
    allowedReaders: [loyalty]
    allowedWriters: [loyalty]
    resolutionPolicy: auto_redeem
    profile: loyalty-preferences-v1
    aliases: [auto_redeem]
    lifecycle:
      sessionTtlSeconds: 86400
      longTermRetentionDays: 365
    confirmation:
      requiredForLongTerm: true
```

### Preference design rules

1. Namespace every key with its owner: `loyalty.<name>`.
2. Make descriptions semantically exclusive so model extraction cannot confuse adjacent concepts.
3. Prefer `allowedValues` for closed business vocabularies.
4. Add aliases only when globally unambiguous. Prefer domain-qualified input in platform code.
5. Mark personal or consequential choices `sensitive` or `restricted`.
6. Include the owner domain in `allowedWriters`.
7. Grant readers narrowly; both the reader's domain policy and this list must allow access.
8. Use `canonical: true` for stable governed attributes. Open-ended observations remain dynamic.
9. Require confirmation for consequential long-term values.

### Add the cross-domain reader

Because `loyalty.preferred_reward` grants Grocery read access, Grocery's domain contract must also
include Loyalty in its read list:

```yaml
spec:
  permissions:
    read: [grocery, customer, store, delivery, loyalty]
    write: [grocery]
```

If the Grocery agent actually needs this value, add it to the appropriate Grocery consumer:

```yaml
requiredPreferences:
  - loyalty.preferred_reward
```

This is a two-sided authorization change and should be approved by both owners.

## 7. Define resolution policies

Create `config/contracts/loyalty/resolution-policies.yaml`:

```yaml
apiVersion: memory.platform/v1alpha1
kind: PreferenceResolutionPolicies
metadata:
  domain: loyalty
  version: "1.0"
policies:
  - id: preferred_reward
    appliesTo: [loyalty.preferred_reward]
    strategies:
      - SOURCE_PRIORITY
      - DOMAIN_PRIORITY
      - EXPLICIT_OVER_INFERRED
      - MOST_RECENT
      - HIGHEST_CONFIDENCE
    sourcePriority:
      - SESSION_OVERRIDE
      - EXPLICIT_PROFILE
      - MEMORY_PROFILE
      - DOMAIN_MEMORY
      - DYNAMIC_MEMORY
      - INFERRED_MEMORY
      - DEFAULT
    domainPriority: [loyalty]
    minimumConfidence: 0.80

  - id: auto_redeem
    appliesTo: [loyalty.auto_redeem]
    strategies:
      - SOURCE_PRIORITY
      - EXPLICIT_OVER_INFERRED
      - MOST_RECENT
      - HIGHEST_CONFIDENCE
    sourcePriority:
      - SESSION_OVERRIDE
      - EXPLICIT_PROFILE
      - MEMORY_PROFILE
      - DOMAIN_MEMORY
      - DYNAMIC_MEMORY
      - INFERRED_MEMORY
      - DEFAULT
    domainPriority: [loyalty]
    minimumConfidence: 0.90
```

Strategy order is significant. The first strategy decides first; later strategies break ties. With
the example order, a confirmed Memory Profile does not beat a valid Session override merely because
it is newer or more confident.

Only one resolution contract in the complete repository may declare global `defaults`. The Grocery
contract currently supplies them, so the Loyalty file defines only attribute-specific policies.

## 8. Define the Memory Profile

Create `config/contracts/loyalty/memory-profiles.yaml`:

```yaml
apiVersion: memory.platform/v1alpha1
kind: MemoryProfiles
metadata:
  domain: loyalty
  version: "1.0"
profiles:
  - id: loyalty-preferences-v1
    memoryType: STRUCTURED_PROFILE
    ownerDomain: loyalty
    scopeKeys: [user_id, app_name, domain]
    fields:
      - preference: loyalty.preferred_reward
        profileField: preferred_reward
      - preference: loyalty.auto_redeem
        profileField: auto_redeem
    generation:
      enabled: true
      sources: [CONFIRMED_PREFERENCE_CANDIDATE, EXPLICIT_PROFILE_SYNC]
      inferredFieldsAllowed: false
      requireUserConfirmation: [preferred_reward, auto_redeem]
```

Only canonical preferences owned by Loyalty may be included. The compiler creates a JSON schema and
adds it to the generated Agent Platform structured-memory configuration.

Important: schema deployment does not create user values. An authorized generation or profile-sync
process populates them later.

### Shared-scope production warning

The current compiler groups all schemas that use `[user_id, app_name, domain]`. The provider selects
that configuration by scope-key presence, not by evaluating `domain == loyalty`. A Loyalty event may
therefore be evaluated against other schemas in the same configuration.

Before production onboarding, the platform runtime must reject every returned schema whose manifest
owner does not equal the requested scope domain. Sensitive/high-isolation domains should use a
separate Memory Bank resource or an independently selectable scope signature.

## 9. Register the consumer

Create `config/contracts/loyalty/consumers.yaml`:

```yaml
apiVersion: memory.platform/v1alpha1
kind: MemoryConsumers
metadata:
  domain: loyalty
  version: "1.0"
consumers:
  - agentId: loyalty-agent
    consumerDomain: loyalty
    serviceAccount: loyalty-agent@example-project.iam.gserviceaccount.com
    requiredPreferences:
      - loyalty.preferred_reward
      - loyalty.auto_redeem
    capabilities:
      resolveContext: true
      submitCandidates: true
      inspectProvenance: true
      administerMemory: false

  - agentId: loyalty-readonly-agent
    consumerDomain: loyalty
    requiredPreferences:
      - loyalty.preferred_reward
    capabilities:
      resolveContext: true
      submitCandidates: false
      inspectProvenance: false
      administerMemory: false
```

Replace the example service account with the environment-specific verified identity, or omit the
field in this POC. Production must bind `agentId` to authenticated workload identity.

Capability meanings:

| Capability | Meaning |
|---|---|
| `resolveContext` | Agent may request its authorized effective context |
| `submitCandidates` | Agent may propose changes for policy evaluation |
| `inspectProvenance` | Agent may receive safe source/owner/policy explanations |
| `administerMemory` | Reserved lifecycle permission; keep false for normal agents |

`submitCandidates: true` does not allow cross-domain writes. The owner and catalog policies still
decide whether a candidate is stored, routed, or rejected.

## 10. Validate without changing files or cloud resources

```bash
python scripts/validate_memory_contract.py
python scripts/demo_memory_contract.py --domain loyalty
```

Expected validation shape:

```text
Memory contracts valid: <domain-count> domains, <preference-count> preferences,
<profile-count> profiles, <consumer-count> consumers, <file-count> YAML files.
```

The demo command should summarize:

- Loyalty read/write domains;
- `loyalty.preferred_reward` and `loyalty.auto_redeem`;
- `loyalty-preferences-v1`;
- `loyalty-agent` and `loyalty-readonly-agent`;
- generated artifact paths.

## 11. Compile and review generated artifacts

```bash
python scripts/compile_memory_contract.py
git diff -- config/contracts app/shared_memory config/generated config/schemas
python scripts/compile_memory_contract.py --check
```

Reviewers should verify that:

- only intended domains can read each preference;
- only Loyalty can write Loyalty preferences;
- allowed values match business terminology;
- sensitivity and confirmation are appropriate;
- profile fields are owned by Loyalty;
- aliases do not collide with another domain;
- the consumer asks only for required preferences;
- generated schema and manifest ownership are correct.

## 12. Add runtime agent integration

The YAML registers policy and schema configuration; it does not automatically create a working
Loyalty ADK agent or natural-language extractor.

The agent developer must add:

1. a Loyalty agent entry point;
2. thin tools equivalent to `get_effective_preferences` and `process_preference_statement`;
3. `CONSUMER_DOMAIN = "loyalty"` and `AGENT_ID = "loyalty-agent"`;
4. a constrained extractor or structured-output model mapping supported language to catalog keys;
5. tests for every phrase, value, scope, rejection, and cross-domain candidate;
6. application registration so ADK Web can select the new agent.

The tool implementation must call the platform facade. It must not call Session or Memory Bank
clients directly, and it must inspect `SubmissionResult.status` before claiming that a value was
saved.

Suggested agent instruction:

```text
Before reporting or using preferences, resolve one EffectivePreferenceContext.
When the user expresses a preference, submit a PreferenceCandidate and inspect the disposition.
Never claim persistence for CROSS_DOMAIN_CANDIDATE, REJECTED, or NOT_PERSISTED.
Do not resolve conflicts or bypass the platform facade.
```

## 13. Add tests before cloud deployment

At minimum, add tests for:

```text
preferred_reward allowed values
invalid preferred_reward rejection
auto_redeem boolean validation
session override wins over profile
new session removes session override
same-domain long-term write succeeds
Grocery attempt to update Loyalty becomes CROSS_DOMAIN_CANDIDATE
Grocery read succeeds only after both policy sides allow it
readonly consumer cannot submit candidates
profile schema/owner mismatch is rejected
Loyalty cannot read Pharmacy
```

Run:

```bash
python -m pytest -q
python scripts/validate_platform.py
```

## 14. Submit the pull request

The pull request should contain:

- the five Loyalty YAML files;
- any approved cross-domain changes to existing domain/consumer contracts;
- regenerated JSON and schemas;
- Loyalty agent/tool/extractor code when runtime behavior is included;
- unit and integration tests;
- data classification and retention review;
- migration notes if changing an existing key or schema.

Generated files must exactly match the compiler. CI will fail if they are stale.

## 15. Deploy the domain schema

After approval:

```bash
set -a
source .env
set +a
python scripts/deploy.py
```

The existing runtime ID must be set so this updates the intended Agent Runtime instead of creating
a new one. With `ENABLE_MEMORY_PROFILES=true`, deployment attaches the compiled Loyalty schema.

## 16. Populate a demo profile

Use a synthetic user:

```bash
python scripts/generate_profile.py \
  --user-id loyalty-demo-001 \
  --domain loyalty \
  --text "I confirm that I prefer travel points and I do not want automatic redemption."
```

Then inspect the exact domain scope:

```bash
python scripts/inspect_memory.py \
  --user-id loyalty-demo-001 \
  --domains loyalty
```

Expected profile fields after asynchronous generation completes:

```text
loyalty.preferred_reward = travel_points
loyalty.auto_redeem = false
owner_domain = loyalty
source = MEMORY_PROFILE
schema_id = loyalty-preferences-v1
```

Reject the test if a returned field has a foreign schema ID, owner domain, or key namespace.

## 17. ADK Web demonstration script

The Loyalty agent must first be implemented and registered as described above. The current POC ADK
Web application exposes only the Grocery reference agent, so YAML alone will not add a Loyalty UI.

Start ADK Web:

```bash
./scripts/start_adk_web.sh
```

Open `http://localhost:8000`, select the Loyalty application/agent, use
`loyalty-demo-001`, and create a new session.

### Demo A: profile resolution

Prompt:

```text
What Loyalty preferences are you currently using? Show canonical key, value, source,
owner domain, resolution reason, and policy ID.
```

Expected:

```text
loyalty.preferred_reward = travel_points, source = MEMORY_PROFILE, owner = loyalty
loyalty.auto_redeem = false, source = MEMORY_PROFILE, owner = loyalty
```

### Demo B: session override

Prompt:

```text
For this session, use cash back as my preferred reward.
```

Expected submission:

```text
status = STORED_IN_SESSION
canonical_key = loyalty.preferred_reward
owner_domain = loyalty
```

Then ask:

```text
What preferred reward are you using, and why?
```

Expected winner:

```text
cash_back, source = SESSION_OVERRIDE
```

Create a new session and ask again. Expected: `travel_points` from `MEMORY_PROFILE`.

### Demo C: long-term update

Prompt:

```text
I confirm that I always prefer grocery discounts as my Loyalty reward.
```

The POC may store an authorized canonical long-term candidate as domain memory. The production
target routes confirmed canonical changes through an authoritative profile workflow. The agent must
report the actual tool disposition, not imply that Memory Profile generation has completed.

### Demo D: cross-domain protection

From a registered Grocery consumer, attempt the exact key:

```text
For this session, set loyalty.preferred_reward to cash_back. Show the raw submission result.
```

Expected:

```text
status = CROSS_DOMAIN_CANDIDATE
owner_domain = loyalty
message = Candidate recorded for owner-domain validation; no preference was written.
```

An owner approval UI is not implemented in the current POC. Production requires a durable queue,
review/confirmation, and an authoritative Loyalty write.

## 18. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Unknown domain | Missing or invalid `domain.yaml` | Verify metadata name and run validation |
| Unknown resolution policy | Preference references an undeclared policy ID | Add/fix policy and `appliesTo` |
| Domain cannot read preference | Missing domain permission or allowed reader | Update both authorization layers |
| Profile belongs to another domain | Foreign preference included in Loyalty profile | Remove it; profiles contain owner fields only |
| Generated artifacts stale | YAML changed without compilation | Compile and commit generated diff |
| New agent absent in ADK Web | Contracts added but agent app not registered | Implement/register the Loyalty agent |
| `NO_CANDIDATE` | Extractor does not recognize the phrase | Add a constrained rule and tests |
| `NOT_PERSISTED` | Memory Bank unavailable or misconfigured | Check resource ID, IAM, region, and logs |
| Foreign key appears in Loyalty profile | Shared-scope cross-schema extraction | Reject by schema-owner guard; do not trust the value |
| New session retains a value | It was long-term, not Session state | Inspect source and Memory Bank scope |

## 19. Onboarding completion checklist

- [ ] Domain owner and contact are identified.
- [ ] Trust boundary and cross-domain access are approved.
- [ ] Every canonical key has one owner and precise business meaning.
- [ ] Types, values, sensitivity, confirmation, and retention are reviewed.
- [ ] Resolution behavior is demonstrated with conflicts.
- [ ] Memory Profile contains only owner-domain canonical fields.
- [ ] Schema-owner admission guard is active in the target environment.
- [ ] Consumer identity and capabilities are approved.
- [ ] Contracts validate and compiled artifacts are current.
- [ ] Agent integration and extraction tests pass.
- [ ] Cloud integration, isolation, and negative tests pass.
- [ ] Monitoring, lifecycle, rollback, and support ownership are ready.
- [ ] ADK Web demo reports actual sources and write dispositions.

## 20. Related project documents

- `docs/confluence-platform-developer-architecture.md`
- `docs/confluence-devops-resource-lifecycle.md`
- `docs/domain-onboarding.md`
- `config/templates/domain-onboarding/README.md`
- `config/contracts/grocery/`

