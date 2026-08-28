# Documentation index

These documents describe the current implementation. Historical phase plans and the pre-refactor
architecture assessment have been removed because their commands and component boundaries no
longer represent the running system.

| Audience | Start here |
|---|---|
| New platform user | [Guided Memory Setup](guided-memory-setup.md) |
| Domain owner | [Domain Onboarding](domain-onboarding.md) |
| Agent developer | [Reference Agent](../apps/reference-agent/README.md) |
| Platform developer | [Agent Memory Setup](agent-memory-setup.md) |
| Platform administrator | [Admin API](admin-api.md) |
| Identity administrator | [Microsoft Entra Authentication](entra-authentication.md) |
| DevOps/SRE | [Deployment and Operations](deployment-operations.md) |
| Vertex integrator | [Vertex Memory Bank](vertex-memory-bank.md) |

The Control Plane API ships interactive OpenAPI docs (Swagger UI at `/docs`, ReDoc at `/redoc`).
See [Admin API](admin-api.md#interactive-api-documentation).

Architecture and analysis:

- [Platform Reference Architecture](GEAP_Platform_Reference_Architecture.md) — current-vs-target analysis
- [Control Panel UX Redesign](GEAP_Console_UX_Redesign.md) — data-model validation and console redesign
- [Control Panel Roadmap](GEAP_Control_Panel_Roadmap.md) — product vision and phased plan
- [Target Architecture](geap-target-architecture.drawio) — Entra → Console → API → GEAP services
- [Agent Memory Flows](agent-memory-flows.drawio) — runtime and onboarding view
- [Google Cloud Services Architecture](google-cloud-services-architecture.drawio) — deployable Google Cloud services

The Markdown guides are directly importable into Confluence. The former Confluence-specific copies,
historical governance gap analysis, planning-only cost assessment, duplicate architecture diagrams,
and standalone deployment placeholder sheet were removed. Their current material is consolidated in
the guides above.

Google Cloud pricing and service capabilities change. Use current official pricing and product
documentation for funding or production decisions rather than treating repository documentation as
a cost estimate.
