# Agent Platform Cost & Architecture Analysis --- 2026 Refresh

## Overview

This document refreshes the earlier **Agent Platform Cost Analysis**
comparing **Cloud Run + Cloud SQL** with **Gemini Enterprise Agent
Platform (GEAP) Agent Runtime, Sessions, Memory Bank, and Memory
Profiles**.

The earlier analysis was completed near the beginning of 2026. Under the
pricing and capabilities available at that time, Cloud Run appeared
significantly less expensive. Since then, GEAP has introduced material
changes, particularly around Sessions, Memory Bank pricing, Memory
Profiles, runtime capabilities, agent identity, governance, and
observability.

The previous analysis should therefore remain as a historical baseline,
but should not be used unchanged for the current platform decision.

> **Status:** Work in progress. The figures below reuse the earlier
> workload assumptions so the impact of the platform changes can be
> understood. Final recommendations will be based on current Google
> Cloud pricing and POC/load-test results.

------------------------------------------------------------------------

# 1. Baseline Workload Assumptions

  Assumption                                                          Baseline
  ------------------------------------ ---------------------------------------
  Runtime requests per session                                              10
  Sessions per month                                                        1M
  Runtime requests per month                                               10M
  Average request duration                                           5 seconds
  Session events per runtime request                                         3
  Session events per month                                                 30M
  Memory generated                                     1 per completed session
  Memories generated per month                                              1M
  Memory retrieval assumption            1 returned memory per runtime request
  Memory retrievals per month                                              10M
  Billing month                                                        30 days

The previous runtime calculation effectively used:

`10M requests × 5 seconds = 50M compute seconds = ~13,889 compute hours`

This assumption needs validation. Agent request latency can include time
waiting for Gemini, tools, APIs, memory operations, and downstream
agents. Wall-clock latency should therefore not automatically be treated
as dedicated CPU utilization.

------------------------------------------------------------------------

# 2. Previous Cloud Run + Cloud SQL Estimate

  ------------------------------------------------------------------------
  Service               Previous Assumption          Previous Monthly Cost
  --------------------- --------------------- ----------------------------
  Cloud Run             1 vCPU, 2 GiB;                             \$50.11
                        traffic builds/fades  
                        over \~12 hours       

  Cloud SQL ---         PostgreSQL, 250 GiB,                      \$229.75
  Short-Term Memory     Enterprise Plus, 2    
                        vCPU/16 GiB, HA       
                        disabled              

  Cloud SQL ---         PostgreSQL, 250 GiB,                      \$396.78
  Long-Term Memory      Enterprise Plus, 2    
                        vCPU/16 GiB, HA       
                        enabled               

  Miscellaneous         Load balancer, Cloud                      \$100.00
                        Trace, Artifact       
                        Registry, Secret      
                        Manager, etc.         

  **Total**                                                   **\$776.60**
  ------------------------------------------------------------------------

This is useful as an infrastructure baseline. However, Cloud SQL storage
by itself is not feature-equivalent to GEAP Sessions and Memory Bank.

If Cloud Run/custom services are expected to provide equivalent
capabilities, the TCO analysis should also consider session lifecycle,
memory extraction, embeddings, semantic retrieval, ranking, retention,
profile management, provenance, agent identity, governance, agent-aware
telemetry, HA/DR, schema management, and operational support.

------------------------------------------------------------------------

# 3. Previous Managed Agent Platform Estimate

## Agent Runtime

Previous calculation:

`10M × 5 seconds ÷ 3,600 = 13,889 hours`

Estimated runtime cost: **\~\$1,450/month**

## Sessions

Previous pricing assumption:

`30M events ÷ 1,000 × $0.25 = $7,500/month`

## Memory Bank

Stored memory:

`1M ÷ 1,000 × $0.25 = $250/month`

Memory retrieval:

`10M ÷ 1,000 × $0.50 = $5,000/month`

Memory Bank total: **\$5,250/month**

  Service           Previous Monthly Cost
  --------------- -----------------------
  Agent Runtime                   \$1,450
  Sessions                        \$7,500
  Memory Bank                     \$5,250
  **Total**                  **\$14,200**

The earlier comparison was therefore:

-   **Cloud Run + Cloud SQL: \$776.60**
-   **Managed Agent Platform: \$14,200**

This made the managed option appear approximately **18× more
expensive**.

------------------------------------------------------------------------

# 4. New GEAP Changes That Require Reassessment

The largest change is the consumption model for **Sessions and Memory
Bank**.

Current published GEAP pricing introduces operation-based pricing for
these services, with the new Sessions and Memory Bank pricing taking
effect September 1, 2026.

  GEAP Capability           Current Published Rate
  -------------------- ---------------------------
  Agent Runtime CPU          \~\$0.085 / vCPU-hour
  Agent Runtime RAM           \~\$0.009 / GiB-hour
  Agent storage               \~\$0.30 / GiB-month
  Sessions reads         \~\$0.085 / 3M operations
  Sessions writes        \~\$0.085 / 1M operations
  Memory Bank reads      \~\$0.085 / 3M operations
  Memory Bank writes     \~\$0.085 / 1M operations

Model inference, memory-generation model usage, embeddings, tools/APIs,
storage, and other dependent services must be modeled separately.

The key implication is that the **\$7,500 Sessions and \$5,250 Memory
Bank estimates from the earlier analysis should not be carried forward
unchanged**.

------------------------------------------------------------------------

# 5. Illustrative Recalculation

These calculations illustrate the pricing-model impact. They are not yet
the final production estimate.

## Sessions

Baseline: 30M session events/writes per month.

Previous:

`30M ÷ 1,000 × $0.25 = $7,500`

Illustrative operation cost under the new model:

`30M ÷ 1M × $0.085 = $2.55`

Storage, reads, retention, and actual API-operation behavior still need
to be added.

## Memory Bank

Baseline:

-   1M memory writes/month
-   10M memory reads/month

Previous:

`$250 storage/generation assumption + $5,000 retrieval = $5,250`

Illustrative operation costs:

`1M writes ÷ 1M × $0.085 = $0.085`

`10M reads ÷ 3M × $0.085 ≈ $0.28`

The final Memory Bank cost must additionally include storage,
memory-generation/model usage, embeddings where applicable, retention,
and actual operation counts.

### Cost Implication

The previous managed-platform total was dominated by **\$12,750/month
for Sessions + Memory Bank**. That portion of the comparison changes
materially under the new pricing model.

Cloud Run may still have an advantage in raw runtime compute cost, but
the earlier \~18× overall difference is no longer an appropriate
current-state conclusion.

------------------------------------------------------------------------

# 6. What the Updated Comparison Must Measure

The revised study should separate **raw infrastructure cost** from
**total cost of ownership**.

  -----------------------------------------------------------------------
  Area                    Cloud Run / Custom      GEAP Managed
  ----------------------- ----------------------- -----------------------
  Runtime compute         Likely lower / highly   Agent-specific managed
                          tunable                 runtime

  Concurrency             Highly configurable     Managed agent execution

  Sessions                Custom DB/service or    Native GEAP Sessions
                          GEAP integration        

  Semantic memory         Custom/integrated       Memory Bank

  Structured memory       Custom profile store    Memory Profiles

  Agent identity          Additional integration  GEAP capability

  Governance              Additional integration  GEAP capability

  Agent observability     Additional              Agent-aware integration
                          instrumentation         

  Local execution         Strong                  Requires local/managed
                                                  pattern

  Platform engineering    Higher                  Lower

  Runtime flexibility     Higher                  More opinionated

  Portability             Higher                  Greater GEAP affinity
  -----------------------------------------------------------------------

The same representative ADK agent should be deployed to both runtimes
and tested under identical load before finalizing runtime cost.

------------------------------------------------------------------------

# 7. Memory Profiles --- New Capability to Include

The earlier comparison primarily treated memory as Cloud SQL versus
Memory Bank. The current architecture should also evaluate **Memory
Profiles**.

Memory Profiles are particularly relevant for structured preferences
that should be accessed predictably rather than repeatedly discovered
through semantic memory search.

Examples include:

-   preferred store;
-   substitution preference;
-   delivery window;
-   brand preference;
-   product preference;
-   other domain-specific preferences.

A multi-agent shared-memory scenario may include Customer, Grocery,
Store, Delivery, and other domain profiles.

------------------------------------------------------------------------

# 8. Proposed Shared Memory Pattern

``` text
Grocery Agent
      |
      v
Shared Preference / Context Service
      |
      +-------------+-------------+-------------+
      |             |             |             |
      v             v             v             v
Grocery Profile Customer Profile Store Profile Delivery Profile
      |
      +---------------------------+
                  |
                  v
             Memory Bank
       Dynamic / Semantic Memory
                  |
                  v
         Preference Resolver
                  |
                  v
     Effective Preference Snapshot
                  |
                  v
                Agent
```

The platform service should control:

-   which profiles an agent can read;
-   which profile an agent can update;
-   preference precedence;
-   conflict resolution;
-   provenance;
-   confidence where applicable;
-   session overrides;
-   external/UI preferences;
-   effective context generation.

------------------------------------------------------------------------

# 9. Memory Profiles vs. Memory Bank

  Requirement                              Capability to Evaluate
  ---------------------------------------- -----------------------------------
  Known structured preference              Memory Profile
  Predictable/low-latency profile access   Memory Profile
  Domain-owned preference                  Memory Profile
  Learned conversational information       Memory Bank
  Unstructured long-term information       Memory Bank
  Semantic retrieval                       Memory Bank
  Session-only preference                  Session context
  Browser/external profile preference      External Profile API
  Conflict resolution                      Preference Resolver
  Cross-domain context                     Shared Preference/Context Service

The intent is not to replace Memory Bank with profiles. The two serve
different purposes.

------------------------------------------------------------------------

# 10. Revisit the Per-Request Memory Retrieval Assumption

The previous model assumes one memory retrieval for every runtime
request.

For a ten-turn session:

``` text
Turn 1 -> Memory retrieval
Turn 2 -> Memory retrieval
...
Turn 10 -> Memory retrieval
```

The shared-memory design should test a more efficient approach:

``` text
Session Start
     |
Load Relevant Profiles
     |
Retrieve Applicable Semantic Memory
     |
Apply Priority / Conflict Rules
     |
Build Effective Preference Snapshot
     |
     +--> Turn 1
     +--> Turn 2
     +--> ...
     +--> Turn 10
```

The snapshot can be refreshed when the user changes a preference, a
relevant profile changes, significant new memory is created, or a
freshness threshold is reached.

This should reduce latency and unnecessary retrieval activity
independent of runtime choice.

------------------------------------------------------------------------

# 11. Online and Offline Development

The platform must support more than production execution.

## Online / Production-Like

``` text
Agent
  |
Agent Runtime / Cloud Run
  |
Shared Context Service
  |
  +-- Sessions
  +-- Memory Profiles
  +-- Memory Bank
  +-- Gemini
```

Used for integration, performance, pre-production, and production.

## Local Agent + Cloud Services

``` text
Developer Laptop
      |
     ADK
      |
      +--> Gemini
      +--> Development Memory Bank
      +--> Development Profile/Context Service
```

Used for rapid development with realistic managed dependencies.

## Offline / Mock

``` text
Developer Laptop
      |
     ADK
      |
Platform Interfaces
      |
      +--> In-Memory Sessions
      +--> Local/Test Preference Store
      +--> Mock Memory Provider
      +--> Mock External Profile API
```

Used for unit testing, CI, deterministic regression tests, and
development without mandatory cloud dependencies.

A provider/interface abstraction should prevent agent business logic
from being directly tied to Cloud SQL, Memory Bank, or the production
runtime.

------------------------------------------------------------------------

# 12. Evaluation Service --- Offline

The platform also needs a common evaluation capability.

Offline evaluation should run against controlled datasets before
deployment.

Candidate metrics include:

-   response quality;
-   groundedness;
-   task completion;
-   tool selection;
-   tool arguments;
-   A2A/multi-agent routing;
-   safety/policy compliance;
-   memory retrieval quality;
-   Memory Profile selection;
-   preference conflict resolution;
-   effective snapshot correctness;
-   latency;
-   token usage;
-   regression against previous versions.

Proposed flow:

``` text
Agent / Prompt / Model Change
            |
            v
     Evaluation Dataset
            |
            v
   Offline Eval Service
            |
    +-------+-------+
    |       |       |
 Quality  Memory   Tools
    |       |       |
 Safety  Routing Performance
    +-------+-------+
            |
            v
       Eval Results
            |
            v
    CI/CD Release Gate
```

Offline evaluations should support local execution where practical,
CI/CD execution, scheduled runs, and release/promotion gates.

------------------------------------------------------------------------

# 13. Evaluation Service --- Online

Online evaluation should measure production or production-like behavior
using controlled sampling.

Candidate signals:

-   task success;
-   user feedback;
-   response quality;
-   tool-call behavior;
-   memory relevance;
-   profile/preference-resolution accuracy;
-   latency;
-   token consumption;
-   safety signals;
-   agent routing;
-   drift/regression.

``` text
Production Agent Traffic
           |
           v
 Observability / Traces
           |
           v
    Controlled Sampling
           |
           v
    Online Eval Service
           |
   +-------+-------+
   |       |       |
Quality  Memory  Safety
Tools   Routing Performance
   +-------+-------+
           |
           v
 Metrics / Trends / Alerts
```

The online design must additionally address privacy, sensitive data,
evaluator cost, retention, access control, and audit requirements.

------------------------------------------------------------------------

# 14. Runtime for Evaluation Services

The agent runtime decision should not automatically determine where
evaluation services execute.

  -----------------------------------------------------------------------
  Workload                            Candidate
  ----------------------------------- -----------------------------------
  Production ADK agent                Agent Runtime vs. Cloud Run ---
                                      under evaluation

  Shared Preference/Context Service   Cloud Run

  Offline evaluation orchestration    Cloud Run / appropriate batch
                                      execution

  Online evaluation processing        Event-driven Cloud Run / managed
                                      processing

  Scheduled large evaluation jobs     Batch-oriented execution

  Evaluation results                  Appropriate managed analytics/data
                                      store
  -----------------------------------------------------------------------

The platform should select execution technology according to workload
characteristics.

------------------------------------------------------------------------

# 15. Three Architecture Options to Compare

## Option A --- Cloud Run-Centric

``` text
Agent -> Cloud Run
          |
          +-- Custom/Integrated Sessions
          +-- Cloud SQL/Profile Store
          +-- Custom/Integrated Semantic Memory
          +-- Shared Preference Service
```

**Strengths:** cost control, flexibility, portability, local
development.

**Trade-offs:** greater platform engineering and operations;
agent-native identity, governance, memory, lifecycle, and telemetry
require integration.

## Option B --- GEAP-Centric

``` text
Agent -> Agent Runtime
          |
          +-- GEAP Sessions
          +-- Memory Profiles
          +-- Memory Bank
          +-- Agent Identity
          +-- GEAP Governance/Observability
```

**Strengths:** managed agent lifecycle, native memory/session
integration, lower platform operations, stronger agent-native
governance.

**Trade-offs:** potentially higher runtime compute cost, greater GEAP
affinity, less runtime-level flexibility.

## Option C --- Hybrid

``` text
              Agent Runtime
                   |
                 Agent
                   |
                   v
      Shared Preference Service
              Cloud Run
                   |
        +----------+----------+
        |          |          |
     Profiles  Memory Bank  External
                           Preference API

Evaluation Services -> Cloud Run / Event / Batch
Offline Providers   -> Local/Test Implementations
```

**Strengths:** managed runtime where agent-specific capabilities provide
value while retaining Cloud Run for reusable platform services and
custom orchestration.

**Trade-offs:** two runtime patterns to operate and clear platform
contracts/standards are required.

**Current direction to validate:** Hybrid is a strong candidate, but the
POC and updated cost study should determine the final recommendation.

------------------------------------------------------------------------

# 16. Decision Criteria

  -----------------------------------------------------------------------
  Criterion                           Evaluation Question
  ----------------------------------- -----------------------------------
  Runtime cost                        What is the cost at representative
                                      volume and concurrency?

  Session/memory cost                 What is the cost under the new GEAP
                                      pricing model?

  Model/token cost                    How much of total cost is actually
                                      model consumption?

  Development effort                  How quickly can teams build and
                                      deploy?

  Platform engineering                What must the platform team build
                                      itself?

  Operations                          What is the long-term support
                                      burden?

  Scaling                             How do options behave at peak and
                                      sustained traffic?

  Availability                        How are enterprise HA/regional
                                      requirements met?

  Identity                            Can agents have governed workload
                                      identity?

  Governance                          How are authorization, audit, and
                                      policy handled?

  Observability                       Can model/tool/memory/agent
                                      behavior be diagnosed?

  Memory Profiles                     Do they satisfy structured
                                      preference requirements?

  Semantic memory                     Does Memory Bank satisfy
                                      dynamic-memory requirements?

  Cross-profile memory                Can authorized agents safely
                                      consume multiple profiles?

  Offline development                 Can developers work without full
                                      cloud deployment?

  Offline evaluation                  Can releases be regression-tested
                                      and gated?

  Online evaluation                   Can production quality and drift be
                                      measured safely?

  Portability                         How strongly does the design depend
                                      on a runtime?
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 17. Work to Complete

## Cost

-   [ ] Validate current Agent Runtime pricing with the Google Cloud
    pricing calculator.
-   [ ] Recalculate Cloud Run using realistic concurrency.
-   [ ] Measure active CPU utilization vs. five-second wall-clock
    latency.
-   [ ] Recalculate Sessions using the new pricing model.
-   [ ] Recalculate Memory Bank using the new pricing model.
-   [ ] Include Memory Bank/session storage.
-   [ ] Include memory-generation and embedding/model costs.
-   [ ] Include Gemini inference separately.
-   [ ] Model average, peak, and growth scenarios.
-   [ ] Compare infrastructure cost and TCO separately.

## Memory

-   [ ] Build Memory Profiles POC.
-   [ ] Validate domain-specific profiles.
-   [ ] Validate cross-profile reads.
-   [ ] Validate domain-specific write ownership.
-   [ ] Define structured-profile vs. semantic-memory rules.
-   [ ] Implement preference precedence/conflict rules.
-   [ ] Validate effective preference snapshot.
-   [ ] Compare per-turn retrieval vs. session-level context.
-   [ ] Measure memory/profile latency.
-   [ ] Validate sensitive-domain isolation.

## Runtime

-   [ ] Deploy the same ADK agent to Agent Runtime and Cloud Run.
-   [ ] Run identical load tests.
-   [ ] Compare concurrency/scaling.
-   [ ] Compare cold-start behavior.
-   [ ] Compare telemetry.
-   [ ] Compare deployment and developer effort.
-   [ ] Validate enterprise identity/networking requirements.

## Offline Development

-   [ ] Define cloud memory provider interface.
-   [ ] Define local/test memory provider.
-   [ ] Define local session provider.
-   [ ] Validate local ADK + cloud-memory mode.
-   [ ] Validate fully offline/mock mode.
-   [ ] Integrate offline mode with CI.

## Evaluation Services

-   [ ] Define common evaluation schema.
-   [ ] Create baseline evaluation datasets.
-   [ ] Prototype offline evaluation.
-   [ ] Integrate offline evaluation with CI/CD.
-   [ ] Define release thresholds/gates.
-   [ ] Prototype online evaluation.
-   [ ] Define production sampling.
-   [ ] Define memory-specific evaluation metrics.
-   [ ] Define tool/A2A metrics.
-   [ ] Define privacy and retention controls.
-   [ ] Estimate evaluator/model cost.

------------------------------------------------------------------------

# 18. Expected Outcome

The refreshed assessment should produce:

1.  An updated cost model replacing the early-2026 comparison.
2.  A Cloud Run vs. Agent Runtime decision matrix based on equivalent
    capabilities.
3.  A Memory Profiles + Memory Bank architecture for structured and
    semantic memory.
4.  A shared preference/context service design for multi-agent
    scenarios.
5.  Online, connected, and offline development patterns.
6.  Online and offline evaluation service architecture.
7.  Platform standards defining default runtime patterns and exception
    criteria.

------------------------------------------------------------------------

# Summary

The earlier analysis correctly represented the economics of the platform
under the assumptions and pricing available at that time. However, the
two largest managed-platform cost components in that analysis ---
**Sessions and Memory Bank** --- are changing materially.

The previous **\$776.60 vs. \$14,200** comparison should therefore
remain visible as historical context, but should not be treated as the
current platform conclusion.

The refreshed evaluation asks a broader question:

> **What combination of Agent Runtime, Cloud Run, Sessions, Memory
> Profiles, Memory Bank, shared platform services, and evaluation
> services provides the best enterprise balance of cost, developer
> experience, operational simplicity, governance, memory capability, and
> scalability?**

The original workload assumptions will initially be retained to make the
impact of the GEAP changes visible. Those assumptions will then be
validated through POCs, representative load testing, and current Google
Cloud pricing before establishing the final platform standard.
