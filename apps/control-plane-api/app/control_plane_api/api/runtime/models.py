from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class RuntimeScope(ApiModel):
    user_id: str = Field(alias="userId", min_length=1)
    organization_id: str | None = Field(default=None, alias="organizationId", min_length=1)
    app_name: str | None = Field(default=None, alias="appName", min_length=1)
    domain: str | None = Field(default=None, min_length=1)


class ResolvePreferencesRequest(ApiModel):
    scope: RuntimeScope
    session_id: str = Field(alias="sessionId", min_length=1)
    include_provenance: bool = Field(default=False, alias="includeProvenance")
    requested_agent_id: str | None = Field(default=None, alias="agentId")


class PreferenceValue(ApiModel):
    value: Any
    source: str
    owner_domain: str = Field(alias="ownerDomain")
    resolution_reason: str = Field(alias="resolutionReason")
    provenance: dict[str, Any] | None = None


class EffectivePreferenceSnapshotResponse(ApiModel):
    agent_id: str = Field(alias="agentId")
    scope: RuntimeScope
    session_id: str = Field(alias="sessionId")
    preferences: dict[str, PreferenceValue]
    snapshot_version: str = Field(alias="snapshotVersion")
    policy_version: str = Field(alias="policyVersion")
    schema_versions: dict[str, str] = Field(alias="schemaVersions")
    writable_preferences: tuple[str, ...] = Field(default=(), alias="writablePreferences")
    approved_topics: tuple[str, ...] = Field(default=(), alias="approvedTopics")
    generated_at: datetime = Field(alias="generatedAt")


class RawProfilesRequest(ApiModel):
    scope: RuntimeScope
    schema_ids: tuple[str, ...] = Field(alias="schemaIds", min_length=1)


class MemoryEventRequest(ApiModel):
    scope: RuntimeScope
    text: str = Field(min_length=1)
    candidates: tuple[PreferenceUpdate, ...] = ()


class PreferenceUpdate(ApiModel):
    schema_id: str | None = Field(default=None, alias="schemaId", min_length=1)
    attribute: str = Field(min_length=1)
    value: Any


class ExplicitPreferenceUpdate(ApiModel):
    scope: RuntimeScope
    schema_id: str | None = Field(default=None, alias="schemaId", min_length=1)
    value: Any


class DynamicMemoryWrite(ApiModel):
    scope: RuntimeScope
    topic: str = Field(min_length=1)
    value: Any
    confidence: float = Field(default=1.0, ge=0, le=1)


class RuntimeMutationResponse(ApiModel):
    status: str
    reference: str
    profile_version: int | None = Field(default=None, alias="profileVersion")


class ApiError(BaseModel):
    code: str
    message: str
    correlation_id: str = Field(alias="correlationId")
