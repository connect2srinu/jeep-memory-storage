import type { AdminRecord } from "../types";

export const templates: Record<string, AdminRecord> = {
  organizations: {
    id: "retail",
    name: "Retail",
    description: "Retail line of business",
    ownerContact: "retail-platform@example.com",
  },
  projects: {
    id: "rewards-experience",
    organizationId: "retail",
    name: "Rewards Experience",
    description: "Rewards personalization agents and domains",
    ownerTeam: "rewards-team",
  },
  domains: {
    id: "rewards",
    organizationId: "retail",
    projectId: "rewards-experience",
    name: "Rewards",
    description: "",
    ownerTeam: "rewards-team",
  },
  scopes: {
    id: "rewards:profile-scope",
    scopeType: "DOMAIN_PROFILE",
    scopeKeys: ["organization_id", "user_id"],
    ownerDomainId: "rewards",
  },
  "preference-catalog": {
    attributeId: "rewards.preferred_reward",
    displayName: "Preferred Reward",
    description: "Preferred reward",
    dataType: "string",
    sensitivityClassification: "normal",
    canonicalOwnerId: "rewards",
  },
  schemas: {
    id: "rewards-preferences-v1",
    domainId: "rewards",
    displayName: "Rewards Preferences",
    ownerTeam: "rewards-team",
    version: "1",
    scopeDefinitionId: "rewards:profile-scope",
    vertexSchemaDefinition: {
      type: "object",
      properties: { preferred_reward: { type: "string" } },
    },
    generationConfig: {},
    mappings: [
      { attributeId: "rewards.preferred_reward", profileField: "preferred_reward" },
    ],
    retentionDays: 365,
    allowedPurposes: ["personalization"],
  },
  agents: {
    id: "rewards-agent",
    displayName: "Rewards Agent",
    organizationId: "retail",
    projectId: "rewards-experience",
    domainId: "rewards",
    runtimeType: "ADK_CLOUD_RUN",
    identityType: "GOOGLE_SERVICE_ACCOUNT",
    capabilities: { resolve_context: true, submit_candidates: true },
    purpose: "personalization",
  },
  "access-requests": {
    requestingAgentId: "rewards-agent",
    requestingTeam: "rewards-team",
    targetSchemaId: "customer-preferences-v1",
    requestedPermission: "READ",
    businessReason: "Customer-aware rewards experience",
  },
  "resolution-policies": {
    id: "rewards-policy-v1",
    agentId: "rewards-agent",
    name: "Rewards policy",
    version: "1",
    defaultRules: { strategy: "DOMAIN_AUTHORITY" },
    schemaPriorities: [
      { schemaId: "rewards-preferences-v1", priority: 0 },
      { schemaId: "customer-preferences-v1", priority: 1 },
    ],
    attributeOverrides: [],
  },
  "dynamic-memory-policies": {
    id: "rewards-dynamic-v1",
    level: "DOMAIN",
    domainId: "rewards",
    confidenceThreshold: 0.8,
  },
};

