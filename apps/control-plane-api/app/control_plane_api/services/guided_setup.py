from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_api.api.admin.models import (
    AccessRequestCreate,
    AgentCreate,
    DomainCreate,
    DynamicMemoryPolicyCreate,
    GuidedCustomPreference,
    GuidedMemorySetupActivation,
    GuidedMemorySetupPreview,
    GuidedMemorySetupRequest,
    OrganizationCreate,
    PreferenceCreate,
    ProjectCreate,
    ResolutionPolicyCreate,
    ResourceUpdate,
    SchemaCreate,
    ScopeCreate,
)
from control_plane_api.domain.control_plane import AccessRequestStatus
from control_plane_api.domain.governance import check_retention, retention_tier
from control_plane_api.domain.memory import MemoryProfileSchema
from control_plane_api.persistence.models import (
    MemoryDomainRecord,
    OrganizationRecord,
    PreferenceDefinitionRecord,
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
    ProjectRecord,
    RegisteredAgentRecord,
    SchemaPreferenceMappingRecord,
    ScopeDefinitionRecord,
)
from control_plane_api.repositories import MemoryStore
from control_plane_api.security.admin import AdminPrincipal
from control_plane_api.services.admin_service import AdminControlPlaneService, ResourceConflictError
from control_plane_api.services.vertex_provisioning import VertexContextProvisioner

SCOPE_KEYS = {
    "USER": ["organization_id", "user_id"],
    "HOUSEHOLD": ["organization_id", "household_id"],
    "USER_STORE": ["organization_id", "user_id", "store_id"],
}


class GuidedMemorySetupService:
    """Compile business selections and activate one governed memory setup atomically."""

    def __init__(
        self,
        session: AsyncSession,
        store: MemoryStore,
        provisioner: VertexContextProvisioner | None = None,
    ) -> None:
        self.session = session
        self.store = store
        self.provisioner = provisioner
        self.admin = AdminControlPlaneService(session)

    async def preview(
        self, principal: AdminPrincipal, request: GuidedMemorySetupRequest
    ) -> GuidedMemorySetupPreview:
        self.admin.authorizer.require_platform(principal)
        contract, summary, warnings = await self._compile(request)
        return GuidedMemorySetupPreview(
            summary=summary,
            generatedContract=contract,
            generatedYaml=yaml.safe_dump(contract, sort_keys=False),
            warnings=warnings,
        )

    async def activate(
        self, principal: AdminPrincipal, request: GuidedMemorySetupRequest
    ) -> GuidedMemorySetupActivation:
        self.admin.authorizer.require_platform(principal)
        preview = await self.preview(principal, request)
        domain = request.use_case.domain
        policy_id = f"{domain}:guided-policy:1"
        dynamic_id = f"{domain}:guided-dynamic:1"

        organization_id = request.use_case.organization_id
        project_id = request.use_case.project_id
        organization = await self.session.get(OrganizationRecord, organization_id)
        if organization is None:
            await self.admin.create_resource(
                principal,
                "organizations",
                OrganizationCreate(
                    id=organization_id,
                    name=organization_id.replace("-", " ").title(),
                    description=f"Organization for {request.use_case.name}",
                ),
            )
            # Organizations are created ACTIVE (create_resource), so they need no lifecycle
            # transition — activating an already-active org is an invalid transition.

        project = await self.session.get(ProjectRecord, project_id)
        if project is None:
            await self.admin.create_resource(
                principal,
                "projects",
                ProjectCreate(
                    id=project_id,
                    organizationId=organization_id,
                    name=project_id.replace("-", " ").title(),
                    description=request.use_case.description,
                    ownerTeam=request.use_case.owning_team,
                ),
            )
            await self._activate_resource(principal, "projects", project_id)
        elif project.organization_id != organization_id:
            raise ResourceConflictError(
                f"project {project_id!r} does not belong to organization {organization_id!r}"
            )

        if not await self.session.get(MemoryDomainRecord, domain):
            await self.admin.create_resource(
                principal,
                "domains",
                DomainCreate(
                    id=domain,
                    organizationId=organization_id,
                    projectId=project_id,
                    name=request.use_case.name,
                    description=request.use_case.description,
                    ownerTeam=request.use_case.owning_team,
                    contractVersion="1.0",
                ),
            )
            await self._activate_resource(principal, "domains", domain)

        for item in request.custom_preferences:
            if not item.attribute_id.startswith(f"{domain}."):
                raise ValueError(
                    "custom preference attribute IDs must use the selected domain prefix"
                )
            if not await self.session.get(PreferenceDefinitionRecord, item.attribute_id):
                await self.admin.create_resource(
                    principal,
                    "preference-catalog",
                    PreferenceCreate(
                        attributeId=item.attribute_id,
                        displayName=item.display_name,
                        description=item.description,
                        dataType=item.data_type,
                        allowedValues=item.allowed_values,
                        sensitivityClassification=self._custom_sensitivity(item),
                        canonicalOwnerId=domain,
                        validationRules={
                            "recommended_domains": [domain],
                            "confirmation_required_for_long_term": (
                                request.memory.confirmation_required
                            ),
                            **({"health": True} if item.health else {}),
                        },
                        defaultResolutionBehavior={"policy": policy_id},
                    ),
                )

        owned_specs = [
            item for item in await self._preference_specs(request) if item["owner"] == domain
        ]
        tiers = self._tiers(request, owned_specs)
        tier_results: list[tuple[dict[str, Any], str, set[str]]] = []
        for tier in tiers:
            version, fields = await self._provision_tier(principal, request, tier)
            tier_results.append((tier, version, fields))
        owned_schema_ids = [tier["schema_id"] for tier in tiers]

        agent = await self.session.get(RegisteredAgentRecord, request.agent.id)
        if request.agent.existing:
            if agent is None:
                raise ValueError(f"selected agent {request.agent.id!r} does not exist")
            if (
                agent.domain_id != domain
                or agent.organization_id != organization_id
                or agent.project_id != project_id
            ):
                raise ValueError(
                    "selected existing agent must belong to the use-case organization, project, "
                    "and primary domain"
                )
        elif agent is not None:
            raise ResourceConflictError(f"agent {request.agent.id!r} already exists")
        else:
            await self.admin.create_resource(
                principal,
                "agents",
                AgentCreate(
                    id=request.agent.id,
                    displayName=request.agent.display_name,
                    organizationId=organization_id,
                    projectId=project_id,
                    domainId=domain,
                    runtimeType=request.agent.runtime_type,
                    identityType=request.agent.identity_type,
                    principal=request.agent.principal,
                    capabilities={
                        "resolve_context": True,
                        "submit_candidates": bool(owned_schema_ids)
                        and request.agent.owned_schema_permission != "READ",
                        "inspect_provenance": True,
                        "administer_memory": False,
                    },
                ),
            )
            await self._activate_resource(principal, "agents", request.agent.id)

        for owned_schema_id in owned_schema_ids:
            owned_request = await self.admin.create_access_request(
                principal,
                AccessRequestCreate(
                    requestingAgentId=request.agent.id,
                    requestingTeam=request.use_case.owning_team,
                    targetSchemaId=owned_schema_id,
                    requestedPermission=request.agent.owned_schema_permission,
                    businessReason=f"Owned schema access for {request.use_case.name}",
                ),
            )
            await self.admin.decide_access_request(
                principal,
                str(owned_request["id"]),
                AccessRequestStatus.APPROVED,
                reason="Automatically approved for the owning domain",
            )

        pending = []
        for shared in request.shared_schemas:
            # Share only the attributes ticked in the wizard; none ticked = the whole schema.
            ticked = sorted(
                set(request.selected_preferences)
                & await self.admin.active_schema_attributes(shared.schema_id)
            )
            shared_request = await self.admin.create_access_request(
                principal,
                AccessRequestCreate(
                    requestingAgentId=request.agent.id,
                    requestingTeam=request.use_case.owning_team,
                    targetSchemaId=shared.schema_id,
                    requestedPermission=shared.permission,
                    attributes=ticked or None,
                    businessReason=f"Shared schema requested by {request.use_case.name}",
                ),
            )
            pending.append(str(shared_request["id"]))

        schema_precedence = [*owned_schema_ids, *[item.schema_id for item in request.shared_schemas]]
        if len(schema_precedence) > 1:
            chosen = request.resolution.schema_precedence if request.resolution else []
            if chosen:
                if len(chosen) != len(set(chosen)) or set(chosen) != set(schema_precedence):
                    raise ValueError(
                        "resolution precedence must contain every available schema once"
                    )
                schema_precedence = chosen
            await self.admin.create_resource(
                principal,
                "resolution-policies",
                ResolutionPolicyCreate(
                    id=policy_id,
                    agentId=request.agent.id,
                    name=f"{request.use_case.name} generated resolution policy",
                    version="1",
                    defaultRules={
                        "source_priority": [
                            "SESSION_OVERRIDE",
                            "EXPLICIT_PROFILE",
                            "MEMORY_PROFILE",
                            "DOMAIN_MEMORY",
                            "DYNAMIC_MEMORY",
                            "INFERRED_MEMORY",
                            "DEFAULT",
                        ],
                        "strategies": [
                            "SOURCE_PRIORITY",
                            "DOMAIN_PRIORITY",
                            "EXPLICIT_OVER_INFERRED",
                            "MOST_RECENT",
                            "HIGHEST_CONFIDENCE",
                        ],
                        "minimum_confidence": request.memory.confidence_threshold,
                    },
                    schemaPriorities=[
                        {"schemaId": item, "priority": index}
                        for index, item in enumerate(schema_precedence)
                    ],
                    attributeOverrides=(
                        request.resolution.attribute_overrides if request.resolution else []
                    ),
                ),
            )
            await self._activate_resource(principal, "resolution-policies", policy_id)

        if request.memory.dynamic_enabled:
            await self.admin.create_resource(
                principal,
                "dynamic-memory-policies",
                DynamicMemoryPolicyCreate(
                    id=dynamic_id,
                    level="DOMAIN",
                    domainId=domain,
                    enabled=True,
                    confidenceThreshold=request.memory.confidence_threshold,
                    memoryTopics=request.memory.memory_topics,
                    topicDefinitions=request.memory.topic_definitions,
                    retentionPolicy={"retention_days": request.memory.retention_days},
                    confirmationRequired=request.memory.confirmation_required,
                    version="1",
                ),
            )
            await self._activate_resource(principal, "dynamic-memory-policies", dynamic_id)

        for tier, version, fields in tier_results:
            await self.store.register_schema(
                MemoryProfileSchema(
                    id=tier["schema_id"],
                    domain=domain,
                    version=version,
                    fields=frozenset(fields),
                )
            )
        primary_schema_id = owned_schema_ids[0] if owned_schema_ids else None
        primary_scope_id = tiers[0]["scope_id"] if tiers else None
        await self.admin._audit(
            principal,
            "memory_setup.activated",
            "memory_setup",
            primary_schema_id or domain,
            None,
            {
                "environment": request.use_case.environment,
                "pending_approvals": pending,
                "profiles_created": 0,
            },
        )
        provisioning = (
            await self.provisioner.provision(self.session)
            if self.provisioner
            else {
                "status": "REGISTERED_LOCAL",
                "backend": type(self.store).__name__,
                "profileInstancesCreated": 0,
                "message": "Schema registered with the local runtime backend; user profiles remain lazy.",
            }
        )
        return GuidedMemorySetupActivation(
            **preview.model_dump(by_alias=True),
            status="ACTIVE_WITH_PENDING_ACCESS" if pending else "ACTIVE",
            resources={
                "organizationId": organization_id,
                "projectId": project_id,
                "domainId": domain,
                "scopeId": primary_scope_id,
                "scopeIds": [tier["scope_id"] for tier in tiers],
                "schemaId": primary_schema_id,
                "schemaIds": owned_schema_ids,
                "agentId": request.agent.id,
                "resolutionPolicyId": policy_id if len(schema_precedence) > 1 else None,
                "dynamicPolicyId": dynamic_id if request.memory.dynamic_enabled else None,
            },
            pendingApprovals=pending,
            provisioning=provisioning,
        )

    async def _compile(
        self, request: GuidedMemorySetupRequest
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        preferences = await self._preference_specs(request)
        owned = [item for item in preferences if item["owner"] == request.use_case.domain]
        if not owned:
            # Consumer-only: no preferences of its own, only approved access to other schemas.
            if not request.shared_schemas:
                raise ValueError(
                    "select or create at least one preference owned by the use-case domain, "
                    "or request shared schemas for a consumer-only agent"
                )
            if request.memory.dynamic_enabled:
                raise ValueError(
                    "a consumer-only agent keeps no memory of its own; disable dynamic memory"
                )
        for shared in request.shared_schemas:
            if shared.permission != "READ" and not set(request.selected_preferences) & (
                await self.admin.active_schema_attributes(shared.schema_id)
            ):
                raise ValueError(
                    f"write access to {shared.schema_id} needs at least one of its preferences "
                    "ticked; only ticked preferences can be written"
                )
        tiers = self._tiers(request, owned)
        for tier in tiers:
            check_retention(
                request.memory.profile_retention_days,
                retention_tier(
                    (item["sensitivity"] for item in tier["specs"]),
                    health=any(item["health"] for item in tier["specs"]),
                ),
                schema_id=tier["schema_id"],
            )
        owned_schema_ids = [tier["schema_id"] for tier in tiers]
        available_schemas = [
            *owned_schema_ids,
            *[item.schema_id for item in request.shared_schemas],
        ]
        warnings = []
        external = [
            item["attributeId"] for item in preferences if item["owner"] != request.use_case.domain
        ]
        if external:
            warnings.append(
                "Externally owned preferences are consumed through shared schema access, not copied "
                f"into the new schema: {', '.join(external)}"
            )
        if request.shared_schemas:
            warnings.append(
                "Shared schema access remains pending until the target schema owner approves it."
            )
        schemas_contract = [
            {
                "id": tier["schema_id"],
                "scope": {"type": tier["scope_type"], "keys": tier["scope_keys"]},
                "preferences": {
                    item["attributeId"]: {
                        "type": item["dataType"],
                        **(
                            {"allowedValues": item["allowedValues"]}
                            if item["allowedValues"]
                            else {}
                        ),
                    }
                    for item in tier["specs"]
                },
            }
            for tier in tiers
        ]
        contract = {
            "apiVersion": "memory.platform/v1alpha1",
            "kind": "GuidedMemorySetup",
            "metadata": {
                "name": request.use_case.name,
                "environment": request.use_case.environment,
                "generatedAt": datetime.now(UTC).isoformat(),
            },
            "organization": {"id": request.use_case.organization_id},
            "project": {
                "id": request.use_case.project_id,
                "organizationId": request.use_case.organization_id,
            },
            "domain": {
                "id": request.use_case.domain,
                "description": request.use_case.description,
                "owningTeam": request.use_case.owning_team,
            },
            "schema": schemas_contract[0] if schemas_contract else None,
            "schemas": schemas_contract,
            "dynamicMemory": request.memory.model_dump(by_alias=True),
            "agent": {
                "id": request.agent.id,
                "schemaAccess": {
                    **{
                        schema_id: request.agent.owned_schema_permission
                        for schema_id in owned_schema_ids
                    },
                    **{item.schema_id: item.permission for item in request.shared_schemas},
                },
            },
            **(
                {
                    "resolution": {
                        "defaultPrecedence": (
                            request.resolution.schema_precedence
                            if request.resolution and request.resolution.schema_precedence
                            else available_schemas
                        ),
                        "attributeOverrides": (
                            [
                                item.model_dump(by_alias=True)
                                for item in request.resolution.attribute_overrides
                            ]
                            if request.resolution
                            else []
                        ),
                    }
                }
                if len(available_schemas) > 1
                else {}
            ),
        }
        summary = {
            "useCase": request.use_case.name,
            "organization": request.use_case.organization_id,
            "project": request.use_case.project_id,
            "domain": request.use_case.domain,
            "environment": request.use_case.environment,
            "ownedPreferenceCount": len(owned),
            "consumerOnly": not owned,
            "scope": request.scope.type,
            "agent": request.agent.id,
            "sharedSchemaCount": len(request.shared_schemas),
            "requiresResolution": len(available_schemas) > 1,
            "profileInstancesCreated": 0,
        }
        return contract, summary, warnings

    def _scope_keys(self, request: GuidedMemorySetupRequest) -> list[str]:
        if request.scope.type == "CUSTOM":
            keys = list(dict.fromkeys(request.scope.custom_keys))
            if not keys:
                raise ValueError("custom scope requires at least one key")
            for required in ("organization_id",):
                if required not in keys:
                    keys.append(required)
            return keys
        return list(SCOPE_KEYS[request.scope.type])

    @staticmethod
    def _custom_sensitivity(item: GuidedCustomPreference) -> str:
        """Health data is at least sensitive."""
        return "sensitive" if item.health and item.sensitivity == "normal" else item.sensitivity

    def _level_map(self, request: GuidedMemorySetupRequest) -> dict[str, str]:
        levels: dict[str, str] = {
            item.attribute_id: item.level for item in request.custom_preferences
        }
        levels.update(request.preference_levels)
        return levels

    def _tiers(
        self, request: GuidedMemorySetupRequest, owned_specs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """The schema tiers to provision for this setup.

        Every mode except HOUSEHOLD_MEMBERS produces a single tier. HOUSEHOLD_MEMBERS splits the
        owned preferences into a household-shared schema ({org, household_id}) and a per-member
        schema ({org, household_id, member_id}) by each preference's level.
        """
        domain = request.use_case.domain
        if not owned_specs:
            return []  # consumer-only: nothing of its own to provision
        if request.scope.type == "HOUSEHOLD_MEMBERS":
            levels = self._level_map(request)
            groups = {
                "household": (
                    f"{domain}-household-preferences-v1",
                    f"{domain}:household-scope",
                    "HOUSEHOLD_PROFILE",
                    ["organization_id", "household_id"],
                ),
                "member": (
                    f"{domain}-member-preferences-v1",
                    f"{domain}:household-member-scope",
                    "HOUSEHOLD_MEMBER_PROFILE",
                    ["organization_id", "household_id", "member_id"],
                ),
            }
            tiers: list[dict[str, Any]] = []
            for level, (schema_id, scope_id, scope_type, scope_keys) in groups.items():
                specs = [
                    item
                    for item in owned_specs
                    if levels.get(item["attributeId"], "household") == level
                ]
                if specs:
                    tiers.append(
                        {
                            "schema_id": schema_id,
                            "scope_id": scope_id,
                            "scope_type": scope_type,
                            "scope_keys": scope_keys,
                            "specs": specs,
                        }
                    )
            if not tiers:
                raise ValueError("household setup requires at least one preference")
            return tiers
        return [
            {
                "schema_id": f"{domain}-preferences-v1",
                "scope_id": f"{domain}:profile-scope",
                "scope_type": f"{request.scope.type}_PROFILE",
                "scope_keys": self._scope_keys(request),
                "specs": owned_specs,
            }
        ]

    async def _provision_tier(
        self,
        principal: AdminPrincipal,
        request: GuidedMemorySetupRequest,
        tier: dict[str, Any],
    ) -> tuple[str, set[str]]:
        """Create (or validate) one tier's scope and schema; return its version and profile fields."""
        domain = request.use_case.domain
        scope_id = tier["scope_id"]
        scope_keys = tier["scope_keys"]
        existing_scope = await self.session.get(ScopeDefinitionRecord, scope_id)
        if existing_scope is None:
            await self.admin.create_resource(
                principal,
                "scopes",
                ScopeCreate(
                    id=scope_id,
                    scopeType=tier["scope_type"],
                    scopeKeys=scope_keys,
                    description=f"Generated scope for {request.use_case.name}",
                    ownerDomainId=domain,
                ),
            )
            await self._activate_resource(principal, "scopes", scope_id)
        elif existing_scope.status != "ACTIVE" or list(existing_scope.scope_keys) != scope_keys:
            raise ResourceConflictError(
                f"existing scope {scope_id!r} is not active with the requested keys"
            )

        schema_id = tier["schema_id"]
        owned_preferences = tier["specs"]
        properties = {
            item["attributeId"].rsplit(".", 1)[-1]: (
                {
                    "type": "array",
                    "description": item["description"],
                    "items": {
                        "type": "string",
                        **({"enum": item["allowedValues"]} if item["allowedValues"] else {}),
                    },
                }
                if item["dataType"] == "list"
                else {
                    "type": self._json_type(item["dataType"]),
                    "description": item["description"],
                    **({"enum": item["allowedValues"]} if item["allowedValues"] else {}),
                }
            )
            for item in owned_preferences
        }
        schema_fields = set(properties)
        schema_version = "1"
        existing_schema = await self.session.get(ProfileSchemaRecord, schema_id)
        if existing_schema is None:
            await self.admin.create_resource(
                principal,
                "schemas",
                SchemaCreate(
                    id=schema_id,
                    domainId=domain,
                    displayName=f"{request.use_case.name} Preferences",
                    description=request.use_case.description,
                    ownerTeam=request.use_case.owning_team,
                    version="1",
                    scopeDefinitionId=scope_id,
                    vertexSchemaDefinition={
                        "type": "object",
                        "properties": properties,
                        "additionalProperties": False,
                    },
                    generationConfig={
                        "enabled": request.memory.canonical,
                        "inferredFieldsAllowed": request.memory.dynamic_enabled,
                        "requireUserConfirmation": (
                            list(properties) if request.memory.confirmation_required else []
                        ),
                    },
                    mappings=[
                        {
                            "attributeId": item["attributeId"],
                            "profileField": item["attributeId"].rsplit(".", 1)[-1],
                        }
                        for item in owned_preferences
                    ],
                    retentionDays=request.memory.profile_retention_days,
                ),
            )
            await self._activate_resource(principal, "schemas", schema_id)
        else:
            if existing_schema.domain_id != domain or existing_schema.status != "ACTIVE":
                raise ResourceConflictError(
                    f"existing schema {schema_id!r} is not active and owned by {domain!r}"
                )
            active_version = await self.session.scalar(
                select(ProfileSchemaVersionRecord).where(
                    ProfileSchemaVersionRecord.schema_id == schema_id,
                    ProfileSchemaVersionRecord.status == "ACTIVE",
                )
            )
            if active_version is None:
                raise ResourceConflictError(f"existing schema {schema_id!r} has no active version")
            schema_version = active_version.version
            mappings = list(
                (
                    await self.session.scalars(
                        select(SchemaPreferenceMappingRecord).where(
                            SchemaPreferenceMappingRecord.schema_version_id == active_version.id,
                        )
                    )
                ).all()
            )
            existing_attributes = {item.attribute_id for item in mappings}
            requested_attributes = {item["attributeId"] for item in owned_preferences}
            missing_attributes = requested_attributes.difference(existing_attributes)
            if missing_attributes:
                raise ResourceConflictError(
                    "active schema requires a reviewed new version before adding attributes: "
                    f"{sorted(missing_attributes)}"
                )
            schema_fields = {item.profile_field for item in mappings}
        return schema_version, schema_fields

    async def _preference_specs(self, request: GuidedMemorySetupRequest) -> list[dict[str, Any]]:
        custom = {item.attribute_id: item for item in request.custom_preferences}
        ids = list(dict.fromkeys([*request.selected_preferences, *custom]))
        rows = []
        if ids:
            rows = list(
                (
                    await self.session.scalars(
                        select(PreferenceDefinitionRecord).where(
                            PreferenceDefinitionRecord.attribute_id.in_(ids)
                        )
                    )
                ).all()
            )
        found = {item.attribute_id for item in rows}
        unresolved = set(request.selected_preferences).difference(found).difference(custom)
        if unresolved:
            raise ValueError(f"unknown preference attributes: {sorted(unresolved)}")
        specs = {
            item.attribute_id: {
                "attributeId": item.attribute_id,
                "displayName": item.display_name,
                "description": item.description,
                "dataType": item.data_type,
                "allowedValues": list(item.allowed_values),
                "owner": item.canonical_owner_id,
                "sensitivity": item.sensitivity_classification,
                "health": bool((item.validation_rules or {}).get("health")),
            }
            for item in rows
        }
        specs.update(
            {
                item.attribute_id: {
                    "attributeId": item.attribute_id,
                    "displayName": item.display_name,
                    "description": item.description,
                    "dataType": item.data_type,
                    "allowedValues": list(item.allowed_values),
                    "owner": request.use_case.domain,
                    "sensitivity": self._custom_sensitivity(item),
                    "health": item.health,
                }
                for item in request.custom_preferences
            }
        )
        return [specs[item] for item in ids if item in specs]

    async def _activate_resource(
        self, principal: AdminPrincipal, resource: str, resource_id: str
    ) -> None:
        for status in ("PENDING_APPROVAL", "APPROVED", "ACTIVE"):
            await self.admin.update_resource(
                principal, resource, resource_id, ResourceUpdate(status=status)
            )

    @staticmethod
    def _json_type(value: str) -> str:
        return {"integer": "integer", "number": "number", "boolean": "boolean"}.get(value, "string")
