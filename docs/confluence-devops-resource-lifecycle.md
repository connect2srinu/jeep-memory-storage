# Shared Memory Platform: DevOps Resources and Deployment Lifecycle

| Document field | Value |
|---|---|
| Audience | DevOps, platform operations, SRE, cloud administrators, and release engineers |
| Purpose | Describe cloud resources, ownership, creation timing, deployment, promotion, and operations |
| Deployment entry point | `python scripts/deploy.py` |
| Important boundary | Validation and compilation do not modify Google Cloud |

## 1. Deployment outcome

The deployment packages the ADK application, creates or updates an Agent Runtime, and optionally
attaches compiled Memory Profile schemas to its Memory Bank configuration. Managed Sessions and
Memory Bank use the configured Agent Platform resource IDs.

```text
Source repository
  |
  +--> CI: validate YAML, compile check, tests            No cloud changes
  |
  +--> Release job: authenticate, preflight, deploy       Cloud changes begin here
                              |
                              +--> staging bucket
                              +--> Agent Runtime
                              +--> Agent Identity
                              +--> Sessions / Memory Bank context
                              +--> structured Memory Profile schemas
```

## 2. Resource inventory

| Resource or configuration | Created by current script? | Creation/update point | Lifecycle owner |
|---|---:|---|---|
| Google Cloud project | No | Before onboarding | Cloud foundation team |
| Billing and organization policy | No | Before onboarding | Cloud foundation team |
| Required Google Cloud APIs | No | Before deployment | Cloud foundation/DevOps |
| Deployment principal and credentials | No | Before deployment | IAM/DevOps |
| Agent staging Cloud Storage bucket | Yes, if absent | `scripts/deploy.py` | DevOps |
| Agent Runtime / reasoning engine | Yes | First `scripts/deploy.py` without an existing ID | Agent platform team |
| Existing Agent Runtime update | Yes | `scripts/deploy.py` with `GOOGLE_CLOUD_AGENT_ENGINE_ID` | Agent platform team |
| Agent Identity | Requested by deployment config | Agent Runtime create/update | Agent platform/IAM |
| Application package and Python dependencies | Yes | Agent Runtime create/update | Release pipeline |
| Memory Bank configuration | Attached to Agent Runtime | Deploy when profiles are enabled | Memory platform team |
| Structured Memory Profile schemas | Compiled locally; deployed in `context_spec` | Agent Runtime create/update | Memory platform/domain owners |
| Managed Sessions | Used through resource ID | Runtime; no separate create command in this repository | Agent platform team |
| Dynamic Memory Bank memories | No initial bulk creation | Runtime authorized writes | Domain workflows |
| Structured Memory Profile values | No | Explicit generation or sync after schema deployment | Profile generation workflow |
| Candidate approval store | No | Not implemented; POC is process memory | Production platform backlog |
| Snapshot/cache service | No | Not implemented; POC is process memory | Production platform backlog |
| Logging, dashboards, alerts, audit sinks | No | Must be provisioned separately | SRE/security |

The deployment currently supports using one Agent Platform resource ID for Runtime, Sessions, and
Memory Bank. Separate IDs can be supplied for Sessions and Memory Bank when the environment design
requires separation.

## 3. What each pipeline stage changes

### 3.1 Pull request and CI

The workflow in `.github/workflows/memory-contracts.yml` performs:

```bash
python -m pip install -e '.[dev]'
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py --check
python -m pytest -q
```

This stage reads repository files only. It does not create a bucket, runtime, session, memory, or
profile.

### 3.2 Local contract compilation

```bash
python scripts/compile_memory_contract.py
```

This writes deterministic files inside the repository. It does not call Google Cloud. Generated
changes must be committed and reviewed with the source YAML.

### 3.3 Initial deployment

When `GOOGLE_CLOUD_AGENT_ENGINE_ID` is empty, `scripts/deploy.py`:

1. verifies that generated artifacts match all YAML contracts;
2. verifies project and staging-bucket settings;
3. creates the staging bucket if it does not already exist;
4. packages the `app` directory and pinned runtime requirements;
5. creates a new Agent Runtime with Agent Identity;
6. attaches compiled Memory Profile configuration when enabled;
7. prints the new resource ID for `.env` or secret-manager configuration.

### 3.4 Update deployment

When `GOOGLE_CLOUD_AGENT_ENGINE_ID` is set, the script constructs the full resource name and calls
the Agent Runtime update operation. This prevents accidental creation of another runtime.

An update can change:

- agent application code;
- packaged dependencies;
- model-facing tools and instructions;
- Memory Profile schemas in `context_spec`;
- runtime display/configuration values represented in the script.

An update does not automatically migrate, correct, or delete existing user memories.

### 3.5 Profile data generation

After profile schemas are deployed, this command submits a cloud-mutating generation event:

```bash
python scripts/generate_profile.py \
  --user-id DEMO_USER \
  --domain grocery \
  --text "I prefer organic groceries and usually allow substitutions."
```

The script uses the configured Memory Bank resource and the standard scope:

```text
user_id + app_name + domain
```

Schema deployment and profile population are deliberately separate operations.

## 4. Environment configuration

Start from `.env.example`. Store production values in the deployment system's secret/configuration
facility rather than committing `.env`.

| Variable | Required | Purpose |
|---|---:|---|
| `GOOGLE_CLOUD_PROJECT` | Yes | Project containing Agent Platform resources |
| `GOOGLE_CLOUD_LOCATION` | Yes | Common supported region, default `us-central1` |
| `GOOGLE_GENAI_USE_VERTEXAI` | Yes | Uses Vertex AI-backed model access |
| `GOOGLE_GENAI_USE_ENTERPRISE` | Yes | Enables Enterprise Agent Platform behavior |
| `GEMINI_MODEL` | Yes | Gemini model used by the ADK agent |
| `ADK_APP_NAME` | Yes | Application scope component used by memory |
| `PREFERENCE_DOMAIN` | Runtime-specific | Default consumer domain for the reference app |
| `MINIMUM_MEMORY_CONFIDENCE` | Yes | Runtime minimum memory confidence |
| `ENABLE_MEMORY_PROFILES` | Yes | Includes structured profile schemas during deployment |
| `GOOGLE_CLOUD_AGENT_ENGINE_ID` | After first deploy | Runtime ID and fallback for Sessions/Memory Bank |
| `AGENT_PLATFORM_SESSIONS_ID` | Optional | Explicit Sessions backing resource override |
| `AGENT_PLATFORM_MEMORY_BANK_ID` | Optional | Explicit Memory Bank backing resource override |
| `AGENT_PLATFORM_STAGING_BUCKET` | Yes for deploy | Bucket URI such as `gs://agent-staging-env-name` |
| `RUN_GCP_INTEGRATION_TESTS` | CI-controlled | Explicit opt-in for cloud integration tests |

Use different resource IDs, buckets, and application names for development, test, staging, and
production. Never point a developer workstation at production memory by default.

## 5. Prerequisites owned outside this repository

Before the first deployment, DevOps must provide:

1. a Google Cloud project with billing and approved organization policies;
2. the required Agent Platform, Vertex AI, Cloud Storage, logging, monitoring, and IAM APIs;
3. an approved region shared by Runtime, Sessions, Memory Bank, model, and staging resources;
4. a deployment identity with least-privilege create/update permissions;
5. runtime identity access to the required models and memory/session operations;
6. private networking, service perimeter, CMEK, and egress controls where required;
7. centralized logging, audit retention, alert routing, and incident ownership;
8. a secret/configuration mechanism for resource IDs and environment settings.

IAM role names and service permissions evolve. Resolve the exact role set from the approved Google
Cloud service documentation and organizational policy at deployment time; do not grant project
Owner to either the deployment or runtime principal.

## 6. Recommended environment topology

```text
Development project
  staging bucket: dev
  Agent Runtime: dev
  Sessions/Memory Bank: dev
  synthetic users only

Test project
  staging bucket: test
  Agent Runtime: test
  Sessions/Memory Bank: test
  integration and isolation suites

Production project
  staging bucket: prod
  Agent Runtime: prod
  Sessions/Memory Bank: prod
  approved identities, SLOs, retention, and audit controls
```

For sensitive or strict-isolation domains, evaluate separate Memory Bank resources rather than
placing all profile schemas in one shared structured-memory configuration.

## 7. Deployment runbook

### 7.1 Preflight

```bash
cd geap-memory
source .venv/bin/activate
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py --check
python -m pytest -q
gcloud auth application-default print-access-token >/dev/null
```

Review the generated diff before deployment:

```bash
git diff -- config/contracts app/shared_memory config/generated config/schemas
```

### 7.2 Deploy

```bash
set -a
source .env
set +a
python scripts/deploy.py
```

On first deployment, capture the printed IDs in the environment's managed configuration:

```text
GOOGLE_CLOUD_AGENT_ENGINE_ID=...
AGENT_PLATFORM_SESSIONS_ID=...
AGENT_PLATFORM_MEMORY_BANK_ID=...
```

Do not leave the runtime ID empty on subsequent deployments. An empty ID causes the script to take
the create path.

### 7.3 Smoke test

```bash
./scripts/start_adk_web.sh
```

In another terminal, run the deterministic local acceptance test and cloud inspection commands:

```bash
python scripts/validate_platform.py
python scripts/inspect_memory.py --user-id DEPLOYMENT_TEST_USER --domains grocery
```

Use a new synthetic user ID for each destructive or profile-generation test.

## 8. Contract and schema release lifecycle

```text
Domain proposal
  -> domain owner review
  -> platform validation
  -> security/privacy review
  -> generated artifact review
  -> merge
  -> deploy to development
  -> cloud integration tests
  -> deploy to test/staging
  -> compatibility and migration checks
  -> production approval
  -> production update
  -> observe and verify
```

A schema change requires more than a successful runtime update. The release must define:

- backward compatibility with existing profile records;
- whether `schemaVersion` changes;
- value migration or regeneration strategy;
- behavior when old and new fields coexist;
- rollback behavior;
- retention and deletion impact;
- consumer compatibility and rollout order.

## 9. Current Memory Profile deployment risk

Schemas with identical scope-key lists are grouped into one `structured_memory_configs` entry. A
scope such as `{user_id, app_name, domain}` selects the configuration by key presence; it does not
select only the schema whose owner equals the value of `domain`.

Operational impact:

- one domain event can be evaluated against several schemas;
- incorrect cross-schema profile fields can be generated;
- local alias normalization can make a returned field appear owned by another domain;
- deploying another schema with the same signature increases that risk.

Production release gates must therefore require schema-owner admission filtering in the runtime.
Until that control is implemented and tested, do not treat generated cross-domain profile fields as
authoritative production data. For high-risk domains, use resource-level isolation.

## 10. Monitoring and alerting

Provision dashboards and alerts for:

| Signal | Operational concern |
|---|---|
| Agent Runtime request latency/error rate | Availability and SLO |
| Session read/write errors | Loss of temporary preference behavior |
| Memory retrieval/generation latency and errors | Long-term context degradation |
| `NOT_PERSISTED` dispositions | User-facing false-success risk |
| `CROSS_DOMAIN_CANDIDATE` volume and age | Approval backlog or extraction problem |
| Schema-owner mismatch rejection | Cross-schema contamination |
| Unauthorized read/write decisions | Misconfiguration or abuse |
| Snapshot hit/miss/invalidation | Performance and stale-context risk |
| Profile generation volume per domain | Cost and unexpected ingestion |
| Staging bucket growth | Cost and lifecycle management |

Logs must avoid raw sensitive preference values. Use trace/correlation IDs and protected audit
records when an investigation needs value-level access.

## 11. Backup, retention, correction, and deletion

The current repository does not implement a complete lifecycle controller. Production operations
must add:

- domain-specific retention enforcement;
- user correction and right-to-forget requests;
- profile and dynamic-memory deletion with exact validated scopes;
- durable candidate/audit retention;
- legal hold behavior where applicable;
- reconciliation between authoritative profile data and Memory Profiles;
- evidence that derived snapshots were invalidated.

Never use broad recursive deletion or an unvalidated user/domain scope. Require a preview, approval,
and audit record for production deletion.

## 12. Rollback

Application rollback and data rollback are different operations.

### Application/configuration rollback

1. revert to the last approved commit;
2. validate contracts and generated artifacts;
3. run tests;
4. deploy to the existing runtime ID;
5. verify context resolution and error metrics.

### Data correction

Reverting code does not remove profiles or memories created by the newer release. Use an approved,
scope-specific correction/migration tool. The current POC does not provide a production deletion
workflow.

## 13. Teardown

Teardown is intentionally not automated by this repository. Removing an Agent Runtime, Memory Bank,
Sessions data, or staging bucket is destructive and may affect user data. DevOps must:

1. resolve exact resource names and environment ownership;
2. export or retain required audit evidence;
3. stop generation and runtime traffic;
4. apply retention/legal-hold policy;
5. receive explicit approval;
6. delete resources with provider-supported lifecycle operations;
7. verify deletion and remove managed configuration references.

## 14. Production readiness gate

Do not promote to production until all of the following are true:

- schema-owner admission filtering is implemented and integration-tested;
- candidate and audit repositories are durable and tenant-scoped;
- owner approval and authoritative profile update workflows exist;
- identities are cryptographically bound to registered consumers;
- data lifecycle and deletion workflows are tested;
- environment isolation and least-privilege IAM are reviewed;
- dashboards, alerts, runbooks, and on-call ownership exist;
- rollback and schema migration have been exercised;
- load, quota, cost, failure, and regional recovery tests meet the agreed SLO.

## 15. Related project documents

- `docs/confluence-platform-developer-architecture.md`
- `docs/confluence-domain-onboarding-demo.md`
- `docs/domain-onboarding.md`
- `docs/adk-web-demo.md`
- `.env.example`
- `.github/workflows/memory-contracts.yml`

