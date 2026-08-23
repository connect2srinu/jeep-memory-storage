from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AdminModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True, extra="forbid")


class DomainCreate(AdminModel):
    id: str = Field(min_length=1, max_length=63)
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
    domain_id: str = Field(alias="domainId", min_length=1)
    runtime_type: str = Field(alias="runtimeType", min_length=1)
    identity_type: str = Field(alias="identityType", min_length=1)
    principal: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)


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
