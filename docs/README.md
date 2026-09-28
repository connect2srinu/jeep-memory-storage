# Documentation index

All documents below describe the implementation on `feature/dynamic-household-members` as of
2026-09-23. The analyses and decision records were re-checked against the code on that date; each one
says what is now implemented and what is still open.

## Guides

| Audience | Document |
|---|---|
| Anyone new to the platform | [Household Memory — End-to-End UI Guide](dynamic-household-test-guide.md) — organization, project, wizard, agent, and a full customer journey, all from the UI |
| Platform user creating a setup | [Guided Memory Setup](guided-memory-setup.md) · [Three Agent Memory Models — UI Test Guide](three-agent-models-test-guide.md) (private, hybrid, consumer only) |
| Domain owner | [Domain Onboarding](domain-onboarding.md) |
| Agent developer | [New Agent Onboarding](new-agent-onboarding.md) · [Memory Agent](../apps/memory-agent/README.md) · [Reference Agent](../apps/reference-agent/README.md) |
| Tester (API level) | [Memory Flow Test Guide](memory-flow-test-guide.md) — runtime API checks, the example script, and the load test |
| Platform administrator | [Admin API](admin-api.md) |
| Identity administrator | [Microsoft Entra Authentication](entra-authentication.md) |
| DevOps / SRE | [Deployment and Operations](deployment-operations.md) |

The Control Plane API serves interactive OpenAPI docs at `/docs` (Swagger UI) and `/redoc`.

## Architecture and design

- [Agent Memory Setup and Runtime Flows](agent-memory-setup.md) — components, read/write flows,
  scopes, capabilities, failure model
- [Agent Turn Flow](architecture/agent-flow.md) — how one message becomes an answer or a tool call
  inside ADK
- [Dynamic Household Members](dynamic-household-members-design.md) — household scopes, runtime member
  resolution, confirmation, consent, purpose, retention (design of record)
- [Dynamic Memory Topic Gating](dynamic-memory-topic-gating.md) — canonical vs dynamic memory,
  resolution policies, deletion
- [Vertex Memory Bank](vertex-memory-bank.md) — provisioning, reads, writes, and deletion against the
  provider

## Analyses and decision records

- [Platform Reference Architecture](GEAP_Platform_Reference_Architecture.md) — current vs target
  Control Panel architecture
- [Control Panel Roadmap](GEAP_Control_Panel_Roadmap.md) — product vision and phase status
- [Console UX Redesign](GEAP_Console_UX_Redesign.md) — data-model validation and the three console
  redesigns (now shipped)
- [Unified Memory Requirements — Proposed Remarks](unified-memory-requirements-remarks.md) — status
  and concerns for each functional and non-functional requirement, ready to paste into the page
- [Next Sprint — Governed Memory Stories](next-sprint-memory-stories.md) — privacy, attributes,
  extraction cost, edge cases, evals, confidence, and load-test stories, each marked verify / gap / design
- [ADR-0001: Managed Memory Bank vs Custom Unified Memory Layer](adr/ADR-0001-shared-memory-memory-bank-vs-unified-memory-layer.md)
  and its evidence:
  [architecture validation](current-memory-bank-architecture-validation.md),
  [assumption validation](memory-bank-assumption-validation.md),
  [capability matrix](memory-bank-vs-uml-capability-matrix.md),
  [cost analysis](memory-bank-vs-uml-cost-analysis.md)
- [Memory Layer Build vs Buy Gap Analysis](Memory_Layer_Build_vs_Buy_Gap_Analysis.md)
- [Memory Sensitivity Classification](memory-sensitivity-classification-gap-analysis.md) — legal
  matrix vs what the write gate enforces
- [DEART-56710 Vertex Memory Bank spike](DEART-56710-vertex-memory-bank-spike.md) and its
  [Jira summary](DEART-56710-jira-comment.md)

## Presentations

- [Governed Memory — Privacy & Legal Review](presentations/privacy-legal-review/privacy-controls-briefing.md)
  — top privacy risks, the controls in code, and a live demo run sheet
  (`scripts/privacy_controls_demo.py`)
- [Memory Bank: build vs buy vs hybrid](presentations/memory-build-vs-buy/memory-build-vs-buy-three-way.md)
- [Control Plane platform value](presentations/control-plane-platform-value/control-plane-platform-value-deck.md)

## Diagrams

The draw.io sources predate household scopes, runtime member resolution, consent, purpose, and
retention; they still show the single `organization_id + user_id` scope. Use them for the overall
component layout, and the Markdown documents above for current behavior.

- [Memory Flows](GEAP_Memory_Flows.drawio) — activation, preference write, session read,
  resource relationships, dynamic-memory topic gate
- [Target Architecture](geap-target-architecture.drawio) — Entra → Console → API → GEAP services
- [Platform Architecture](GEAP_Architecture.drawio)
- [Agent Memory Flows](agent-memory-flows.drawio) — runtime and onboarding view
- [Google Cloud Services Architecture](google-cloud-services-architecture.drawio) — deployable
  Google Cloud services

The Markdown files import directly into Confluence. Google Cloud pricing and service capabilities
change; use current official pricing and product documentation for funding or production decisions.
