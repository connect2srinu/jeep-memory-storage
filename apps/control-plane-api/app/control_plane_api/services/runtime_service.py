from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from control_plane_api.api.runtime.models import (
    EffectivePreferenceSnapshotResponse,
    ExplicitPreferenceUpdate,
    MemoryEventRequest,
    PreferenceValue,
    RawProfilesRequest,
    ResolvePreferencesRequest,
    RuntimeMutationResponse,
    RuntimeScope,
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
    RuntimeResolutionConfig,
    RuntimeSchemaGrant,
)
from control_plane_api.persistence.runtime_repository import RuntimeControlPlaneRepository
from control_plane_api.repositories import MemoryStore
from control_plane_api.security.authentication import AuthenticatedPrincipal
from control_plane_api.services.authorization import AgentCapability
from control_plane_api.services.preference_resolver import PreferenceResolver
from control_plane_api.services.scope_registry import ScopeRegistry


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
        agent = await self._agent(principal, request.requested_agent_id)
        self._require_capability(agent, AgentCapability.RESOLVE_CONTEXT)
        self._require_consumer_scope(agent, request.scope)
        grants = await self.repository.list_schema_grants(agent.id)
        readable = tuple(grant for grant in grants if self._allows(grant.permission, write=False))
        config = await self.repository.get_resolution_config(agent.id, agent.domain_id)
        catalog, policies = self._resolution_components(agent, grants, config)
        candidates: list[Preference] = []
        for grant in readable:
            await self._register_schema(grant)
            scope = self._owner_scope(request.scope, agent, grant.scope_keys)
            profiles = await self.store.get_profiles(scope, (grant.schema_id,))
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
                    )
                    for field, value in profile.values.items()
                    if field in grant.field_to_attribute
                )
        snapshot = PreferenceResolver(catalog, policies).resolve(
            user_id=request.scope.user_id,
            session_id=request.session_id,
            consumer_domain=agent.domain_id,
            agent_id=agent.id,
            preferences=candidates,
            readable_domains=tuple(dict.fromkeys(grant.domain_id for grant in readable)),
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
        return EffectivePreferenceSnapshotResponse(
            agent_id=agent.id,
            scope=request.scope,
            session_id=request.session_id,
            preferences=preferences,
            snapshot_version=hashlib.sha256(version_payload.encode()).hexdigest()[:24],
            policy_version=policies.version,
            schema_versions=schema_versions,
            writable_preferences=writable_preferences,
            generated_at=generated_at,
        )

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
            scope = self._owner_scope(request.scope, agent, grant.scope_keys)
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
        await self._register_schema(grant)
        profile = await self.store.write_preference(
            self._memory_scope(request.scope, agent),
            schema_id=grant.schema_id,
            attribute=profile_field,
            value=request.value,
        )
        return RuntimeMutationResponse(
            status="updated",
            reference=f"{profile.schema_id}:{attribute}",
            profile_version=profile.version,
        )

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
            if grant.domain_id == scope_domain and self._allows(grant.permission, write=True)
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
        return self.scope_registry.resolve(
            "organization-user-profile",
            {"organization_id": agent.organization_id, "user_id": scope.user_id},
        )

    def _owner_scope(
        self, scope: RuntimeScope, agent: RuntimeAgent, required_keys: tuple[str, ...]
    ) -> MemoryScope:
        if set(required_keys) != {"organization_id", "user_id"}:
            raise ValueError(f"unsupported runtime scope keys {required_keys!r}")
        return self._memory_scope(scope, agent)

    @staticmethod
    def _resolution_components(
        agent: RuntimeAgent,
        grants: tuple[RuntimeSchemaGrant, ...],
        config: RuntimeResolutionConfig | None,
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
        return PreferenceCatalog(tuple(definitions)), ResolutionPolicyRegistry(
            domain_policies=(
                DomainAccessPolicy(agent.domain_id, readable_domains, writable_domains),
            ),
            policies=policies,
            default_policy=default_policy,
            version=config.version if config else "runtime-default-v1",
        )
