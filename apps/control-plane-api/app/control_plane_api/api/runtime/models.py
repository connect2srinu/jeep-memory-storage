from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class RuntimeScope(ApiModel):
    # userId is the acting caller (always present) — also the member key for the classic {org,user}
    # scope. The household keys below are separate partition selectors.
    user_id: str = Field(alias="userId", min_length=1)
    organization_id: str | None = Field(default=None, alias="organizationId", min_length=1)
    app_name: str | None = Field(default=None, alias="appName", min_length=1)
    domain: str | None = Field(default=None, min_length=1)
    # Household partition selectors: householdId (the shared grouping) + memberId (a person in the
    # household). The control plane infers the scope level from the attribute's schema, not the
    # agent, and derives householdId from the acting member when omitted.
    household_id: str | None = Field(default=None, alias="householdId", min_length=1)
    member_id: str | None = Field(default=None, alias="memberId", min_length=1)


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
    sensitivity: str | None = None
    memory_source: str | None = Field(default=None, alias="memorySource")


class ApprovedTopic(ApiModel):
    topic: str
    sensitivity: str = "normal"
    description: str | None = None


class WritablePreference(ApiModel):
    """A writable canonical attribute annotated with the scope level and its meaning.

    ``description`` mirrors ``ApprovedTopic.description`` so the agent can map a user statement to the
    right attribute the same way it maps to a topic.
    """

    attribute: str
    level: str  # "member" | "household" | "household_member"
    description: str | None = None
    # Health data: stricter matching, a confirmation turn, and a consent record.
    health: bool = False


class HouseholdMemberModel(ApiModel):
    member_id: str = Field(alias="memberId")
    display_name: str | None = Field(default=None, alias="displayName")
    relationship: str = "member"
    has_login: bool = Field(default=False, alias="hasLogin")
    is_guardian: bool = Field(default=False, alias="isGuardian")
    member_kind: str = Field(default="PROXY_ADULT", alias="memberKind")
    minor: bool = False
    # "active", or "provisional" while a proposed member awaits the user's confirmation.
    status: str = "active"
    aliases: tuple[str, ...] = ()
    # True for the logged-in customer the snapshot was resolved for.
    is_self: bool = Field(default=False, alias="isSelf")


class EffectivePreferenceSnapshotResponse(ApiModel):
    agent_id: str = Field(alias="agentId")
    scope: RuntimeScope
    session_id: str = Field(alias="sessionId")
    preferences: dict[str, PreferenceValue]
    snapshot_version: str = Field(alias="snapshotVersion")
    policy_version: str = Field(alias="policyVersion")
    schema_versions: dict[str, str] = Field(alias="schemaVersions")
    writable_preferences: tuple[str, ...] = Field(default=(), alias="writablePreferences")
    writable_preference_details: tuple[WritablePreference, ...] = Field(
        default=(), alias="writablePreferenceDetails"
    )
    approved_topics: tuple[str, ...] = Field(default=(), alias="approvedTopics")
    approved_topic_details: tuple[ApprovedTopic, ...] = Field(
        default=(), alias="approvedTopicDetails"
    )
    household_id: str | None = Field(default=None, alias="householdId")
    household_members: tuple[HouseholdMemberModel, ...] = Field(
        default=(), alias="householdMembers"
    )
    # The logged-in customer's member id, and the member whose per-member values are shown.
    acting_member_id: str | None = Field(default=None, alias="actingMemberId")
    resolved_member_id: str | None = Field(default=None, alias="resolvedMemberId")
    generated_at: datetime = Field(alias="generatedAt")


class RawProfilesRequest(ApiModel):
    scope: RuntimeScope
    schema_ids: tuple[str, ...] = Field(alias="schemaIds", min_length=1)


_SOURCE_PATTERN = "^(user_directed|inference)$"


class MemoryEventRequest(ApiModel):
    scope: RuntimeScope
    text: str = Field(min_length=1)
    candidates: tuple[PreferenceUpdate, ...] = ()
    source: str = Field(default="user_directed", pattern=_SOURCE_PATTERN)


class PreferenceUpdate(ApiModel):
    schema_id: str | None = Field(default=None, alias="schemaId", min_length=1)
    attribute: str = Field(min_length=1)
    value: Any


class ExplicitPreferenceUpdate(ApiModel):
    scope: RuntimeScope
    schema_id: str | None = Field(default=None, alias="schemaId", min_length=1)
    value: Any
    source: str = Field(default="user_directed", pattern=_SOURCE_PATTERN)
    # A per-member attribute may name the person instead of passing scope.memberId; the platform
    # matches the name inside the customer's household. Omit both for the customer themself.
    member_name: str | None = Field(default=None, alias="memberName", min_length=1)
    relationship: str | None = Field(default=None, min_length=1)
    # True only after the user answered yes to the platform's confirmationPrompt.
    confirmed: bool = False


class HouseholdMemberAddRequest(ApiModel):
    scope: RuntimeScope
    name: str = Field(min_length=1)
    relationship: str | None = Field(default=None, min_length=1)
    # The proposed (provisional) member id returned by the first call, when confirming it.
    member_id: str | None = Field(default=None, alias="memberId", min_length=1)
    confirmed: bool = False


class HouseholdMemberUpdateRequest(ApiModel):
    scope: RuntimeScope
    display_name: str | None = Field(default=None, alias="displayName", min_length=1)
    minor: bool | None = None


class HouseholdMemberMergeRequest(ApiModel):
    scope: RuntimeScope
    keep_member_id: str = Field(alias="keepMemberId", min_length=1)
    merge_member_id: str = Field(alias="mergeMemberId", min_length=1)
    confirmed: bool = False


class PreferenceMoveRequest(ApiModel):
    """Move one per-member value from scope.memberId to another member (a split)."""

    scope: RuntimeScope
    to_member_id: str = Field(alias="toMemberId", min_length=1)
    confirmed: bool = False


class PreferenceForgetRequest(ApiModel):
    """Delete one value (scope.memberId for a per-member attribute; omit for yourself)."""

    scope: RuntimeScope


class DynamicMemoryWrite(ApiModel):
    scope: RuntimeScope
    topic: str = Field(min_length=1)
    value: Any
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: str = Field(default="user_directed", pattern=_SOURCE_PATTERN)


class HouseholdMemberWriteRequest(ApiModel):
    display_name: str | None = Field(default=None, alias="displayName")
    relationship: str = Field(default="member", min_length=1)
    has_login: bool = Field(default=False, alias="hasLogin")
    is_guardian: bool = Field(default=False, alias="isGuardian")


class ForgetMemoryRequest(ApiModel):
    scope: RuntimeScope


class PurgeMemoryRequest(ApiModel):
    tier: str | None = Field(default=None, pattern="^(canonical|dynamic)$")
    attribute: str | None = Field(default=None, min_length=1)
    topic: str | None = Field(default=None, min_length=1)
    dry_run: bool = Field(default=True, alias="dryRun")


class RuntimeMutationResponse(ApiModel):
    # "updated" / "accepted" when written. Nothing is written for:
    # "needs_confirmation" (ask the user confirmationPrompt, then repeat with confirmed=true),
    # "ambiguous" (ask which of `candidates`), "not_allowed" (see `message`).
    status: str
    reference: str | None = None
    profile_version: int | None = Field(default=None, alias="profileVersion")
    member_id: str | None = Field(default=None, alias="memberId")
    confirmation_prompt: str | None = Field(default=None, alias="confirmationPrompt")
    candidates: tuple[HouseholdMemberModel, ...] = ()
    message: str | None = None


class ApiError(BaseModel):
    code: str
    message: str
    correlation_id: str = Field(alias="correlationId")
