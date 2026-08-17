# Gemini Enterprise Agent Platform: Runtime, Memory, and Evaluation Service Assessment

## Purpose

This page summarizes the evaluation currently being performed for the
Gemini Enterprise Agent Platform (GEAP). The intent is to give platform
leadership, product management, and architecture stakeholders a clear
view of the decisions being assessed before standardizing the platform
implementation.

The assessment is focused on three related areas:

1.  **Agent Runtime vs. Cloud Run** for agent execution, including an
    updated cost comparison.
2.  **Memory Bank and Memory Profiles** for shared and persistent agent
    memory.
3.  **Evaluation services** for both online and offline evaluation
    scenarios.

This is an **evaluation-in-progress**, not a final platform decision.
The objective is to validate cost, capabilities, operational impact,
developer experience, and enterprise requirements before establishing
platform standards.

------------------------------------------------------------------------

## 1. Agent Runtime vs. Cloud Run

### Background

An earlier cost assessment compared hosting agents on Cloud Run with
using the managed Vertex AI agent runtime. Based on the assumptions and
pricing available at the beginning of 2026, Cloud Run appeared
significantly less expensive.

That analysis needs to be revisited because the Gemini Enterprise Agent
Platform has evolved substantially, including changes to the runtime,
Sessions, Memory Bank, Memory Profiles, agent identity, governance, and
pricing models.

The updated evaluation should therefore consider **total platform value
and total cost of ownership**, rather than comparing compute cost alone.

### Areas Being Evaluated

  --------------------------------------------------------------------------------------
  Evaluation Area   Cloud Run                Agent Runtime     What We Need to Determine
  ----------------- ------------------------ ----------------- -------------------------
  Runtime compute   Generally strong cost    Managed           Updated cost at expected
  cost              optimization and         agent-specific    production volume
                    concurrency controls     runtime pricing   

  Scaling           Highly configurable      Managed for agent Behavior under peak and
                                             workloads         sustained agent traffic

  Development       Requires                 More agent-native Developer productivity
  effort            application/runtime                        and standardization
                    integration                                

  Operational       Platform team owns more  More managed      Ongoing support and
  effort            runtime configuration                      maintenance effort

  Sessions          Requires integration     Native GEAP       Cost and operational
                    with a session           integration       value
                    implementation/service                     

  Memory Bank       Can access through       Native            Whether runtime choice
                    APIs/SDKs                integration       materially affects memory
                                                               architecture

  Agent identity    Requires additional      Platform-native   Enterprise
  and governance    integration              capabilities      security/governance
                                                               benefit

  Observability     Cloud-native application Agent-aware       Required operational
                    observability            platform          visibility
                                             integration       

  Runtime           Very high                More opinionated  Need for custom
  flexibility                                toward agent      frameworks/dependencies
                                             workloads         

  Local development Strong                   Production        Required local
                                             runtime is        development pattern
                                             managed           

  Portability       Higher                   Greater GEAP      Acceptable platform
                                             affinity          dependency
  --------------------------------------------------------------------------------------

### Cost Assessment

The previous comparison should be treated as a **historical baseline**,
not as the current decision model.

The revised analysis will:

-   Recalculate Cloud Run and Agent Runtime using current GEAP pricing.
-   Revisit the assumptions around request duration and CPU utilization.
-   Account for concurrency rather than assuming every request consumes
    a dedicated CPU for its entire end-to-end latency.
-   Recalculate Sessions and Memory Bank using the current pricing
    model.
-   Separate model/token costs from runtime infrastructure costs.
-   Include supporting platform services required by each option.
-   Consider engineering and operational effort in addition to
    infrastructure spend.
-   Model realistic production traffic, peak traffic, and growth
    scenarios.

### Target Outcome

The expected outcome is not necessarily that one runtime must be used
for every workload.

A likely platform pattern to validate is:

-   **Agent Runtime** as the preferred runtime for GEAP-native agent
    workloads where managed agent lifecycle, identity, sessions, memory,
    governance, and observability provide material value.
-   **Cloud Run** as a supported runtime for workloads requiring greater
    runtime flexibility, conventional services, or specific cost/scaling
    characteristics.
-   Establish clear decision criteria so development teams do not need
    to make this choice independently for every agent.

------------------------------------------------------------------------

## 2. Memory Bank and Memory Profiles

### Objective

The memory evaluation is focused on supporting agents that need both
agent-specific memory and access to shared user/domain context.

Example domains may include:

-   Customer
-   Grocery
-   Store
-   Delivery
-   Other line-of-business-specific profiles

An agent may own and update its domain-specific preferences while also
consuming authorized preferences from other profiles.

### Proposed Memory Pattern

The platform is evaluating a layered model:

**Structured preferences → Memory Profiles**

Use profiles for known, structured attributes that should be retrieved
predictably and efficiently.

Examples:

-   preferred store
-   substitution preference
-   delivery preference
-   brand preference
-   product preference

**Dynamic/semantic memory → Memory Bank**

Use Memory Bank where the information is learned from conversations or
cannot be represented effectively as a predefined structured preference.

**Shared Preference/Context Service**

A platform service would provide a consistent abstraction across the
different memory sources. Its responsibilities may include:

-   retrieving relevant profiles;
-   retrieving applicable long-term memories;
-   incorporating session-specific preferences;
-   incorporating preferences supplied through external profile APIs;
-   applying domain-specific precedence rules;
-   resolving conflicting preferences;
-   preserving source/provenance information;
-   producing an effective preference snapshot for the requesting agent.

### Key Questions Being Evaluated

  -----------------------------------------------------------------------
  Question                            Why It Matters
  ----------------------------------- -----------------------------------
  How many Memory Profiles should be  Determines domain ownership and
  used?                               isolation model

  How should an agent read across     Required for shared-memory
  profiles?                           scenarios

  Which agent/profile can update each Prevents unintended cross-domain
  preference?                         updates

  How are conflicts resolved?         Required when multiple domains
                                      contain related preferences

  Which attributes belong in profiles Impacts latency, predictability,
  vs. semantic memory?                and cost

  Should memory be retrieved per turn Major latency and efficiency
  or per session?                     consideration

  How are dynamic preferences         Prevents the schema from becoming
  represented?                        too restrictive

  What is the isolation model for     Required for enterprise security
  sensitive domains?                  and governance

  How is provenance retained?         Required for explainability and
                                      preference resolution
  -----------------------------------------------------------------------

### Runtime Independence

The memory architecture should not unnecessarily depend on whether an
agent executes on Agent Runtime or Cloud Run.

The preferred direction is to expose memory through a common platform
contract so that an agent can request an **effective context/preference
snapshot** without understanding the underlying storage implementation.

This also supports future runtime changes without redesigning the memory
model.

------------------------------------------------------------------------

## 3. Online and Offline Development Model

A key platform requirement is enabling developers to work efficiently
without requiring every development activity to execute against
production-like managed services.

The evaluation will therefore define multiple execution modes.

### Online / Managed Mode

Used for integration, performance, pre-production, and production
testing.

Potential services include:

-   Agent Runtime or Cloud Run
-   Gemini models on Vertex AI
-   GEAP Sessions
-   Memory Bank
-   Memory Profiles
-   Shared Preference/Context Service
-   Enterprise identity and governance
-   Centralized observability

### Local / Connected Mode

The agent runs locally while connecting to selected Google Cloud
services.

Example uses:

-   local ADK development;
-   testing against a development Memory Bank;
-   testing Gemini model behavior;
-   validating integration with the shared preference service.

This provides higher-fidelity testing without requiring deployment for
every code change.

### Offline / Mock Mode

The agent and supporting dependencies run locally or use test doubles.

Potential substitutes include:

-   in-memory session implementation;
-   local database or test fixture for preferences;
-   mock profile service;
-   mock Memory Bank provider;
-   recorded/model-stub responses where appropriate.

The goal is to enable fast development, deterministic automated tests,
and CI validation without unnecessary cloud dependencies.

### Design Principle

Agents should consume platform interfaces rather than directly coupling
business logic to a specific persistence implementation.

For example:

`Agent → Shared Context Interface → Cloud Provider / Local Provider / Test Provider`

This abstraction is important for developer productivity and
testability.

------------------------------------------------------------------------

## 4. Evaluation Services

The platform is also evaluating a common evaluation capability that can
support agents throughout their lifecycle.

The evaluation framework should support both **offline evaluations** and
**online evaluations**.

### Offline Evaluations

Offline evaluations are primarily intended for development, regression
testing, release validation, and model/prompt comparison.

Potential capabilities include:

-   curated evaluation datasets;
-   golden/reference responses where appropriate;
-   tool-selection accuracy;
-   task completion;
-   response quality;
-   groundedness;
-   safety and policy checks;
-   memory retrieval quality;
-   preference resolution correctness;
-   multi-agent/A2A workflow evaluation;
-   latency and token usage;
-   comparison across agent, prompt, model, and configuration versions.

Offline evaluation should be integrated with CI/CD so that material
regressions can be identified before promotion.

### Online Evaluations

Online evaluations are intended to assess production or production-like
agent behavior using actual interaction telemetry, subject to security
and privacy requirements.

Potential capabilities include:

-   sampled production interactions;
-   quality scoring;
-   task success indicators;
-   tool-call behavior;
-   memory retrieval effectiveness;
-   latency and failure rates;
-   policy/guardrail signals;
-   user feedback;
-   drift or regression detection.

Online evaluation should complement operational monitoring rather than
replace it.

### Online vs. Offline Evaluation

  ------------------------------------------------------------------------
  Area                    Offline Evaluation       Online Evaluation
  ----------------------- ------------------------ -----------------------
  Primary purpose         Pre-release quality and  Production quality
                          regression testing       monitoring

  Data                    Curated/synthetic/test   Sampled real
                          datasets                 interactions

  Execution               CI/CD, scheduled or      Continuous or scheduled
                          on-demand                sampling

  Reproducibility         High                     Lower due to real-world
                                                   variability

  Release gating          Yes                      Typically informs
                                                   rollback/improvement
                                                   decisions

  Privacy considerations  Controlled datasets      Higher; requires strong
                                                   governance

  Cost predictability     Easier to control        Depends on sampling and
                                                   evaluator usage
  ------------------------------------------------------------------------

------------------------------------------------------------------------

## 5. Platform-Level Decision Framework

Rather than evaluating each component independently, the final
recommendation should consider the complete platform experience.

The major decision dimensions are:

  -----------------------------------------------------------------------
  Dimension                           Key Consideration
  ----------------------------------- -----------------------------------
  Cost                                Infrastructure cost plus
                                      managed-service consumption

  Total Cost of Ownership             Engineering, maintenance, support,
                                      and operational overhead

  Developer Experience                Time required to build, test,
                                      deploy, and troubleshoot an agent

  Enterprise Governance               Identity, authorization,
                                      auditability, isolation, and policy
                                      enforcement

  Memory                              Structured profiles, semantic
                                      memory, shared context, and
                                      conflict resolution

  Evaluation                          Consistent online/offline quality
                                      measurement

  Observability                       Agent, model, tool, memory, and
                                      infrastructure visibility

  Scalability                         Production traffic, peak behavior,
                                      and future growth

  Availability/Resiliency             Enterprise availability and
                                      regional requirements

  Local Development                   Ability to develop and test without
                                      full managed deployment

  Portability                         Ability to change runtime or
                                      implementation without redesigning
                                      agents

  Platform Standardization            Ability to provide reusable
                                      patterns across lines of business
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 6. Work in Progress / Next Steps

The following activities are planned as part of the assessment:

-   [ ] Recalculate Agent Runtime cost using current GEAP pricing.
-   [ ] Recalculate Cloud Run cost using equivalent workload and
    concurrency assumptions.
-   [ ] Include Sessions and Memory Bank using the current pricing
    model.
-   [ ] Compare infrastructure cost separately from total cost of
    ownership.
-   [ ] Validate realistic runtime CPU/memory utilization using a
    representative agent workload.
-   [ ] Prototype Memory Profiles for structured user/domain
    preferences.
-   [ ] Validate cross-profile read patterns and domain-specific write
    ownership.
-   [ ] Prototype the Shared Preference/Context Service and effective
    preference snapshot.
-   [ ] Validate session-level caching/reuse to avoid unnecessary memory
    retrieval on every turn.
-   [ ] Define the local, connected, and offline development patterns.
-   [ ] Define a common abstraction for cloud and local memory
    providers.
-   [ ] Prototype offline evaluation for regression and release
    validation.
-   [ ] Prototype online evaluation using controlled production-like
    telemetry.
-   [ ] Define common evaluation metrics for model, tool, memory, and
    agent behavior.
-   [ ] Assess security, privacy, governance, and data-isolation
    requirements.
-   [ ] Produce a final decision matrix and recommended platform
    standards.

------------------------------------------------------------------------

## 7. Expected Deliverables

At the end of the assessment, the platform team should have:

1.  An updated **Agent Runtime vs. Cloud Run cost and capability
    comparison**.
2.  A recommended **runtime decision framework** for platform users.
3.  A validated **shared-memory architecture** using Memory Profiles,
    Memory Bank, and the Shared Preference/Context Service.
4.  A defined **online, connected, and offline development model**.
5.  A common **online and offline evaluation architecture**.
6.  A documented set of **platform standards, supported patterns, and
    exception criteria**.

------------------------------------------------------------------------

## Current Direction

The current assessment is intentionally avoiding a single technology
decision based only on compute price.

The goal is to determine the combination of GEAP managed capabilities
and Google Cloud services that provides the best balance of **cost,
developer productivity, operational simplicity, governance, memory
capabilities, evaluation quality, and enterprise scalability**.

The final recommendation will be based on validated workload
measurements and proof-of-concept results rather than the historical
cost comparison alone.
