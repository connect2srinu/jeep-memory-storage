from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from control_plane_api.api.runtime.models import (
    ApprovedTopic,
    DynamicMemoryWrite,
    EffectivePreferenceSnapshotResponse,
    ExplicitPreferenceUpdate,
    ForgetMemoryRequest,
    HouseholdMemberModel,
    HouseholdMemberWriteRequest,
    MemoryEventRequest,
    PreferenceValue,
    PurgeMemoryRequest,
    RawProfilesRequest,
    ResolvePreferencesRequest,
    RuntimeMutationResponse,
    RuntimeScope,
    WritablePreference,
)
from control_plane_api.domain.control_plane import AccessPermission
from control_plane_api.domain.memory import (
    MemoryEvent,
    MemoryProfile,
    MemoryProfileSchema,
    MemoryScope,
    PreferenceWrite,
)
from control_plane_api.domain.preferences import Preference, PreferenceSource
from control_plane_api.domain.resolution import (
    DomainAccessPolicy,
    PreferenceCatalog,
    PreferenceDefinition,
    ResolutionPolicy,
    ResolutionPolicyRegistry,
    ResolutionStrategy,
)
from control_plane_api.domain.runtime import (
    RuntimeAgent,
    RuntimeDynamicPolicy,
    RuntimeResolutionConfig,
    RuntimeSchemaGrant,
)
from control_plane_api.domain.sensitivity import (
    MemorySource,
    SensitivityTier,
    max_tier,
    parse_tier,
)
from control_plane_api.observability.runtime import correlation_id_context
from control_plane_api.persistence.runtime_repository import RuntimeControlPlaneRepository
from control_plane_api.repositories import MemoryStore
from control_plane_api.security.authentication import AuthenticatedPrincipal
from control_plane_api.services.authorization import AgentCapability
from control_plane_api.services.memory_classification import classify_content
from control_plane_api.services.preference_resolver import PreferenceResolver
from control_plane_api.services.scope_registry import ScopeRegistry

logger = logging.getLogger("uvicorn.error.control_plane_api.preference_resolution")

# Scope keys beyond organization_id, and which scope contract each combination maps to.
_SUB_SCOPE_KEYS = ("user_id", "household_id", "member_id")
# Per-sub-entity keys: a schema bound to one is resolved lazily (only when the request names it).
_ENTITY_SCOPE_KEYS = frozenset({"member_id"})
_CONTRACT_BY_KEYS = {
    frozenset({"organization_id", "user_id"}): "organization-user-profile",
    frozenset({"organization_id", "household_id"}): "organization-household-profile",
    frozenset(
        {"organization_id", "household_id", "member_id"}
    ): "organization-household-member-profile",
}


def _scope_values(scope: RuntimeScope) -> dict[str, str]:
    """The sub-entity scope keys the request carries (userId / householdId / memberId)."""
    return {key: getattr(scope, key) for key in _SUB_SCOPE_KEYS if getattr(scope, key, None)}


def _primary_scope_values(scope: RuntimeScope) -> dict[str, str]:
    """The top-level partition for member/household-level writes (dynamic memory)."""
    if scope.user_id:
        return {"user_id": scope.user_id}
    if scope.household_id:
        return {"household_id": scope.household_id}
    raise ValueError("scope requires a userId or householdId")


def _screen_memory_write(
    value: object, *, declared: str | None, source: str, label: str
) -> SensitivityTier:
    """Classify a memory write and enforce the sensitivity/source policy, or raise.

    Effective tier is the max of the attribute's declared classification and a content scan.
    Policy: RESTRICTED -> reject; SENSITIVE + inferred -> reject (only user-directed sensitive
    memories may be stored); otherwise allow. Returns the effective tier for auditing.
    """
    detected, category = classify_content(value)
    tier = max_tier(parse_tier(declared), detected)
    memory_source = MemorySource.INFERENCE if source == MemorySource.INFERENCE else (
        MemorySource.USER_DIRECTED
    )
    if tier is SensitivityTier.RESTRICTED:
        reason = category or "restricted attribute"
        raise ValueError(f"{label} contains restricted content ({reason}) and cannot be stored")
    if tier is SensitivityTier.SENSITIVE and memory_source is MemorySource.INFERENCE:
        raise PermissionError(
            f"{label} is sensitive and was inferred, not user-directed; it will not be stored"
        )
    return tier


def _log_flow_step(step: str, **fields: object) -> None:
    logger.info(
        json.dumps(
            {
                "correlation_id": correlation_id_context.get(),
                "flow": "effective_preference_snapshot",
                "step": step,
                **fields,
            },
            sort_keys=True,
            default=str,
        )
    )


def _log_memory_write(*, tier: str, version: int, **fields: object) -> None:
    """Emit a structured create/update event for a long-term memory write.

    ``op`` is derived from the version (1 = created, otherwise updated). Values are never logged —
    they can be sensitive. Flows to container logs and, in GCP, to Cloud Logging.
    """
    logger.info(
        json.dumps(
            {
                "event": "memory_write",
                "correlation_id": correlation_id_context.get(),
                "tier": tier,
                "op": "created" if version == 1 else "updated",
                "version": version,
                **fields,
            },
            sort_keys=True,
            default=str,
        )
    )


def _log_memory_deletion(*, op: str, **fields: object) -> None:
    """Emit a structured audit event for a memory deletion (forget / purge)."""
    logger.info(
        json.dumps(
            {
                "event": "memory_deletion",
                "correlation_id": correlation_id_context.get(),
                "op": op,
                **fields,
            },
            sort_keys=True,
            default=str,
        )
    )


class RuntimeMemoryService:
    def __init__(
        self,
        repository: RuntimeControlPlaneRepository,
        store: MemoryStore,
        scope_registry: ScopeRegistry,
    ) -> None:
        self.repository = repository
        self.store = store
        self.scope_registry = scope_registry

    async def resolve_preferences(
        self,
        principal: AuthenticatedPrincipal,
        request: ResolvePreferencesRequest,
    ) -> EffectivePreferenceSnapshotResponse:
        _log_flow_step(
            "control_plane_validation_started",
            claimed_agent_id=principal.claimed_agent_id,
            requested_agent_id=request.requested_agent_id,
            requested_domain=request.scope.domain,
            requested_organization_id=request.scope.organization_id,
            session_id=request.session_id,
        )
        agent = await self._agent(principal, request.requested_agent_id)
        self._require_capability(agent, AgentCapability.RESOLVE_CONTEXT)
        self._require_consumer_scope(agent, request.scope)
        grants = await self.repository.list_schema_grants(agent.id)
        readable = tuple(grant for grant in grants if self._allows(grant.permission, write=False))
        writable = tuple(grant for grant in grants if self._allows(grant.permission, write=True))
        _log_flow_step(
            "agent_capability_scope_and_grants_validated",
            agent_id=agent.id,
            capability=AgentCapability.RESOLVE_CONTEXT.value,
            domain=agent.domain_id,
            organization_id=agent.organization_id,
            readable_schema_ids=[grant.schema_id for grant in readable],
            writable_schema_ids=[grant.schema_id for grant in writable],
        )
        config = await self.repository.get_resolution_config(agent.id, agent.domain_id)
        dynamic_policies: dict[str, RuntimeDynamicPolicy] = {}
        for domain_id in dict.fromkeys(grant.domain_id for grant in readable):
            dynamic = await self.repository.get_dynamic_memory_policy(domain_id)
            if dynamic is not None and dynamic.enabled and dynamic.approved_topics:
                dynamic_policies[domain_id] = dynamic
        catalog, policies = self._resolution_components(agent, grants, config, dynamic_policies)
        # Populate household_id (derived from the acting member) when any readable schema is
        # household-scoped, so household-shared and household-member profiles can be addressed.
        effective_scope = request.scope
        if any("household_id" in grant.scope_keys for grant in readable):
            effective_scope = await self._with_household(request.scope, agent)
        candidates: list[Preference] = []
        for grant in readable:
            # Per-member schemas are read lazily: only when the turn names a member. A top-level
            # resolve skips them to keep read fan-out minimal.
            entity_key = self._entity_key(grant)
            if entity_key and not getattr(effective_scope, entity_key):
                continue
            await self._register_schema(grant)
            scope = self._owner_scope(effective_scope, grant)
            _log_flow_step(
                "authorized_memory_profiles_read_started",
                agent_id=agent.id,
                memory_backend=type(self.store).__name__,
                owner_domain=grant.domain_id,
                owner_organization_id=grant.owner_organization_id,
                schema_id=grant.schema_id,
            )
            profiles = await self.store.get_profiles(scope, (grant.schema_id,))
            _log_flow_step(
                "authorized_memory_profiles_read_completed",
                agent_id=agent.id,
                memory_backend=type(self.store).__name__,
                owner_domain=grant.domain_id,
                profile_count=len(profiles),
                schema_id=grant.schema_id,
            )
            for profile in profiles:
                candidates.extend(
                    Preference(
                        key=grant.field_to_attribute[field],
                        value=value,
                        source=PreferenceSource.MEMORY_PROFILE,
                        owner_domain=grant.domain_id,
                        confidence=1.0,
                        updated_at=profile.updated_at,
                        provenance={
                            "schema_id": grant.schema_id,
                            "schema_version": grant.schema_version,
                            "profile_version": profile.version,
                        },
                        sensitivity=grant.attribute_sensitivity.get(
                            grant.field_to_attribute[field]
                        ),
                    )
                    for field, value in profile.values.items()
                    if field in grant.field_to_attribute
                )
        seen_dynamic_domains: set[str] = set()
        for grant in readable:
            policy = dynamic_policies.get(grant.domain_id)
            if policy is None or grant.domain_id in seen_dynamic_domains:
                continue
            seen_dynamic_domains.add(grant.domain_id)
            # Dynamic (topic) memory is top-level (member/household), independent of a schema's grain.
            owner_scope = MemoryScope(
                organization_id=grant.owner_organization_id,
                **_primary_scope_values(request.scope),
            )
            for memory in await self.store.get_dynamic_memories(owner_scope, policy.approved_topics):
                candidates.append(
                    Preference(
                        key=f"{grant.domain_id}.topic.{memory.topic}",
                        value=memory.value,
                        source=PreferenceSource.DYNAMIC_MEMORY,
                        owner_domain=grant.domain_id,
                        confidence=memory.confidence,
                        updated_at=memory.updated_at,
                        expires_at=memory.expires_at,
                        provenance={"topic": memory.topic, "dynamic_version": memory.version},
                        sensitivity=max_tier(
                            parse_tier(memory.sensitivity),
                            parse_tier(policy.topic_sensitivity.get(memory.topic)),
                        ).value,
                        memory_source=memory.source,
                    )
                )
        _log_flow_step(
            "configured_resolution_policy_loaded",
            agent_id=agent.id,
            candidate_count=len(candidates),
            policy_version=policies.version,
            resolution_policy_id=(config.policy_id if config else "runtime-default"),
        )
        snapshot = PreferenceResolver(catalog, policies).resolve(
            user_id=request.scope.user_id,
            session_id=request.session_id,
            consumer_domain=agent.domain_id,
            agent_id=agent.id,
            preferences=candidates,
            readable_domains=tuple(dict.fromkeys(grant.domain_id for grant in readable)),
        )
        _log_flow_step(
            "configured_resolution_policy_applied",
            agent_id=agent.id,
            candidate_count=len(candidates),
            effective_preference_count=len(snapshot.preferences),
            policy_version=policies.version,
        )
        include_provenance = request.include_provenance and (
            AgentCapability.INSPECT_PROVENANCE.value in agent.capabilities
        )
        preferences = {
            key: PreferenceValue(
                value=item.preference.value,
                source=item.preference.source.value,
                owner_domain=item.preference.owner_domain,
                resolution_reason=item.resolution_reason,
                provenance=item.preference.provenance if include_provenance else None,
                sensitivity=item.preference.sensitivity,
                memory_source=item.preference.memory_source,
            )
            for key, item in snapshot.preferences.items()
        }
        schema_versions = {grant.schema_id: grant.schema_version for grant in readable}
        writable_preferences = tuple(
            dict.fromkeys(
                attribute
                for grant in grants
                if grant.domain_id == agent.domain_id and self._allows(grant.permission, write=True)
                for attribute in grant.field_to_attribute.values()
            )
        )
        # Annotate each writable attribute with the scope level it is written at, so the agent
        # knows a "household_member"-level attribute needs a memberId — without any local config.
        seen_writable: set[str] = set()
        writable_preference_details: list[WritablePreference] = []
        for grant in grants:
            if grant.domain_id != agent.domain_id or not self._allows(
                grant.permission, write=True
            ):
                continue
            level = self._scope_level(grant)
            for attribute in grant.field_to_attribute.values():
                if attribute in seen_writable:
                    continue
                seen_writable.add(attribute)
                writable_preference_details.append(
                    WritablePreference(
                        attribute=attribute,
                        level=level,
                        description=grant.attribute_descriptions.get(attribute),
                    )
                )
        household_members: tuple[HouseholdMemberModel, ...] = ()
        if effective_scope.household_id:
            household_members = tuple(
                HouseholdMemberModel(
                    member_id=item.member_id,
                    display_name=item.display_name,
                    relationship=item.relationship,
                    has_login=item.has_login,
                    is_guardian=item.is_guardian,
                )
                for item in await self.repository.list_household_members(
                    agent.organization_id, effective_scope.household_id
                )
            )
        agent_dynamic_policy = dynamic_policies.get(agent.domain_id)
        approved_topics = agent_dynamic_policy.approved_topics if agent_dynamic_policy else ()
        approved_topic_details = (
            tuple(
                ApprovedTopic(
                    topic=topic,
                    sensitivity=agent_dynamic_policy.topic_sensitivity.get(topic, "normal"),
                    description=agent_dynamic_policy.topic_descriptions.get(topic),
                )
                for topic in agent_dynamic_policy.approved_topics
            )
            if agent_dynamic_policy
            else ()
        )
        generated_at = datetime.now(UTC)
        version_payload = json.dumps(
            {
                "agent": agent.id,
                "scope": request.scope.model_dump(by_alias=True),
                "preferences": {
                    key: value.model_dump(by_alias=True, mode="json")
                    for key, value in sorted(preferences.items())
                },
                "policy": policies.version,
                "schemas": schema_versions,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        response = EffectivePreferenceSnapshotResponse(
            agent_id=agent.id,
            scope=request.scope,
            session_id=request.session_id,
            preferences=preferences,
            snapshot_version=hashlib.sha256(version_payload.encode()).hexdigest()[:24],
            policy_version=policies.version,
            schema_versions=schema_versions,
            writable_preferences=writable_preferences,
            writable_preference_details=tuple(writable_preference_details),
            approved_topics=approved_topics,
            approved_topic_details=approved_topic_details,
            household_id=effective_scope.household_id,
            household_members=household_members,
            generated_at=generated_at,
        )
        _log_flow_step(
            "effective_preference_snapshot_returned",
            agent_id=agent.id,
            preference_count=len(response.preferences),
            schema_count=len(response.schema_versions),
            session_id=request.session_id,
            snapshot_version=response.snapshot_version,
            writable_preference_count=len(response.writable_preferences),
        )
        return response

    async def raw_profiles(
        self, principal: AuthenticatedPrincipal, request: RawProfilesRequest
    ) -> dict[str, object]:
        agent = await self._agent(principal)
        self._require_capability(agent, AgentCapability.INSPECT_PROVENANCE)
        self._require_consumer_scope(agent, request.scope)
        grants = {
            item.schema_id: item for item in await self.repository.list_schema_grants(agent.id)
        }
        profiles: list[tuple[MemoryProfile, str]] = []
        for schema_id in request.schema_ids:
            grant = grants.get(schema_id)
            if grant is None or not self._allows(grant.permission, write=False):
                raise PermissionError(
                    f"agent {agent.id!r} lacks READ access to schema {schema_id!r}"
                )
            await self._register_schema(grant)
            scope = self._owner_scope(request.scope, grant)
            profiles.extend(
                (profile, grant.domain_id)
                for profile in await self.store.get_profiles(scope, (schema_id,))
            )
        return {
            "agentId": agent.id,
            "profiles": [
                {
                    "schemaId": profile.schema_id,
                    "domain": owner_domain,
                    "organizationId": profile.scope.organization_id,
                    "values": profile.values,
                    "version": profile.version,
                    "updatedAt": profile.updated_at.isoformat(),
                }
                for profile, owner_domain in profiles
            ],
        }

    async def ingest_event(
        self, principal: AuthenticatedPrincipal, request: MemoryEventRequest
    ) -> RuntimeMutationResponse:
        agent = await self._agent(principal)
        self._require_capability(agent, AgentCapability.SUBMIT_CANDIDATES)
        self._require_consumer_scope(agent, request.scope)
        grants = await self.repository.list_schema_grants(agent.id)
        writes = []
        for candidate in request.candidates:
            grant = self._resolve_write_grant(
                agent,
                grants,
                candidate.attribute,
                agent.domain_id,
                candidate.schema_id,
            )
            if self._entity_key(grant):
                raise ValueError(
                    f"attribute {candidate.attribute!r} is sub-entity-scoped; write it via "
                    "PUT /preferences/{attribute} with the entity id, not through ingest_event"
                )
            _screen_memory_write(
                candidate.value,
                declared=grant.attribute_sensitivity.get(candidate.attribute),
                source=request.source,
                label=f"attribute {candidate.attribute!r}",
            )
            await self._register_schema(grant)
            writes.append(
                PreferenceWrite(
                    grant.schema_id,
                    self._profile_field(grant, candidate.attribute),
                    candidate.value,
                )
            )
        scope = self._memory_scope(request.scope, agent)
        result = await self.store.ingest_event(scope, MemoryEvent(request.text, tuple(writes)))
        return RuntimeMutationResponse(status="accepted", reference=result.natural_memory.id)

    async def write_dynamic_memory(
        self, principal: AuthenticatedPrincipal, request: DynamicMemoryWrite
    ) -> RuntimeMutationResponse:
        agent = await self._agent(principal)
        self._require_capability(agent, AgentCapability.SUBMIT_CANDIDATES)
        self._require_consumer_scope(agent, request.scope)
        policy = await self.repository.get_dynamic_memory_policy(agent.domain_id)
        if policy is None or not policy.enabled:
            raise PermissionError(
                f"dynamic memory is not enabled for domain {agent.domain_id!r}"
            )
        if request.topic not in policy.approved_topics:
            raise PermissionError(
                f"topic {request.topic!r} is not an approved dynamic-memory topic for "
                f"domain {agent.domain_id!r}"
            )
        tier = _screen_memory_write(
            request.value,
            declared=policy.topic_sensitivity.get(request.topic),
            source=request.source,
            label=f"topic {request.topic!r}",
        )
        expires_at = (
            datetime.now(UTC) + timedelta(days=policy.retention_days)
            if policy.retention_days
            else None
        )
        scope = self._memory_scope(request.scope, agent)
        memory = await self.store.write_dynamic_memory(
            scope,
            topic=request.topic,
            value=request.value,
            confidence=request.confidence,
            expires_at=expires_at,
            sensitivity=tier.value,
            source=request.source,
        )
        _log_memory_write(
            tier="dynamic",
            version=memory.version,
            agent_id=agent.id,
            domain=agent.domain_id,
            topic=memory.topic,
            sensitivity=tier.value,
            source=request.source,
            reference=f"{agent.domain_id}.topic.{memory.topic}",
        )
        return RuntimeMutationResponse(
            status="accepted",
            reference=f"{agent.domain_id}.topic.{memory.topic}",
            profile_version=memory.version,
        )

    async def forget_user_memories(
        self, principal: AuthenticatedPrincipal, request: ForgetMemoryRequest
    ) -> dict[str, object]:
        """Right-to-be-forgotten: delete every memory for the requested user scope."""
        agent = await self._agent(principal)
        self._require_capability(agent, AgentCapability.SUBMIT_CANDIDATES)
        self._require_consumer_scope(agent, request.scope)
        scope = self._user_scope(request.scope, agent)
        deleted = await self.store.forget_user(scope)
        _log_memory_deletion(
            op="forget",
            agent_id=agent.id,
            domain=agent.domain_id,
            organization_id=agent.organization_id,
            user_id=request.scope.user_id,
            household_id=request.scope.household_id,
            member_id=request.scope.member_id,
            deleted=deleted,
        )
        return {
            "status": "forgotten",
            "userId": request.scope.user_id,
            "householdId": request.scope.household_id,
            "memberId": request.scope.member_id,
            "deleted": deleted,
        }

    async def purge_memories(
        self, principal: AuthenticatedPrincipal, request: PurgeMemoryRequest
    ) -> dict[str, object]:
        """Operator on-demand deletion across the organization, gated by ADMINISTER_MEMORY.

        Requires at least one filter (tier, attribute, or topic). ``dryRun`` (default true) previews
        the matches without deleting.
        """
        agent = await self._agent(principal)
        self._require_capability(agent, AgentCapability.ADMINISTER_MEMORY)
        if not (request.tier or request.attribute or request.topic):
            raise ValueError("purge requires at least one of tier, attribute, or topic")
        matches = await self.store.purge(
            organization_id=agent.organization_id,
            tier=request.tier,
            attribute=request.attribute,
            topic=request.topic,
            dry_run=request.dry_run,
        )
        _log_memory_deletion(
            op="purge_preview" if request.dry_run else "purge",
            agent_id=agent.id,
            organization_id=agent.organization_id,
            tier=request.tier,
            attribute=request.attribute,
            topic=request.topic,
            matched=len(matches),
        )
        return {
            "status": "preview" if request.dry_run else "purged",
            "matched": len(matches),
            "entries": list(matches),
        }

    async def update_preference(
        self,
        principal: AuthenticatedPrincipal,
        attribute: str,
        request: ExplicitPreferenceUpdate,
    ) -> RuntimeMutationResponse:
        agent = await self._agent(principal)
        self._require_capability(agent, AgentCapability.SUBMIT_CANDIDATES)
        self._require_consumer_scope(agent, request.scope)
        grants = await self.repository.list_schema_grants(agent.id)
        grant = self._resolve_write_grant(
            agent,
            grants,
            attribute,
            agent.domain_id,
            request.schema_id,
        )
        profile_field = self._profile_field(grant, attribute)
        sensitivity = _screen_memory_write(
            request.value,
            declared=grant.attribute_sensitivity.get(attribute),
            source=request.source,
            label=f"attribute {attribute!r}",
        )
        write_request_scope = request.scope
        if "household_id" in grant.scope_keys:
            write_request_scope = await self._with_household(request.scope, agent)
            await self._require_household_write(write_request_scope, agent, grant)
        await self._register_schema(grant)
        write_scope = self._build_scope(
            organization_id=agent.organization_id,
            scope_keys=grant.scope_keys,
            values=_scope_values(write_request_scope),
            strict=True,
        )
        profile = await self.store.write_preference(
            write_scope,
            schema_id=grant.schema_id,
            attribute=profile_field,
            value=request.value,
        )
        _log_memory_write(
            tier="canonical",
            version=profile.version,
            agent_id=agent.id,
            domain=agent.domain_id,
            attribute=attribute,
            schema_id=grant.schema_id,
            sensitivity=sensitivity.value,
            source=request.source,
            reference=f"{profile.schema_id}:{attribute}",
        )
        return RuntimeMutationResponse(
            status="updated",
            reference=f"{profile.schema_id}:{attribute}",
            profile_version=profile.version,
        )

    async def upsert_household_member(
        self,
        principal: AuthenticatedPrincipal,
        household_id: str,
        member_id: str,
        request: HouseholdMemberWriteRequest,
    ) -> dict[str, object]:
        """Add or update a member on a household roster (enrolment/admin action)."""
        agent = await self._agent(principal)
        self._require_capability(agent, AgentCapability.ADMINISTER_MEMORY)
        await self.repository.upsert_household_member(
            organization_id=agent.organization_id,
            household_id=household_id,
            member_id=member_id,
            display_name=request.display_name,
            relationship=request.relationship,
            has_login=request.has_login,
            is_guardian=request.is_guardian,
        )
        return {"status": "upserted", "householdId": household_id, "memberId": member_id}

    async def deactivate_household_member(
        self, principal: AuthenticatedPrincipal, household_id: str, member_id: str
    ) -> dict[str, object]:
        """Deactivate a household member. Their memory scope is cleared via forget/purge."""
        agent = await self._agent(principal)
        self._require_capability(agent, AgentCapability.ADMINISTER_MEMORY)
        removed = await self.repository.deactivate_household_member(
            organization_id=agent.organization_id,
            household_id=household_id,
            member_id=member_id,
        )
        return {
            "status": "deactivated" if removed else "not_found",
            "householdId": household_id,
            "memberId": member_id,
        }

    async def _agent(
        self, principal: AuthenticatedPrincipal, requested_agent_id: str | None = None
    ) -> RuntimeAgent:
        agent = await self.repository.resolve_agent(
            principal=principal.principal,
            local_agent_id=principal.claimed_agent_id,
        )
        if agent is None:
            raise PermissionError("authenticated principal is not mapped to an active agent")
        if requested_agent_id is not None and requested_agent_id != agent.id:
            raise PermissionError("requested agent does not match authenticated principal")
        return agent

    @staticmethod
    def _require_capability(agent: RuntimeAgent, capability: AgentCapability) -> None:
        if capability.value not in agent.capabilities:
            raise PermissionError(f"agent {agent.id!r} lacks capability {capability.value}")

    @staticmethod
    def _require_consumer_scope(agent: RuntimeAgent, scope: RuntimeScope) -> None:
        if scope.domain is not None and scope.domain != agent.domain_id:
            raise PermissionError("request scope domain does not match registered agent domain")
        if scope.organization_id is not None and scope.organization_id != agent.organization_id:
            raise PermissionError(
                "request scope organization does not match registered agent organization"
            )

    @staticmethod
    def _allows(permission: AccessPermission, *, write: bool) -> bool:
        allowed = (
            {AccessPermission.WRITE, AccessPermission.READ_WRITE}
            if write
            else {AccessPermission.READ, AccessPermission.READ_WRITE}
        )
        return permission in allowed

    def _require_write_grant(
        self,
        agent: RuntimeAgent,
        grants: dict[str, RuntimeSchemaGrant],
        schema_id: str,
        scope_domain: str,
    ) -> RuntimeSchemaGrant:
        grant = grants.get(schema_id)
        if grant is None or not self._allows(grant.permission, write=True):
            raise PermissionError(f"agent {agent.id!r} lacks WRITE access to schema {schema_id!r}")
        if grant.domain_id != scope_domain:
            raise PermissionError("cross-domain profile writes are not allowed")
        if grant.owner_organization_id != agent.organization_id:
            raise PermissionError("cross-organization profile writes are not allowed")
        return grant

    def _resolve_write_grant(
        self,
        agent: RuntimeAgent,
        grants: tuple[RuntimeSchemaGrant, ...],
        attribute: str,
        scope_domain: str,
        schema_id: str | None,
    ) -> RuntimeSchemaGrant:
        """Resolve a schema only from active, same-domain writable grants."""
        if schema_id is not None:
            return self._require_write_grant(
                agent,
                {grant.schema_id: grant for grant in grants},
                schema_id,
                scope_domain,
            )

        matching = tuple(
            grant
            for grant in grants
            if attribute in grant.field_to_attribute
            or attribute in grant.field_to_attribute.values()
        )
        writable = tuple(
            grant
            for grant in matching
            if grant.domain_id == scope_domain
            and grant.owner_organization_id == agent.organization_id
            and self._allows(grant.permission, write=True)
        )
        if len(writable) == 1:
            return writable[0]
        if len(writable) > 1:
            schema_ids = ", ".join(sorted(grant.schema_id for grant in writable))
            raise ValueError(
                f"attribute {attribute!r} maps to multiple writable schemas ({schema_ids}); "
                "fix the active schema mappings before retrying"
            )
        if matching:
            raise PermissionError(
                f"agent {agent.id!r} has no same-domain WRITE access for attribute {attribute!r}"
            )
        raise ValueError(
            f"attribute {attribute!r} is not registered in a writable schema for "
            f"domain {scope_domain!r}"
        )

    @staticmethod
    def _profile_field(grant: RuntimeSchemaGrant, attribute: str) -> str:
        if attribute in grant.field_to_attribute:
            return attribute
        for profile_field, canonical_attribute in grant.field_to_attribute.items():
            if canonical_attribute == attribute:
                return profile_field
        raise ValueError(f"attribute {attribute!r} is not registered in schema {grant.schema_id!r}")

    async def _register_schema(self, grant: RuntimeSchemaGrant) -> None:
        await self.store.register_schema(
            MemoryProfileSchema(
                id=grant.schema_id,
                domain=grant.domain_id,
                version=grant.schema_version,
                fields=frozenset(grant.field_to_attribute),
            )
        )

    def _memory_scope(self, scope: RuntimeScope, agent: RuntimeAgent) -> MemoryScope:
        """The primary member/household scope for top-level writes (dynamic memory)."""
        return MemoryScope(organization_id=agent.organization_id, **_primary_scope_values(scope))

    @staticmethod
    def _entity_key(grant: RuntimeSchemaGrant) -> str | None:
        """The per-member key a grant partitions on (member_id), if any."""
        return next((key for key in grant.scope_keys if key in _ENTITY_SCOPE_KEYS), None)

    @staticmethod
    def _scope_level(grant: RuntimeSchemaGrant) -> str:
        """The scope level surfaced to the agent so it knows which id (if any) to supply."""
        keys = set(grant.scope_keys)
        if "member_id" in keys:
            return "household_member"
        if "household_id" in keys:
            return "household"
        return "member"

    def _build_scope(
        self,
        *,
        organization_id: str,
        scope_keys: tuple[str, ...],
        values: dict[str, str],
        strict: bool,
    ) -> MemoryScope:
        """Build the scope a schema is bound to from the request's available scope values.

        ``strict`` (writes) rejects sub-entity keys the schema does not use; non-strict (reads) ignores
        them, so a resolve can read broader-scoped schemas at their own level while it names a
        specific member for the narrower ones.
        """
        contract = _CONTRACT_BY_KEYS.get(frozenset(scope_keys))
        if contract is None:
            raise ValueError(f"unsupported runtime scope keys {tuple(scope_keys)!r}")
        needed = [key for key in scope_keys if key != "organization_id"]
        scope_values = {"organization_id": organization_id}
        for key in needed:
            value = values.get(key)
            if not value:
                raise ValueError(
                    f"scope key {key!r} is required for this schema but was not supplied"
                )
            scope_values[key] = value
        if strict:
            # A write must not name a per-member partition (memberId) the schema doesn't use —
            # e.g. a memberId on a household-shared or member-level attribute.
            invalid = {key for key in _ENTITY_SCOPE_KEYS if values.get(key)} - set(scope_keys)
            if invalid:
                raise ValueError(
                    f"scope keys {sorted(invalid)} are not valid for this attribute's schema"
                )
        return self.scope_registry.resolve(contract, scope_values)

    def _user_scope(self, scope: RuntimeScope, agent: RuntimeAgent) -> MemoryScope:
        """Deletion scope: the exact partition the request names; a broader scope cascades.

        A householdId (optionally + memberId) targets the household partition; otherwise the member
        (userId). A household forget cascades to the members under it.
        """
        if scope.household_id:
            keys = {"household_id": scope.household_id}
            if scope.member_id:
                keys["member_id"] = scope.member_id
        else:
            keys = {"user_id": scope.user_id}
        return MemoryScope(organization_id=agent.organization_id, **keys)

    def _owner_scope(self, scope: RuntimeScope, grant: RuntimeSchemaGrant) -> MemoryScope:
        """Read scope for a grant during resolve/raw-profiles (non-strict — ignores extra keys)."""
        return self._build_scope(
            organization_id=grant.owner_organization_id,
            scope_keys=grant.scope_keys,
            values=_scope_values(scope),
            strict=False,
        )

    async def _resolve_household_id(self, scope: RuntimeScope, agent: RuntimeAgent) -> str:
        """The acting member's household. Derived from the roster; defaults to the member id when a
        household is not modeled (the 95% case where one household == one member)."""
        if scope.household_id:
            return scope.household_id
        derived = await self.repository.get_household_for_member(
            agent.organization_id, scope.user_id
        )
        return derived or scope.user_id

    async def _with_household(self, scope: RuntimeScope, agent: RuntimeAgent) -> RuntimeScope:
        """Return the scope with household_id populated, deriving it if the request omitted it."""
        household_id = await self._resolve_household_id(scope, agent)
        return scope.model_copy(update={"household_id": household_id})

    async def _require_household_write(
        self, scope: RuntimeScope, agent: RuntimeAgent, grant: RuntimeSchemaGrant
    ) -> None:
        """Guardian check: writing another member's profile requires the caller to be a guardian."""
        if "member_id" not in grant.scope_keys:
            return
        target = scope.member_id
        if not target or target == scope.user_id:
            return
        member = await self.repository.get_household_member(
            agent.organization_id, scope.household_id, scope.user_id
        )
        if member is None or not member.is_guardian:
            raise PermissionError(
                f"caller {scope.user_id!r} is not a guardian and cannot write for member "
                f"{target!r}"
            )

    @staticmethod
    def _resolution_components(
        agent: RuntimeAgent,
        grants: tuple[RuntimeSchemaGrant, ...],
        config: RuntimeResolutionConfig | None,
        dynamic_policies: dict[str, RuntimeDynamicPolicy] | None = None,
    ) -> tuple[PreferenceCatalog, ResolutionPolicyRegistry]:
        readable_domains = tuple(
            dict.fromkeys(
                item.domain_id
                for item in grants
                if RuntimeMemoryService._allows(item.permission, write=False)
            )
        )
        writable_domains = tuple(
            dict.fromkeys(
                item.domain_id
                for item in grants
                if RuntimeMemoryService._allows(item.permission, write=True)
            )
        )
        rule_map = config.attribute_rules if config else {}
        definitions = []
        schema_domains = {item.schema_id: item.domain_id for item in grants}
        for grant in grants:
            for attribute in grant.field_to_attribute.values():
                rules = rule_map.get(attribute, {})
                definitions.append(
                    PreferenceDefinition(
                        key=attribute,
                        owner_domain=grant.domain_id,
                        resolution_key=attribute.rsplit(".", 1)[-1],
                        allowed_readers=(agent.domain_id,),
                        allowed_writers=(grant.domain_id,),
                    )
                )
        defaults = config.defaults if config else {}
        default_policy = ResolutionPolicy(
            id=config.policy_id if config else "runtime-default",
            source_priority=tuple(
                PreferenceSource(item)
                for item in defaults.get(
                    "source_priority",
                    [
                        "SESSION_OVERRIDE",
                        "EXPLICIT_PROFILE",
                        "MEMORY_PROFILE",
                        "DOMAIN_MEMORY",
                        "DYNAMIC_MEMORY",
                        "INFERRED_MEMORY",
                        "DEFAULT",
                    ],
                )
            ),
            domain_priority=tuple(defaults.get("domain_priority", [])),
            strategies=tuple(
                ResolutionStrategy(item)
                for item in defaults.get(
                    "strategies",
                    ["SOURCE_PRIORITY", "DOMAIN_PRIORITY", "EXPLICIT_OVER_INFERRED", "MOST_RECENT"],
                )
            ),
            minimum_confidence=float(defaults.get("minimum_confidence", 0.7)),
        )
        policies = {}
        for attribute, rules in rule_map.items():
            logical_key = attribute.rsplit(".", 1)[-1]
            policies[logical_key] = ResolutionPolicy(
                id=f"{default_policy.id}:{logical_key}",
                source_priority=tuple(
                    PreferenceSource(item)
                    for item in (rules.get("source_priority") or default_policy.source_priority)
                ),
                domain_priority=tuple(
                    schema_domains[item]
                    for item in rules.get("schema_precedence", [])
                    if item in schema_domains
                ),
                strategies=tuple(
                    ResolutionStrategy(item)
                    for item in (rules.get("strategies") or default_policy.strategies)
                ),
                minimum_confidence=float(
                    rules.get("minimum_confidence")
                    if rules.get("minimum_confidence") is not None
                    else default_policy.minimum_confidence
                ),
            )
        # Register approved dynamic-memory topics as first-class resolution keys so dynamic
        # candidates group correctly and are gated by the policy's confidence threshold. Their
        # DYNAMIC_MEMORY source already ranks below canonical MEMORY_PROFILE in source_priority.
        for domain_id, dynamic_policy in (dynamic_policies or {}).items():
            for topic in dynamic_policy.approved_topics:
                logical_key = f"topic:{topic}"
                definitions.append(
                    PreferenceDefinition(
                        key=f"{domain_id}.topic.{topic}",
                        owner_domain=domain_id,
                        resolution_key=logical_key,
                        allowed_readers=(agent.domain_id,),
                        allowed_writers=(domain_id,),
                    )
                )
                policies[logical_key] = ResolutionPolicy(
                    id=f"{default_policy.id}:{logical_key}",
                    source_priority=default_policy.source_priority,
                    domain_priority=(),
                    strategies=default_policy.strategies,
                    minimum_confidence=dynamic_policy.confidence_threshold,
                )
        return PreferenceCatalog(tuple(definitions)), ResolutionPolicyRegistry(
            domain_policies=(
                DomainAccessPolicy(agent.domain_id, readable_domains, writable_domains),
            ),
            policies=policies,
            default_policy=default_policy,
            version=config.version if config else "runtime-default-v1",
        )
