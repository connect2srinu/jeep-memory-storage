from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared_memory.models import PreferenceScope, PreferenceSource
from app.shared_memory.policies import ResolutionStrategy


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ContractOwner(ContractModel):
    team: str
    email: str | None = None


class ContractMetadata(ContractModel):
    name: str | None = None
    domain: str | None = None
    display_name: str | None = None
    version: str = "1.0"
    owner: ContractOwner | None = None


class ScopeConfiguration(ContractModel):
    profile_scope_keys: list[str] = Field(
        default_factory=lambda: ["user_id", "app_name", "domain"]
    )

    @field_validator("profile_scope_keys")
    @classmethod
    def validate_scope_keys(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)):
            raise ValueError("profileScopeKeys must be non-empty and unique")
        if "user_id" not in value:
            raise ValueError("profileScopeKeys must include user_id")
        return value


class DomainPermissions(ContractModel):
    read: list[str]
    write: list[str]


class DynamicMemoryPolicy(ContractModel):
    enabled: bool = True
    key_pattern: str | None = None
    minimum_confidence: float = Field(default=0.7, ge=0, le=1)
    require_explicit_statement: bool = True

    @field_validator("key_pattern")
    @classmethod
    def validate_pattern(cls, value: str | None) -> str | None:
        if value:
            re.compile(value)
        return value


class DomainDefaults(ContractModel):
    retention_days: int | None = Field(default=None, gt=0)
    inferred_preference_ttl_days: int | None = Field(default=None, gt=0)


class DomainSpec(ContractModel):
    isolation: Literal["standard", "strict"] = "standard"
    scopes: ScopeConfiguration = Field(default_factory=ScopeConfiguration)
    permissions: DomainPermissions
    dynamic_memory: DynamicMemoryPolicy = Field(default_factory=DynamicMemoryPolicy)
    defaults: DomainDefaults = Field(default_factory=DomainDefaults)


class DomainContract(ContractModel):
    api_version: Literal["memory.platform/v1alpha1"] = "memory.platform/v1alpha1"
    kind: Literal["MemoryDomain"]
    metadata: ContractMetadata
    spec: DomainSpec

    @model_validator(mode="after")
    def require_name(self) -> DomainContract:
        if not self.metadata.name:
            raise ValueError("MemoryDomain metadata.name is required")
        return self


class PreferenceLifecycle(ContractModel):
    session_ttl_seconds: int | None = Field(default=None, gt=0)
    long_term_retention_days: int | None = Field(default=None, gt=0)


class PreferenceConfirmation(ContractModel):
    required_for_long_term: bool = False


class PreferenceDefinition(ContractModel):
    key: str
    type: Literal["string", "boolean", "integer", "number"]
    description: str
    owner_domain: str
    canonical: bool = True
    sensitivity: Literal["normal", "sensitive", "restricted"] = "normal"
    scopes: list[PreferenceScope]
    schema_version: str = "1"
    allowed_readers: list[str]
    allowed_writers: list[str]
    resolution_policy: str
    profile: str | None = None
    allowed_values: list[Any] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    lifecycle: PreferenceLifecycle = Field(default_factory=PreferenceLifecycle)
    confirmation: PreferenceConfirmation = Field(default_factory=PreferenceConfirmation)

    @model_validator(mode="after")
    def validate_definition(self) -> PreferenceDefinition:
        if not self.key.startswith(f"{self.owner_domain}."):
            raise ValueError("preference key must start with ownerDomain followed by a dot")
        if not self.scopes:
            raise ValueError("preference scopes cannot be empty")
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError("preference scopes must be unique")
        return self


class PreferenceCatalogContract(ContractModel):
    api_version: Literal["memory.platform/v1alpha1"] = "memory.platform/v1alpha1"
    kind: Literal["PreferenceCatalog"]
    metadata: ContractMetadata
    preferences: list[PreferenceDefinition]

    @model_validator(mode="after")
    def require_domain(self) -> PreferenceCatalogContract:
        if not self.metadata.domain:
            raise ValueError("PreferenceCatalog metadata.domain is required")
        return self


class ResolutionDefaults(ContractModel):
    source_priority: list[PreferenceSource]
    domain_priority: list[str] = Field(default_factory=list)
    strategies: list[ResolutionStrategy]
    minimum_confidence: float = Field(default=0.7, ge=0, le=1)


class ResolutionPolicyDefinition(ContractModel):
    id: str
    applies_to: list[str]
    source_priority: list[PreferenceSource] | None = None
    domain_priority: list[str] | None = None
    strategies: list[ResolutionStrategy] | None = None
    minimum_confidence: float | None = Field(default=None, ge=0, le=1)


class ResolutionPoliciesContract(ContractModel):
    api_version: Literal["memory.platform/v1alpha1"] = "memory.platform/v1alpha1"
    kind: Literal["PreferenceResolutionPolicies"]
    metadata: ContractMetadata
    defaults: ResolutionDefaults | None = None
    policies: list[ResolutionPolicyDefinition] = Field(default_factory=list)


class MemoryProfileField(ContractModel):
    preference: str
    profile_field: str


class MemoryProfileGeneration(ContractModel):
    enabled: bool = True
    sources: list[
        Literal["CONFIRMED_PREFERENCE_CANDIDATE", "SESSION_EVENTS", "EXPLICIT_PROFILE_SYNC"]
    ] = Field(default_factory=lambda: ["CONFIRMED_PREFERENCE_CANDIDATE"])
    inferred_fields_allowed: bool = False
    require_user_confirmation: list[str] = Field(default_factory=list)


class MemoryProfileDefinition(ContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    memory_type: Literal["STRUCTURED_PROFILE"] = "STRUCTURED_PROFILE"
    owner_domain: str
    scope_keys: list[str]
    fields: list[MemoryProfileField]
    generation: MemoryProfileGeneration = Field(default_factory=MemoryProfileGeneration)

    @model_validator(mode="after")
    def validate_profile(self) -> MemoryProfileDefinition:
        if not self.scope_keys or len(self.scope_keys) != len(set(self.scope_keys)):
            raise ValueError("profile scopeKeys must be non-empty and unique")
        names = [item.profile_field for item in self.fields]
        if not names or len(names) != len(set(names)):
            raise ValueError("profile fields must be non-empty and have unique profileField values")
        return self


class MemoryProfilesContract(ContractModel):
    api_version: Literal["memory.platform/v1alpha1"] = "memory.platform/v1alpha1"
    kind: Literal["MemoryProfiles"]
    metadata: ContractMetadata
    profiles: list[MemoryProfileDefinition] = Field(default_factory=list)


class ConsumerCapabilities(ContractModel):
    resolve_context: bool = False
    submit_candidates: bool = False
    inspect_provenance: bool = False
    administer_memory: bool = False


class ConsumerDefinition(ContractModel):
    agent_id: str
    consumer_domain: str
    service_account: str | None = None
    required_preferences: list[str] = Field(default_factory=list)
    capabilities: ConsumerCapabilities


class MemoryConsumersContract(ContractModel):
    api_version: Literal["memory.platform/v1alpha1"] = "memory.platform/v1alpha1"
    kind: Literal["MemoryConsumers"]
    metadata: ContractMetadata
    consumers: list[ConsumerDefinition]


ContractDocument = (
    DomainContract
    | PreferenceCatalogContract
    | ResolutionPoliciesContract
    | MemoryProfilesContract
    | MemoryConsumersContract
)


CONTRACT_MODELS: dict[str, type[ContractModel]] = {
    "MemoryDomain": DomainContract,
    "PreferenceCatalog": PreferenceCatalogContract,
    "PreferenceResolutionPolicies": ResolutionPoliciesContract,
    "MemoryProfiles": MemoryProfilesContract,
    "MemoryConsumers": MemoryConsumersContract,
}
