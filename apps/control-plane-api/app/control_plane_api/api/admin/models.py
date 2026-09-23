from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AdminModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True, extra="forbid")


# Declared use of memory (see domain.governance.PURPOSES).
Purpose = Literal["personalization", "analytics", "advertising"]


class OrganizationCreate(AdminModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=63)
    name: str = Field(min_length=1)
    description: str = ""
    owner_contact: str | None = Field(default=None, alias="ownerContact")


class ProjectCreate(AdminModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=63)
    organization_id: str = Field(alias="organizationId", min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    owner_team: str = Field(alias="ownerTeam", min_length=1)


class MembershipCreate(AdminModel):
    member_principal: str = Field(alias="memberPrincipal", min_length=3, max_length=320)
    display_name: str | None = Field(default=None, alias="displayName", max_length=255)
    role: Literal["OWNER", "ADMIN", "VIEWER"]


class BudgetThreshold(AdminModel):
    percent: float = Field(gt=0, le=100)
    basis: Literal["ACTUAL", "FORECAST"] = "ACTUAL"


class OrganizationSettingsUpdate(AdminModel):
    budget_amount: float | None = Field(default=None, alias="budgetAmount", gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    budget_period: Literal["MONTHLY", "QUARTERLY", "ANNUAL"] = Field(
        default="MONTHLY", alias="budgetPeriod"
    )
    budget_enabled: bool = Field(default=False, alias="budgetEnabled")
    thresholds: list[BudgetThreshold] = Field(default_factory=list)
    email_recipients: list[str] = Field(default_factory=list, alias="emailRecipients")
    monitoring_channel_ids: list[str] = Field(default_factory=list, alias="monitoringChannelIds")
    pubsub_topic: str | None = Field(default=None, alias="pubsubTopic")
    billing_account_id: str | None = Field(default=None, alias="billingAccountId")
    billing_project_ids: list[str] = Field(default_factory=list, alias="billingProjectIds")


class ProjectSettingsUpdate(AdminModel):
    health_refresh_seconds: int = Field(default=300, alias="healthRefreshSeconds", ge=30, le=86400)
    latency_warning_ms: float = Field(default=2000, alias="latencyWarningMs", gt=0)
    error_rate_warning: float = Field(default=0.05, alias="errorRateWarning", ge=0, le=1)
    notifications_enabled: bool = Field(default=True, alias="notificationsEnabled")
    notification_channel_ids: list[str] = Field(
        default_factory=list, alias="notificationChannelIds"
    )


class AgentRuntimeBindingUpdate(AdminModel):
    provider: Literal["GOOGLE_AGENT_RUNTIME", "CLOUD_RUN", "ADK_LOCAL"]
    gcp_project_id: str | None = Field(default=None, alias="gcpProjectId")
    location: str | None = None
    resource_name: str | None = Field(default=None, alias="resourceName")
    endpoint_url: str | None = Field(default=None, alias="endpointUrl")
    environment: str = "development"


class DomainCreate(AdminModel):
    id: str = Field(min_length=1, max_length=63)
    organization_id: str = Field(alias="organizationId", min_length=1)
    project_id: str = Field(alias="projectId", min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    owner_team: str = Field(alias="ownerTeam", min_length=1)
    owner_contact: str | None = Field(default=None, alias="ownerContact")
    contract_version: str = Field(default="1.0", alias="contractVersion")


class ScopeCreate(AdminModel):
    id: str = Field(min_length=1)
    scope_type: str = Field(alias="scopeType", min_length=1)
    scope_keys: list[str] = Field(alias="scopeKeys", min_length=1)
    description: str = ""
    owner_domain_id: str = Field(alias="ownerDomainId", min_length=1)


class SchemaMapping(AdminModel):
    attribute_id: str = Field(alias="attributeId", min_length=1)
    profile_field: str = Field(alias="profileField", min_length=1)


class SchemaCreate(AdminModel):
    id: str = Field(min_length=1)
    domain_id: str = Field(alias="domainId", min_length=1)
    display_name: str = Field(alias="displayName", min_length=1)
    description: str = ""
    owner_team: str = Field(alias="ownerTeam", min_length=1)
    version: str = Field(min_length=1)
    scope_definition_id: str = Field(alias="scopeDefinitionId", min_length=1)
    vertex_schema_definition: dict[str, Any] = Field(alias="vertexSchemaDefinition")
    generation_config: dict[str, Any] = Field(default_factory=dict, alias="generationConfig")
    mappings: list[SchemaMapping] = Field(min_length=1)
    # Schema-owner retention within the platform limit for the schema's sensitivity tier.
    retention_days: int | None = Field(default=None, alias="retentionDays", ge=1, le=3650)
    allowed_purposes: list[Purpose] = Field(
        default_factory=lambda: ["personalization"], alias="allowedPurposes", min_length=1
    )


class SchemaVersionChange(AdminModel):
    version: str = Field(min_length=1)
    scope_definition_id: str | None = Field(default=None, alias="scopeDefinitionId")
    vertex_schema_definition: dict[str, Any] | None = Field(
        default=None, alias="vertexSchemaDefinition"
    )
    generation_config: dict[str, Any] | None = Field(default=None, alias="generationConfig")
    mappings: list[SchemaMapping] = Field(min_length=1)


class PreferenceCreate(AdminModel):
    attribute_id: str = Field(alias="attributeId", min_length=1)
    display_name: str = Field(alias="displayName", min_length=1)
    description: str = Field(min_length=1)
    data_type: str = Field(alias="dataType", min_length=1)
    allowed_values: list[Any] = Field(default_factory=list, alias="allowedValues")
    sensitivity_classification: str = Field(alias="sensitivityClassification", min_length=1)
    canonical_owner_id: str = Field(alias="canonicalOwnerId", min_length=1)
    validation_rules: dict[str, Any] = Field(default_factory=dict, alias="validationRules")
    default_resolution_behavior: dict[str, Any] = Field(
        default_factory=dict, alias="defaultResolutionBehavior"
    )
    catalog_version: str = Field(default="1", alias="catalogVersion")


class AgentCreate(AdminModel):
    id: str = Field(min_length=1)
    display_name: str = Field(alias="displayName", min_length=1)
    organization_id: str = Field(alias="organizationId", min_length=1)
    project_id: str = Field(alias="projectId", min_length=1)
    domain_id: str = Field(alias="domainId", min_length=1)
    runtime_type: str = Field(alias="runtimeType", min_length=1)
    identity_type: str = Field(alias="identityType", min_length=1)
    principal: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    # Declared use of the memory it reads; checked against each schema's allowed purposes.
    purpose: Purpose = "personalization"


class RetentionSweepRequest(AdminModel):
    dry_run: bool = Field(default=True, alias="dryRun")
    # Preview what would expire as of a future date (dry run only).
    as_of: datetime | None = Field(default=None, alias="asOf")


class ResolutionSchemaPriority(AdminModel):
    schema_id: str = Field(alias="schemaId", min_length=1)
    priority: int = Field(ge=0)


class ResolutionAttributeOverride(AdminModel):
    attribute_id: str = Field(alias="attributeId", min_length=1)
    schema_precedence: list[str] = Field(alias="schemaPrecedence", min_length=1)
    rules: dict[str, Any] = Field(default_factory=dict)


class ResolutionPolicyCreate(AdminModel):
    id: str = Field(min_length=1)
    agent_id: str | None = Field(default=None, alias="agentId")
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    default_rules: dict[str, Any] = Field(default_factory=dict, alias="defaultRules")
    schema_priorities: list[ResolutionSchemaPriority] = Field(
        default_factory=list, alias="schemaPriorities"
    )
    attribute_overrides: list[ResolutionAttributeOverride] = Field(
        default_factory=list, alias="attributeOverrides"
    )


class DynamicMemoryPolicyCreate(AdminModel):
    id: str = Field(min_length=1)
    level: str = Field(min_length=1)
    domain_id: str | None = Field(default=None, alias="domainId")
    schema_id: str | None = Field(default=None, alias="schemaId")
    enabled: bool = True
    confidence_threshold: float = Field(default=0.7, alias="confidenceThreshold", ge=0, le=1)
    memory_topics: list[str] = Field(default_factory=list, alias="memoryTopics")
    topic_definitions: dict[str, str] = Field(default_factory=dict, alias="topicDefinitions")
    retention_policy: dict[str, Any] = Field(default_factory=dict, alias="retentionPolicy")
    confirmation_required: bool = Field(default=True, alias="confirmationRequired")
    allowed_dynamic_categories: list[str] = Field(
        default_factory=list, alias="allowedDynamicCategories"
    )
    version: str = "1"


class ResourceUpdate(AdminModel):
    status: str | None = None
    changes: dict[str, Any] = Field(default_factory=dict)


class AccessRequestCreate(AdminModel):
    requesting_agent_id: str = Field(alias="requestingAgentId", min_length=1)
    requesting_team: str = Field(alias="requestingTeam", min_length=1)
    target_schema_id: str = Field(alias="targetSchemaId", min_length=1)
    requested_permission: str = Field(alias="requestedPermission", min_length=1)
    business_reason: str = Field(alias="businessReason", min_length=1)
    expiration: datetime | None = None


class AccessDecision(AdminModel):
    expiration: datetime | None = None
    reason: str | None = None


class AdminRecord(AdminModel):
    data: dict[str, Any]


class AdminRecordList(AdminModel):
    items: list[dict[str, Any]]


class HouseholdMemberAdminWrite(AdminModel):
    display_name: str | None = Field(default=None, alias="displayName")
    relationship: str = Field(default="member", min_length=1)
    has_login: bool = Field(default=False, alias="hasLogin")
    is_guardian: bool = Field(default=False, alias="isGuardian")
    # Defaults from the relationship (a child is a minor); set it to correct, e.g. an adult son.
    minor: bool | None = None


class GuidedUseCase(AdminModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    owning_team: str = Field(alias="owningTeam", min_length=1)
    organization_id: str = Field(alias="organizationId", min_length=1)
    project_id: str = Field(alias="projectId", min_length=1)
    domain: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    environment: str = Field(min_length=1)


class GuidedCustomPreference(AdminModel):
    attribute_id: str = Field(alias="attributeId", min_length=3)
    display_name: str = Field(alias="displayName", min_length=1)
    description: str = Field(min_length=1)
    data_type: Literal["string", "boolean", "integer", "number"] = Field(alias="dataType")
    allowed_values: list[Any] = Field(default_factory=list, alias="allowedValues")
    sensitivity: Literal["normal", "sensitive", "restricted"] = "normal"
    # For the HOUSEHOLD_MEMBERS scope, which tier this preference belongs to: shared by the whole
    # household ("household") or specific to one member such as a child ("member").
    level: Literal["household", "member"] = "household"
    # Health data (e.g. allergies): stricter matching, a confirmation turn and a consent record.
    # Implies at least "sensitive".
    health: bool = Field(default=False, alias="isHealth")


class GuidedScope(AdminModel):
    type: Literal["USER", "HOUSEHOLD", "USER_STORE", "HOUSEHOLD_MEMBERS", "CUSTOM"]
    custom_keys: list[str] = Field(default_factory=list, alias="customKeys")


class GuidedMemoryBehavior(AdminModel):
    canonical: bool = True
    dynamic_enabled: bool = Field(default=True, alias="dynamicEnabled")
    confidence_threshold: float = Field(default=0.85, alias="confidenceThreshold", ge=0, le=1)
    confirmation_required: bool = Field(default=True, alias="confirmationRequired")
    retention_days: int = Field(default=365, alias="retentionDays", ge=1, le=3650)
    # Retention for canonical preference values (the generated schemas); None keeps them until
    # deleted. Must be within the platform limit for each schema's sensitivity tier.
    profile_retention_days: int | None = Field(
        default=None, alias="profileRetentionDays", ge=1, le=3650
    )
    memory_topics: list[str] = Field(default_factory=list, alias="memoryTopics")
    topic_definitions: dict[str, str] = Field(default_factory=dict, alias="topicDefinitions")


class GuidedAgent(AdminModel):
    id: str = Field(min_length=1)
    display_name: str = Field(alias="displayName", min_length=1)
    existing: bool = False
    runtime_type: str = Field(default="ADK_LOCAL", alias="runtimeType", min_length=1)
    identity_type: str = Field(default="LOCAL_POC", alias="identityType", min_length=1)
    principal: str | None = None
    owned_schema_permission: Literal["READ", "WRITE", "READ_WRITE"] = Field(
        default="READ_WRITE", alias="ownedSchemaPermission"
    )


class GuidedSharedSchema(AdminModel):
    schema_id: str = Field(alias="schemaId", min_length=1)
    permission: Literal["READ", "WRITE", "READ_WRITE"] = "READ"


class GuidedResolution(AdminModel):
    schema_precedence: list[str] = Field(default_factory=list, alias="schemaPrecedence")
    attribute_overrides: list[ResolutionAttributeOverride] = Field(
        default_factory=list, alias="attributeOverrides"
    )


class GuidedMemorySetupRequest(AdminModel):
    use_case: GuidedUseCase = Field(alias="useCase")
    selected_preferences: list[str] = Field(default_factory=list, alias="selectedPreferences")
    custom_preferences: list[GuidedCustomPreference] = Field(
        default_factory=list, alias="customPreferences"
    )
    scope: GuidedScope
    memory: GuidedMemoryBehavior
    agent: GuidedAgent
    shared_schemas: list[GuidedSharedSchema] = Field(default_factory=list, alias="sharedSchemas")
    resolution: GuidedResolution | None = None
    # Optional per-attribute tier override for HOUSEHOLD_MEMBERS setups, keyed by attribute id
    # ("household" or "member"). Catalog preferences default to "household" when absent; custom
    # preferences fall back to their own `level`.
    preference_levels: dict[str, Literal["household", "member"]] = Field(
        default_factory=dict, alias="preferenceLevels"
    )


class GuidedMemorySetupPreview(AdminModel):
    summary: dict[str, Any]
    generated_contract: dict[str, Any] = Field(alias="generatedContract")
    generated_yaml: str = Field(alias="generatedYaml")
    warnings: list[str] = Field(default_factory=list)


class GuidedMemorySetupActivation(GuidedMemorySetupPreview):
    status: str
    resources: dict[str, Any]
    pending_approvals: list[str] = Field(default_factory=list, alias="pendingApprovals")
    provisioning: dict[str, Any]
