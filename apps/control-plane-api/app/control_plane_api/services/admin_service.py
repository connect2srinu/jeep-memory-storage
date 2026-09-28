from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_api.api.admin.models import (
    AccessRequestCreate,
    AgentCreate,
    AgentRuntimeBindingUpdate,
    DomainCreate,
    DynamicMemoryPolicyCreate,
    MembershipCreate,
    OrganizationCreate,
    OrganizationSettingsUpdate,
    PreferenceCreate,
    ProjectCreate,
    ProjectSettingsUpdate,
    ResolutionPolicyCreate,
    ResourceUpdate,
    SchemaCreate,
    SchemaVersionChange,
    ScopeCreate,
)
from control_plane_api.domain import AccessPermission, AccessRequestStatus, LifecycleStatus
from control_plane_api.domain.governance import (
    RESTRICTED_PURPOSE,
    check_retention,
    retention_tier,
)
from control_plane_api.domain.household_identity import member_kind_for, normalize_name
from control_plane_api.integrations.agent_health import AgentHealthProvider
from control_plane_api.observability.runtime import correlation_id_context
from control_plane_api.persistence.models import (
    AccessRequestRecord,
    AgentHealthSnapshotRecord,
    AgentRuntimeBindingRecord,
    AgentSchemaGrantRecord,
    AuditEventRecord,
    ConsentRecord,
    DynamicMemoryPolicyRecord,
    HouseholdMemberAliasRecord,
    HouseholdMemberRecord,
    MemoryDomainRecord,
    OrganizationMembershipRecord,
    OrganizationRecord,
    OrganizationSettingsRecord,
    PreferenceDefinitionRecord,
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
    ProjectMembershipRecord,
    ProjectRecord,
    ProjectSettingsRecord,
    RegisteredAgentRecord,
    ResolutionAttributeOverrideRecord,
    ResolutionPolicyRecord,
    ResolutionPolicySchemaPriorityRecord,
    ResourceChangeRequestRecord,
    SchemaPreferenceMappingRecord,
    ScopeDefinitionRecord,
)
from control_plane_api.security.admin import AdminAuthorizer, AdminPrincipal, AdminRole


class ResourceNotFoundError(LookupError):
    pass


class ResourceConflictError(RuntimeError):
    pass


RESOURCE_MODELS = {
    "organizations": OrganizationRecord,
    "projects": ProjectRecord,
    "domains": MemoryDomainRecord,
    "scopes": ScopeDefinitionRecord,
    "schemas": ProfileSchemaRecord,
    "preference-catalog": PreferenceDefinitionRecord,
    "agents": RegisteredAgentRecord,
    "resolution-policies": ResolutionPolicyRecord,
    "dynamic-memory-policies": DynamicMemoryPolicyRecord,
}

RESOURCE_IDS = {
    "organizations": "id",
    "projects": "id",
    "domains": "id",
    "scopes": "id",
    "schemas": "id",
    "preference-catalog": "attribute_id",
    "agents": "id",
    "resolution-policies": "id",
    "dynamic-memory-policies": "id",
}

UPDATABLE_FIELDS = {
    "organizations": {"name", "description", "owner_contact"},
    "projects": {"name", "description", "owner_team"},
    "domains": {"name", "description", "owner_team", "owner_contact", "contract_version"},
    "scopes": {"scope_type", "scope_keys", "description"},
    "schemas": {"display_name", "description", "owner_team"},
    "preference-catalog": {
        "display_name",
        "description",
        "allowed_values",
        "validation_rules",
        "default_resolution_behavior",
        "catalog_version",
    },
    "agents": {"display_name", "runtime_type", "identity_type", "principal", "capabilities"},
    "resolution-policies": {
        "name",
        "default_rules",
        "schema_priorities",
        "attribute_overrides",
    },
    "dynamic-memory-policies": {
        "enabled",
        "confidence_threshold",
        "memory_topics",
        "topic_definitions",
        "retention_policy",
        "confirmation_required",
        "allowed_dynamic_categories",
    },
}

LIFECYCLE_TRANSITIONS = {
    LifecycleStatus.DRAFT: {LifecycleStatus.PENDING_APPROVAL, LifecycleStatus.RETIRED},
    LifecycleStatus.PENDING_APPROVAL: {LifecycleStatus.APPROVED, LifecycleStatus.DRAFT},
    LifecycleStatus.APPROVED: {LifecycleStatus.ACTIVE, LifecycleStatus.RETIRED},
    LifecycleStatus.ACTIVE: {LifecycleStatus.DEPRECATED},
    LifecycleStatus.DEPRECATED: {LifecycleStatus.RETIRED, LifecycleStatus.ACTIVE},
    LifecycleStatus.RETIRED: set(),
}

CHANGE_ALIASES = {
    "organizationId": "organization_id",
    "projectId": "project_id",
    "ownerTeam": "owner_team",
    "ownerContact": "owner_contact",
    "contractVersion": "contract_version",
    "scopeType": "scope_type",
    "scopeKeys": "scope_keys",
    "displayName": "display_name",
    "allowedValues": "allowed_values",
    "validationRules": "validation_rules",
    "defaultResolutionBehavior": "default_resolution_behavior",
    "catalogVersion": "catalog_version",
    "runtimeType": "runtime_type",
    "identityType": "identity_type",
    "defaultRules": "default_rules",
    "schemaPriorities": "schema_priorities",
    "attributeOverrides": "attribute_overrides",
    "confidenceThreshold": "confidence_threshold",
    "memoryTopics": "memory_topics",
    "topicDefinitions": "topic_definitions",
    "retentionPolicy": "retention_policy",
    "confirmationRequired": "confirmation_required",
    "allowedDynamicCategories": "allowed_dynamic_categories",
}


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _record_data(record: Any) -> dict[str, Any]:
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def _audit_metadata(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None

    def json_value(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_value(item) for item in value]
        return value

    return {key: json_value(value) for key, value in data.items()}


class AdminControlPlaneService:
    def __init__(
        self, session: AsyncSession, health_provider: AgentHealthProvider | None = None
    ) -> None:
        self.session = session
        self.authorizer = AdminAuthorizer()
        self.health_provider = health_provider or AgentHealthProvider()

    async def _audit(
        self,
        principal: AdminPrincipal,
        action: str,
        target_type: str,
        target_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        self.session.add(
            AuditEventRecord(
                id=str(uuid4()),
                actor=principal.principal,
                action=action,
                target_type=target_type,
                target_id=target_id,
                correlation_id=correlation_id_context.get() or str(uuid4()),
                before_metadata=_audit_metadata(before),
                after_metadata=_audit_metadata(after),
            )
        )

    async def _get(self, resource: str, resource_id: str) -> Any:
        model = RESOURCE_MODELS[resource]
        record = await self.session.get(model, resource_id)
        if record is None:
            raise ResourceNotFoundError(f"{resource} resource {resource_id} was not found")
        return record

    async def list_households(
        self, principal: AdminPrincipal, organization_id: str
    ) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        records = list(
            (
                await self.session.scalars(
                    select(HouseholdMemberRecord)
                    .where(HouseholdMemberRecord.organization_id == organization_id)
                    .order_by(
                        HouseholdMemberRecord.household_id, HouseholdMemberRecord.member_id
                    )
                )
            ).all()
        )
        households: dict[str, dict[str, Any]] = {}
        for record in records:
            summary = households.setdefault(
                record.household_id,
                {
                    "organization_id": organization_id,
                    "household_id": record.household_id,
                    "member_count": 0,
                    "guardian_count": 0,
                },
            )
            if record.status == "active":
                summary["member_count"] += 1
                if record.is_guardian:
                    summary["guardian_count"] += 1
        return list(households.values())

    async def list_household_members(
        self, principal: AdminPrincipal, organization_id: str, household_id: str
    ) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        records = await self.session.scalars(
            select(HouseholdMemberRecord)
            .where(
                HouseholdMemberRecord.organization_id == organization_id,
                HouseholdMemberRecord.household_id == household_id,
            )
            .order_by(HouseholdMemberRecord.member_id)
        )
        aliases: dict[str, list[str]] = {}
        for alias in await self.session.scalars(
            select(HouseholdMemberAliasRecord)
            .where(
                HouseholdMemberAliasRecord.organization_id == organization_id,
                HouseholdMemberAliasRecord.household_id == household_id,
            )
            .order_by(HouseholdMemberAliasRecord.alias)
        ):
            aliases.setdefault(alias.member_id, []).append(alias.alias)
        return [
            {**_record_data(record), "aliases": aliases.get(record.member_id, [])}
            for record in records
        ]

    async def list_household_consents(
        self, principal: AdminPrincipal, organization_id: str, household_id: str
    ) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        records = await self.session.scalars(
            select(ConsentRecord)
            .where(
                ConsentRecord.organization_id == organization_id,
                ConsentRecord.household_id == household_id,
            )
            .order_by(ConsentRecord.requested_at.desc())
        )
        return [_record_data(record) for record in records]

    async def upsert_household_member(
        self,
        principal: AdminPrincipal,
        organization_id: str,
        household_id: str,
        member_id: str,
        *,
        display_name: str | None,
        relationship: str,
        has_login: bool,
        is_guardian: bool,
        minor: bool | None = None,
    ) -> dict[str, Any]:
        self.authorizer.require_platform(principal)
        if has_login:
            # One login = one household root: a member with a login signs in with its member id.
            other = await self.session.scalar(
                select(HouseholdMemberRecord).where(
                    HouseholdMemberRecord.organization_id == organization_id,
                    HouseholdMemberRecord.login_id == member_id,
                    HouseholdMemberRecord.household_id != household_id,
                )
            )
            if other is not None:
                raise ResourceConflictError(
                    f"login {member_id!r} already belongs to household {other.household_id!r}"
                )
        record = await self.session.get(
            HouseholdMemberRecord, (organization_id, household_id, member_id)
        )
        before = _record_data(record) if record is not None else None
        if record is None:
            record = HouseholdMemberRecord(
                organization_id=organization_id,
                household_id=household_id,
                member_id=member_id,
                confirmed_at=datetime.now(UTC),
            )
            self.session.add(record)
        member_kind, default_minor = member_kind_for(relationship, has_login=has_login)
        record.display_name = display_name
        record.normalized_name = normalize_name(display_name) if display_name else None
        record.relationship = relationship
        record.has_login = has_login
        record.is_guardian = is_guardian
        record.member_kind = member_kind
        record.minor = default_minor if minor is None or has_login else minor
        record.login_id = member_id if has_login else None
        record.provenance = "ADMIN"
        record.status = "active"
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal,
            "household_member.upserted",
            "household_member",
            f"{organization_id}:{household_id}:{member_id}",
            before,
            after,
        )
        return after

    async def deactivate_household_member(
        self,
        principal: AdminPrincipal,
        organization_id: str,
        household_id: str,
        member_id: str,
    ) -> dict[str, Any]:
        self.authorizer.require_platform(principal)
        record = await self.session.get(
            HouseholdMemberRecord, (organization_id, household_id, member_id)
        )
        if record is None:
            raise ResourceNotFoundError(
                f"household member {member_id} was not found in household {household_id}"
            )
        before = _record_data(record)
        record.status = "inactive"
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal,
            "household_member.deactivated",
            "household_member",
            f"{organization_id}:{household_id}:{member_id}",
            before,
            after,
        )
        return after

    async def _domain_for(self, resource: str, record: Any) -> str | None:
        if resource in {"organizations", "projects"}:
            return None
        if resource == "domains":
            return record.id
        if resource == "scopes":
            return record.owner_domain_id
        if resource == "schemas":
            return record.domain_id
        if resource == "preference-catalog":
            return record.canonical_owner_id
        if resource == "agents":
            return record.domain_id
        if resource == "resolution-policies":
            if not record.agent_id:
                return None
            agent = await self.session.get(RegisteredAgentRecord, record.agent_id)
            return agent.domain_id if agent else None
        if resource == "dynamic-memory-policies":
            if record.domain_id:
                return record.domain_id
            if record.schema_id:
                schema = await self.session.get(ProfileSchemaRecord, record.schema_id)
                return schema.domain_id if schema else None
        return None

    async def list_resources(
        self,
        principal: AdminPrincipal,
        resource: str,
        organization_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        model = RESOURCE_MODELS[resource]
        id_column = getattr(model, RESOURCE_IDS[resource])
        records = await self.session.scalars(select(model).order_by(id_column))
        items: list[dict[str, Any]] = []
        for record in records:
            owner_organization_id = await self._organization_for(resource, record)
            if (
                organization_id
                and resource in {"projects", "agents"}
                and owner_organization_id != organization_id
            ):
                continue
            data = _record_data(record)
            if organization_id and owner_organization_id:
                visibility = (
                    "OWNED"
                    if owner_organization_id == organization_id
                    else "PLATFORM"
                    if owner_organization_id == "default-org"
                    else "RESTRICTED"
                )
                data["owner_organization_id"] = owner_organization_id
                data["visibility"] = visibility
                data["editable"] = visibility == "OWNED"
                if resource == "schemas":
                    data["access_status"] = await self._schema_access_status(
                        organization_id, record.id
                    )
                if visibility == "RESTRICTED":
                    allowed = {
                        "id",
                        "attribute_id",
                        "domain_id",
                        "display_name",
                        "name",
                        "description",
                        "status",
                        "owner_organization_id",
                        "visibility",
                        "editable",
                        "access_status",
                        "created_at",
                        "updated_at",
                    }
                    data = {key: value for key, value in data.items() if key in allowed}
            items.append(data)
        return items

    async def _organization_for(self, resource: str, record: Any) -> str | None:
        if resource == "organizations":
            return record.id
        if resource == "projects":
            return record.organization_id
        domain_id = await self._domain_for(resource, record)
        if not domain_id:
            return None
        domain = await self.session.get(MemoryDomainRecord, domain_id)
        return domain.organization_id if domain else None

    async def _schema_access_status(self, organization_id: str, schema_id: str) -> str:
        agents = (
            await self.session.scalars(
                select(RegisteredAgentRecord.id).where(
                    RegisteredAgentRecord.organization_id == organization_id,
                    RegisteredAgentRecord.status == "ACTIVE",
                )
            )
        ).all()
        if not agents:
            return "NOT_REQUESTED"
        grant = await self.session.scalar(
            select(AgentSchemaGrantRecord).where(
                AgentSchemaGrantRecord.agent_id.in_(agents),
                AgentSchemaGrantRecord.schema_id == schema_id,
                AgentSchemaGrantRecord.status == "ACTIVE",
            )
        )
        if grant:
            return "APPROVED"
        pending = await self.session.scalar(
            select(AccessRequestRecord).where(
                AccessRequestRecord.requesting_agent_id.in_(agents),
                AccessRequestRecord.target_schema_id == schema_id,
                AccessRequestRecord.status == "PENDING",
            )
        )
        return "PENDING" if pending else "NOT_REQUESTED"

    async def get_resource(
        self, principal: AdminPrincipal, resource: str, resource_id: str
    ) -> dict[str, Any]:
        self.authorizer.require_read(principal)
        record = await self._get(resource, resource_id)
        if resource == "schemas":
            return await self._schema_data(record)
        if resource == "resolution-policies":
            return await self._resolution_policy_data(record)
        return _record_data(record)

    async def agent_schema_access(
        self, principal: AdminPrincipal, agent_id: str
    ) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        agent = await self.session.get(RegisteredAgentRecord, agent_id)
        if agent is None:
            raise ResourceNotFoundError(f"agent {agent_id} was not found")
        schemas = await self.list_resources(principal, "schemas", agent.organization_id)
        grants = {
            item.schema_id: item
            for item in (
                await self.session.scalars(
                    select(AgentSchemaGrantRecord).where(
                        AgentSchemaGrantRecord.agent_id == agent.id
                    )
                )
            ).all()
        }
        requests = (
            await self.session.scalars(
                select(AccessRequestRecord)
                .where(AccessRequestRecord.requesting_agent_id == agent.id)
                .order_by(AccessRequestRecord.requested_at.desc())
            )
        ).all()
        latest_requests: dict[str, AccessRequestRecord] = {}
        for request in requests:
            latest_requests.setdefault(request.target_schema_id, request)

        result: list[dict[str, Any]] = []
        for schema in schemas:
            schema_id = str(schema["id"])
            grant = grants.get(schema_id)
            request = latest_requests.get(schema_id)
            grant_active = grant is not None and grant.status == LifecycleStatus.ACTIVE.value
            access_status = (
                "APPROVED"
                if grant_active
                else request.status
                if request is not None
                else "NOT_REQUESTED"
            )
            result.append(
                {
                    **schema,
                    "agent_id": agent.id,
                    "permission": grant.permission if grant_active else None,
                    "access_status": access_status,
                    "request_id": request.id if request else None,
                    "requestable": access_status
                    not in {
                        AccessRequestStatus.PENDING.value,
                        AccessRequestStatus.APPROVED.value,
                    },
                }
            )
        return result

    async def _schema_data(self, record: ProfileSchemaRecord) -> dict[str, Any]:
        data = _record_data(record)
        versions = (
            await self.session.scalars(
                select(ProfileSchemaVersionRecord)
                .where(ProfileSchemaVersionRecord.schema_id == record.id)
                .order_by(ProfileSchemaVersionRecord.version)
            )
        ).all()
        details = []
        for version in versions:
            version_data = _record_data(version)
            mappings = (
                await self.session.scalars(
                    select(SchemaPreferenceMappingRecord)
                    .where(SchemaPreferenceMappingRecord.schema_version_id == version.id)
                    .order_by(SchemaPreferenceMappingRecord.profile_field)
                )
            ).all()
            version_data["mappings"] = [_record_data(mapping) for mapping in mappings]
            details.append(version_data)
        data["versions"] = details
        return data

    async def _resolution_policy_data(self, record: ResolutionPolicyRecord) -> dict[str, Any]:
        data = _record_data(record)
        priorities = (
            await self.session.scalars(
                select(ResolutionPolicySchemaPriorityRecord)
                .where(ResolutionPolicySchemaPriorityRecord.policy_id == record.id)
                .order_by(ResolutionPolicySchemaPriorityRecord.priority)
            )
        ).all()
        overrides = (
            await self.session.scalars(
                select(ResolutionAttributeOverrideRecord)
                .where(ResolutionAttributeOverrideRecord.policy_id == record.id)
                .order_by(ResolutionAttributeOverrideRecord.attribute_id)
            )
        ).all()
        data["schema_priorities"] = [_record_data(item) for item in priorities]
        data["attribute_overrides"] = [_record_data(item) for item in overrides]
        return data

    async def schema_agent_access(
        self, principal: AdminPrincipal, schema_id: str
    ) -> list[dict[str, Any]]:
        """Which agents can access a schema, and how they qualify for that access.

        Access is explicit-grant-only: an agent in the schema's owning project is
        eligible but is not granted access until an explicit grant exists.
        """
        self.authorizer.require_read(principal)
        schema = await self.session.get(ProfileSchemaRecord, schema_id)
        if schema is None:
            raise ResourceNotFoundError(f"schema {schema_id} was not found")
        domain = await self.session.get(MemoryDomainRecord, schema.domain_id)
        schema_project_id = domain.project_id if domain else None
        schema_organization_id = domain.organization_id if domain else None

        agents = (
            (
                await self.session.scalars(
                    select(RegisteredAgentRecord)
                    .where(
                        RegisteredAgentRecord.organization_id == schema_organization_id,
                        RegisteredAgentRecord.status == "ACTIVE",
                    )
                    .order_by(RegisteredAgentRecord.display_name)
                )
            ).all()
            if schema_organization_id
            else []
        )
        grants = {
            item.agent_id: item
            for item in (
                await self.session.scalars(
                    select(AgentSchemaGrantRecord).where(
                        AgentSchemaGrantRecord.schema_id == schema_id
                    )
                )
            ).all()
        }
        requests = (
            await self.session.scalars(
                select(AccessRequestRecord)
                .where(AccessRequestRecord.target_schema_id == schema_id)
                .order_by(AccessRequestRecord.requested_at.desc())
            )
        ).all()
        latest_requests: dict[str, AccessRequestRecord] = {}
        for request in requests:
            latest_requests.setdefault(request.requesting_agent_id, request)

        result: list[dict[str, Any]] = []
        for agent in agents:
            grant = grants.get(agent.id)
            request = latest_requests.get(agent.id)
            grant_active = grant is not None and grant.status == LifecycleStatus.ACTIVE.value
            same_project = schema_project_id is not None and agent.project_id == schema_project_id
            request_status = (
                request.status if request is not None else AccessRequestStatus.PENDING.value
            )
            if grant_active:
                access_kind = "OWNING_PROJECT_GRANT" if same_project else "CROSS_PROJECT_GRANT"
                access_status = "APPROVED"
            elif request is not None and request.status == AccessRequestStatus.PENDING.value:
                access_kind = "REQUEST_PENDING"
                access_status = "PENDING"
            elif same_project:
                access_kind = "ELIGIBLE_NOT_GRANTED"
                access_status = request_status if request is not None else "NOT_REQUESTED"
            else:
                access_kind = "NONE"
                access_status = request_status if request is not None else "NOT_REQUESTED"
            result.append(
                {
                    "agent_id": agent.id,
                    "display_name": agent.display_name,
                    "project_id": agent.project_id,
                    "domain_id": agent.domain_id,
                    "same_project": same_project,
                    "permission": grant.permission if grant_active else None,
                    "access_kind": access_kind,
                    "access_status": access_status,
                    "request_id": request.id if request is not None else None,
                    "requested_permission": (
                        request.requested_permission if request is not None else None
                    ),
                }
            )
        return result

    async def domain_detail(self, principal: AdminPrincipal, domain_id: str) -> dict[str, Any]:
        """Aggregate everything associated with a domain for its detail page."""
        self.authorizer.require_read(principal)
        domain = await self.session.get(MemoryDomainRecord, domain_id)
        if domain is None:
            raise ResourceNotFoundError(f"domain {domain_id} was not found")
        organization = await self.session.get(OrganizationRecord, domain.organization_id)
        project = await self.session.get(ProjectRecord, domain.project_id)

        scopes = (
            await self.session.scalars(
                select(ScopeDefinitionRecord)
                .where(ScopeDefinitionRecord.owner_domain_id == domain_id)
                .order_by(ScopeDefinitionRecord.id)
            )
        ).all()

        schema_records = (
            await self.session.scalars(
                select(ProfileSchemaRecord)
                .where(ProfileSchemaRecord.domain_id == domain_id)
                .order_by(ProfileSchemaRecord.id)
            )
        ).all()
        schemas: list[dict[str, Any]] = []
        schema_ids: list[str] = []
        for schema in schema_records:
            schema_ids.append(schema.id)
            data = await self._schema_data(schema)
            data["access_status"] = await self._schema_access_status(
                domain.organization_id, schema.id
            )
            grant_count = await self.session.scalar(
                select(func.count())
                .select_from(AgentSchemaGrantRecord)
                .where(
                    AgentSchemaGrantRecord.schema_id == schema.id,
                    AgentSchemaGrantRecord.status == "ACTIVE",
                )
            )
            data["active_grant_count"] = int(grant_count or 0)
            schemas.append(data)

        home_agents = (
            await self.session.scalars(
                select(RegisteredAgentRecord)
                .where(RegisteredAgentRecord.domain_id == domain_id)
                .order_by(RegisteredAgentRecord.display_name)
            )
        ).all()
        home_agent_ids = [agent.id for agent in home_agents]

        policy_clauses = [ResolutionPolicyRecord.id.like(f"{domain_id}:%")]
        if home_agent_ids:
            policy_clauses.append(ResolutionPolicyRecord.agent_id.in_(home_agent_ids))
        policy_rows = (
            await self.session.scalars(
                select(ResolutionPolicyRecord).where(
                    ResolutionPolicyRecord.status == "ACTIVE",
                    or_(*policy_clauses),
                )
            )
        ).all()
        domain_default: dict[str, Any] | None = None
        agent_policies: list[dict[str, Any]] = []
        for policy in policy_rows:
            detail = await self._resolution_policy_data(policy)
            if policy.agent_id is None and policy.id.startswith(f"{domain_id}:"):
                domain_default = detail
            else:
                agent_policies.append(detail)

        pending_access = (
            (
                await self.session.scalars(
                    select(AccessRequestRecord)
                    .where(
                        AccessRequestRecord.target_schema_id.in_(schema_ids),
                        AccessRequestRecord.status == AccessRequestStatus.PENDING.value,
                    )
                    .order_by(AccessRequestRecord.requested_at.desc())
                )
            ).all()
            if schema_ids
            else []
        )
        pending_changes = (
            await self.session.scalars(
                select(ResourceChangeRequestRecord)
                .where(
                    ResourceChangeRequestRecord.domain_id == domain_id,
                    ResourceChangeRequestRecord.status == AccessRequestStatus.PENDING.value,
                )
                .order_by(ResourceChangeRequestRecord.requested_at.desc())
            )
        ).all()

        audit_targets = {domain_id, *schema_ids, *[scope.id for scope in scopes]}
        audit_rows = (
            await self.session.scalars(
                select(AuditEventRecord)
                .where(AuditEventRecord.target_id.in_(audit_targets))
                .order_by(AuditEventRecord.timestamp.desc())
                .limit(25)
            )
        ).all()

        return {
            "domain": _record_data(domain),
            "organization": _record_data(organization) if organization else None,
            "project": _record_data(project) if project else None,
            "scopes": [_record_data(scope) for scope in scopes],
            "schemas": schemas,
            "home_agents": [_record_data(agent) for agent in home_agents],
            "resolution": {
                "domain_default": domain_default,
                "agent_policies": agent_policies,
            },
            "pending_requests": {
                "access": [_record_data(item) for item in pending_access],
                "changes": [_record_data(item) for item in pending_changes],
            },
            "audit": [_record_data(item) for item in audit_rows],
        }

    async def _organization_membership(
        self, principal: AdminPrincipal, organization_id: str
    ) -> OrganizationMembershipRecord | None:
        return await self.session.scalar(
            select(OrganizationMembershipRecord).where(
                OrganizationMembershipRecord.organization_id == organization_id,
                OrganizationMembershipRecord.member_principal == principal.principal.casefold(),
                OrganizationMembershipRecord.status == "ACTIVE",
            )
        )

    async def _project_membership(
        self, principal: AdminPrincipal, project_id: str
    ) -> ProjectMembershipRecord | None:
        return await self.session.scalar(
            select(ProjectMembershipRecord).where(
                ProjectMembershipRecord.project_id == project_id,
                ProjectMembershipRecord.member_principal == principal.principal.casefold(),
                ProjectMembershipRecord.status == "ACTIVE",
            )
        )

    async def _require_organization_access(
        self, principal: AdminPrincipal, organization_id: str, *, manage: bool = False
    ) -> None:
        if AdminRole.PLATFORM_ADMIN in principal.roles:
            return
        membership = await self._organization_membership(principal, organization_id)
        if membership is None or (manage and membership.role not in {"OWNER", "ADMIN"}):
            action = "manage" if manage else "read"
            raise PermissionError(
                f"organization membership is required to {action} {organization_id}"
            )

    async def _require_project_access(
        self, principal: AdminPrincipal, project: ProjectRecord, *, manage: bool = False
    ) -> None:
        if AdminRole.PLATFORM_ADMIN in principal.roles:
            return
        organization_membership = await self._organization_membership(
            principal, project.organization_id
        )
        if organization_membership and (
            not manage or organization_membership.role in {"OWNER", "ADMIN"}
        ):
            return
        project_membership = await self._project_membership(principal, project.id)
        if project_membership is None or (
            manage and project_membership.role not in {"OWNER", "ADMIN"}
        ):
            action = "manage" if manage else "read"
            raise PermissionError(f"project membership is required to {action} {project.id}")

    async def organization_hierarchy(self, principal: AdminPrincipal) -> dict[str, Any]:
        self.authorizer.require_read(principal)
        organizations = list(
            (
                await self.session.scalars(
                    select(OrganizationRecord).order_by(OrganizationRecord.name)
                )
            ).all()
        )
        projects = list(
            (await self.session.scalars(select(ProjectRecord).order_by(ProjectRecord.name))).all()
        )
        organization_members = list(
            (
                await self.session.scalars(
                    select(OrganizationMembershipRecord).order_by(
                        OrganizationMembershipRecord.member_principal
                    )
                )
            ).all()
        )
        project_members = list(
            (
                await self.session.scalars(
                    select(ProjectMembershipRecord).order_by(
                        ProjectMembershipRecord.member_principal
                    )
                )
            ).all()
        )
        domains = list(
            (
                await self.session.scalars(
                    select(MemoryDomainRecord).order_by(MemoryDomainRecord.name)
                )
            ).all()
        )
        agents = list(
            (
                await self.session.scalars(
                    select(RegisteredAgentRecord).order_by(RegisteredAgentRecord.display_name)
                )
            ).all()
        )

        is_platform_admin = AdminRole.PLATFORM_ADMIN in principal.roles
        organization_roles = {
            member.organization_id: member.role
            for member in organization_members
            if member.member_principal == principal.principal.casefold()
            and member.status == "ACTIVE"
        }
        project_roles = {
            member.project_id: member.role
            for member in project_members
            if member.member_principal == principal.principal.casefold()
            and member.status == "ACTIVE"
        }
        projects_by_organization: dict[str, list[dict[str, Any]]] = {}
        for project in projects:
            project_data = _record_data(project)
            project_data["current_member_role"] = (
                "PLATFORM_ADMIN" if is_platform_admin else project_roles.get(project.id)
            )
            project_data["members"] = [
                _record_data(member)
                for member in project_members
                if member.project_id == project.id
            ]
            project_data["domains"] = [
                _record_data(domain) for domain in domains if domain.project_id == project.id
            ]
            project_data["agents"] = [
                _record_data(agent) for agent in agents if agent.project_id == project.id
            ]
            projects_by_organization.setdefault(project.organization_id, []).append(project_data)

        return {
            "organizations": [
                {
                    **_record_data(organization),
                    "current_member_role": (
                        "PLATFORM_ADMIN"
                        if is_platform_admin
                        else organization_roles.get(organization.id)
                    ),
                    "members": [
                        _record_data(member)
                        for member in organization_members
                        if member.organization_id == organization.id
                    ],
                    "projects": projects_by_organization.get(organization.id, []),
                }
                for organization in organizations
            ]
        }

    async def add_organization_member(
        self,
        principal: AdminPrincipal,
        organization_id: str,
        payload: MembershipCreate,
    ) -> dict[str, Any]:
        await self._require_existing_organization(organization_id)
        await self._require_organization_access(principal, organization_id, manage=True)
        member_principal = payload.member_principal.strip().casefold()
        existing = await self.session.scalar(
            select(OrganizationMembershipRecord).where(
                OrganizationMembershipRecord.organization_id == organization_id,
                OrganizationMembershipRecord.member_principal == member_principal,
            )
        )
        if existing is not None:
            raise ResourceConflictError(
                f"member {member_principal} already belongs to organization {organization_id}"
            )
        record = OrganizationMembershipRecord(
            id=str(uuid4()),
            organization_id=organization_id,
            member_principal=member_principal,
            display_name=payload.display_name,
            role=payload.role,
            status="ACTIVE",
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal,
            "organization.member_added",
            "organization-membership",
            record.id,
            None,
            after,
        )
        return after

    async def get_organization_settings(
        self, principal: AdminPrincipal, organization_id: str
    ) -> dict[str, Any]:
        await self._require_existing_organization(organization_id)
        await self._require_organization_access(principal, organization_id)
        record = await self.session.get(OrganizationSettingsRecord, organization_id)
        if record is None:
            return {
                "organization_id": organization_id,
                "budget_amount": None,
                "currency": "USD",
                "budget_period": "MONTHLY",
                "budget_enabled": False,
                "thresholds": [{"percent": 80, "basis": "ACTUAL"}],
                "email_recipients": [],
                "monitoring_channel_ids": [],
                "pubsub_topic": None,
                "billing_account_id": None,
                "billing_project_ids": [],
                "external_budget_name": None,
                "sync_status": "LOCAL_ONLY",
            }
        return _record_data(record)

    async def update_organization_settings(
        self,
        principal: AdminPrincipal,
        organization_id: str,
        payload: OrganizationSettingsUpdate,
    ) -> dict[str, Any]:
        await self._require_existing_organization(organization_id)
        await self._require_organization_access(principal, organization_id, manage=True)
        if payload.budget_enabled and payload.budget_amount is None:
            raise ValueError("budgetAmount is required when budget notifications are enabled")
        record = await self.session.get(OrganizationSettingsRecord, organization_id)
        before = _record_data(record) if record else None
        values = payload.model_dump(by_alias=False)
        values["thresholds"] = [item.model_dump() for item in payload.thresholds]
        if record is None:
            record = OrganizationSettingsRecord(
                organization_id=organization_id,
                external_budget_name=None,
                sync_status="PENDING_SYNC" if payload.budget_enabled else "LOCAL_ONLY",
                **values,
            )
            self.session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
            record.sync_status = "PENDING_SYNC" if payload.budget_enabled else "LOCAL_ONLY"
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal,
            "organization.settings_updated",
            "organization",
            organization_id,
            before,
            after,
        )
        return after

    async def get_project_settings(
        self, principal: AdminPrincipal, project_id: str
    ) -> dict[str, Any]:
        project = await self.session.get(ProjectRecord, project_id)
        if project is None:
            raise ResourceNotFoundError(f"project {project_id} was not found")
        await self._require_project_access(principal, project)
        record = await self.session.get(ProjectSettingsRecord, project_id)
        if record is None:
            return {
                "project_id": project_id,
                "health_refresh_seconds": 300,
                "latency_warning_ms": 2000,
                "error_rate_warning": 0.05,
                "notifications_enabled": True,
                "notification_channel_ids": [],
            }
        return _record_data(record)

    async def update_project_settings(
        self, principal: AdminPrincipal, project_id: str, payload: ProjectSettingsUpdate
    ) -> dict[str, Any]:
        project = await self.session.get(ProjectRecord, project_id)
        if project is None:
            raise ResourceNotFoundError(f"project {project_id} was not found")
        await self._require_project_access(principal, project, manage=True)
        record = await self.session.get(ProjectSettingsRecord, project_id)
        before = _record_data(record) if record else None
        values = payload.model_dump(by_alias=False)
        if record is None:
            record = ProjectSettingsRecord(project_id=project_id, **values)
            self.session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal, "project.settings_updated", "project", project_id, before, after
        )
        return after

    async def upsert_agent_runtime_binding(
        self, principal: AdminPrincipal, agent_id: str, payload: AgentRuntimeBindingUpdate
    ) -> dict[str, Any]:
        agent = await self.session.get(RegisteredAgentRecord, agent_id)
        if agent is None:
            raise ResourceNotFoundError(f"agent {agent_id} was not found")
        project = await self.session.get(ProjectRecord, agent.project_id)
        if project is None:
            raise ResourceNotFoundError(f"project {agent.project_id} was not found")
        await self._require_project_access(principal, project, manage=True)
        if payload.provider == "GOOGLE_AGENT_RUNTIME" and (
            not payload.gcp_project_id or not payload.resource_name
        ):
            raise ValueError("gcpProjectId and resourceName are required for Google Agent Runtime")
        record = await self.session.get(AgentRuntimeBindingRecord, agent_id)
        before = _record_data(record) if record else None
        values = payload.model_dump(by_alias=False)
        if record is None:
            record = AgentRuntimeBindingRecord(agent_id=agent_id, status="CONFIGURED", **values)
            self.session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
            record.status = "CONFIGURED"
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal, "agent.runtime_binding_updated", "agent", agent_id, before, after
        )
        return after

    async def get_agent_runtime_binding(
        self, principal: AdminPrincipal, agent_id: str
    ) -> dict[str, Any]:
        agent = await self.session.get(RegisteredAgentRecord, agent_id)
        if agent is None:
            raise ResourceNotFoundError(f"agent {agent_id} was not found")
        project = await self.session.get(ProjectRecord, agent.project_id)
        if project is None:
            raise ResourceNotFoundError(f"project {agent.project_id} was not found")
        await self._require_project_access(principal, project)
        record = await self.session.get(AgentRuntimeBindingRecord, agent_id)
        return (
            _record_data(record) if record else {"agent_id": agent_id, "status": "NOT_CONFIGURED"}
        )

    async def project_health(
        self, principal: AdminPrincipal, project_id: str, *, refresh: bool = False
    ) -> dict[str, Any]:
        project = await self.session.get(ProjectRecord, project_id)
        if project is None:
            raise ResourceNotFoundError(f"project {project_id} was not found")
        await self._require_project_access(principal, project)
        agents = list(
            (
                await self.session.scalars(
                    select(RegisteredAgentRecord)
                    .where(RegisteredAgentRecord.project_id == project_id)
                    .order_by(RegisteredAgentRecord.display_name)
                )
            ).all()
        )
        items: list[dict[str, Any]] = []
        for agent in agents:
            binding = await self.session.get(AgentRuntimeBindingRecord, agent.id)
            snapshot = await self.session.get(AgentHealthSnapshotRecord, agent.id)
            if refresh and binding is not None:
                result = await self.health_provider.collect(binding)
                now = datetime.now(UTC)
                values = {
                    "health_status": result.health_status,
                    "provider_status": result.provider_status,
                    "request_count": result.request_count,
                    "error_rate": result.error_rate,
                    "p95_latency_ms": result.p95_latency_ms,
                    "last_success_at": result.last_success_at,
                    "observed_at": now,
                    "details": result.details or {},
                }
                if snapshot is None:
                    snapshot = AgentHealthSnapshotRecord(agent_id=agent.id, **values)
                    self.session.add(snapshot)
                else:
                    for key, value in values.items():
                        setattr(snapshot, key, value)
            items.append(
                {
                    "agent": _record_data(agent),
                    "binding": _record_data(binding) if binding else None,
                    "health": _record_data(snapshot)
                    if snapshot
                    else {
                        "health_status": "UNKNOWN",
                        "provider_status": "NOT_CONFIGURED" if binding is None else "NOT_CHECKED",
                    },
                    "resource_tags": {
                        "organization_id": project.organization_id,
                        "project_id": project.id,
                        "agent_id": agent.id,
                        "environment": binding.environment if binding else "unknown",
                    },
                }
            )
        if refresh:
            await self.session.flush()
        return {"project": _record_data(project), "agents": items}

    async def add_project_member(
        self,
        principal: AdminPrincipal,
        project_id: str,
        payload: MembershipCreate,
    ) -> dict[str, Any]:
        project = await self.session.get(ProjectRecord, project_id)
        if project is None:
            raise ResourceNotFoundError(f"project {project_id} was not found")
        await self._require_project_access(principal, project, manage=True)
        member_principal = payload.member_principal.strip().casefold()
        organization_member = await self.session.scalar(
            select(OrganizationMembershipRecord).where(
                OrganizationMembershipRecord.organization_id == project.organization_id,
                OrganizationMembershipRecord.member_principal == member_principal,
                OrganizationMembershipRecord.status == "ACTIVE",
            )
        )
        if organization_member is None:
            raise ResourceConflictError(
                "project members must first be active members of the parent organization"
            )
        existing = await self.session.scalar(
            select(ProjectMembershipRecord).where(
                ProjectMembershipRecord.project_id == project_id,
                ProjectMembershipRecord.member_principal == member_principal,
            )
        )
        if existing is not None:
            raise ResourceConflictError(
                f"member {member_principal} already belongs to project {project_id}"
            )
        record = ProjectMembershipRecord(
            id=str(uuid4()),
            project_id=project_id,
            member_principal=member_principal,
            display_name=payload.display_name,
            role=payload.role,
            status="ACTIVE",
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal,
            "project.member_added",
            "project-membership",
            record.id,
            None,
            after,
        )
        return after

    async def create_resource(
        self,
        principal: AdminPrincipal,
        resource: str,
        payload: DomainCreate
        | OrganizationCreate
        | ProjectCreate
        | ScopeCreate
        | SchemaCreate
        | PreferenceCreate
        | AgentCreate
        | ResolutionPolicyCreate
        | DynamicMemoryPolicyCreate,
    ) -> dict[str, Any]:
        values = payload.model_dump(by_alias=False)
        schema_details: dict[str, Any] | None = None
        policy_details: dict[str, Any] | None = None
        if resource == "schemas":
            schema_details = {
                key: values.pop(key)
                for key in (
                    "version",
                    "scope_definition_id",
                    "vertex_schema_definition",
                    "generation_config",
                    "mappings",
                    "retention_days",
                    "allowed_purposes",
                )
            }
        elif resource == "resolution-policies":
            policy_details = {
                "schema_priorities": values.pop("schema_priorities"),
                "attribute_overrides": values.pop("attribute_overrides"),
            }
        resource_id = str(values[RESOURCE_IDS[resource]])
        if await self.session.get(RESOURCE_MODELS[resource], resource_id):
            raise ResourceConflictError(f"{resource} resource {resource_id} already exists")

        domain_id = values.get("owner_domain_id") or values.get("domain_id")
        if resource in {"organizations", "projects", "domains"}:
            self.authorizer.require_platform(principal)
        elif resource == "resolution-policies":
            agent_id = values.get("agent_id")
            if agent_id:
                agent = await self.session.get(RegisteredAgentRecord, agent_id)
                if agent is None:
                    raise ResourceNotFoundError(f"agent {agent_id} was not found")
                domain_id = agent.domain_id
            else:
                self.authorizer.require_platform(principal)
        elif resource == "dynamic-memory-policies" and not domain_id:
            schema_id = values.get("schema_id")
            if schema_id:
                schema = await self.session.get(ProfileSchemaRecord, schema_id)
                if schema is None:
                    raise ResourceNotFoundError(f"schema {schema_id} was not found")
                domain_id = schema.domain_id
            else:
                self.authorizer.require_platform(principal)

        if domain_id:
            await self._require_existing_domain(str(domain_id))
            self.authorizer.require_domain(principal, str(domain_id))

        if resource == "projects":
            await self._require_existing_organization(str(values["organization_id"]))
        elif resource == "domains":
            await self._require_project_ownership(
                str(values["organization_id"]), str(values["project_id"])
            )
        elif resource == "agents":
            await self._require_project_ownership(
                str(values["organization_id"]), str(values["project_id"])
            )
            domain = await self._require_existing_domain(str(values["domain_id"]))
            if (
                domain.organization_id != values["organization_id"]
                or domain.project_id != values["project_id"]
            ):
                raise ResourceConflictError(
                    "agent organization/project must match its primary domain ownership"
                )

        model = RESOURCE_MODELS[resource]
        if "status" in model.__table__.columns:
            values["status"] = (
                LifecycleStatus.ACTIVE.value
                if resource == "organizations"
                else LifecycleStatus.DRAFT.value
            )
        record = model(**values)
        self.session.add(record)
        await self.session.flush()
        if resource == "schemas" and schema_details is not None:
            await self._create_schema_version(record, schema_details)
        elif resource == "resolution-policies" and policy_details is not None:
            await self._replace_resolution_controls(record.id, **policy_details)
        await self.session.refresh(record)
        after = await self.get_resource(principal, resource, resource_id)
        await self._audit(principal, f"{resource}.created", resource, resource_id, None, after)
        return after

    async def _create_schema_version(
        self, schema: ProfileSchemaRecord, details: dict[str, Any]
    ) -> None:
        scope = await self.session.get(ScopeDefinitionRecord, details["scope_definition_id"])
        if scope is None:
            raise ResourceNotFoundError(f"scope {details['scope_definition_id']} was not found")
        if scope.owner_domain_id != schema.domain_id:
            raise ResourceConflictError("schema and scope must belong to the same domain")
        mappings = details["mappings"]
        attributes = [item["attribute_id"] for item in mappings]
        fields = [item["profile_field"] for item in mappings]
        if len(attributes) != len(set(attributes)) or len(fields) != len(set(fields)):
            raise ResourceConflictError("schema mappings must have unique attributes and fields")
        sensitivities: list[str] = []
        has_health = False
        for attribute_id in attributes:
            preference = await self.session.get(PreferenceDefinitionRecord, attribute_id)
            if preference is None:
                raise ResourceNotFoundError(f"preference {attribute_id} was not found")
            if preference.canonical_owner_id != schema.domain_id:
                raise ResourceConflictError(
                    f"preference {attribute_id} is not owned by domain {schema.domain_id}"
                )
            sensitivities.append(preference.sensitivity_classification)
            has_health = has_health or bool((preference.validation_rules or {}).get("health"))
        retention_days = details.get("retention_days")
        check_retention(
            retention_days, retention_tier(sensitivities, health=has_health), schema_id=schema.id
        )
        version_id = f"{schema.id}:{details['version']}"
        self.session.add(
            ProfileSchemaVersionRecord(
                id=version_id,
                schema_id=schema.id,
                version=details["version"],
                status=LifecycleStatus.DRAFT.value,
                scope_definition_id=details["scope_definition_id"],
                vertex_schema_definition=details["vertex_schema_definition"],
                generation_config=details["generation_config"],
                retention_days=retention_days,
                allowed_purposes=list(details.get("allowed_purposes") or ["personalization"]),
            )
        )
        for mapping in mappings:
            self.session.add(
                SchemaPreferenceMappingRecord(
                    id=f"{version_id}:{mapping['profile_field']}",
                    schema_version_id=version_id,
                    attribute_id=mapping["attribute_id"],
                    profile_field=mapping["profile_field"],
                )
            )
        await self.session.flush()

    async def _replace_resolution_controls(
        self,
        policy_id: str,
        *,
        schema_priorities: list[dict[str, Any]],
        attribute_overrides: list[dict[str, Any]],
    ) -> None:
        priorities = [item["priority"] for item in schema_priorities]
        if len(priorities) != len(set(priorities)):
            raise ResourceConflictError("resolution policy priorities must be unique")
        await self.session.execute(
            delete(ResolutionPolicySchemaPriorityRecord).where(
                ResolutionPolicySchemaPriorityRecord.policy_id == policy_id
            )
        )
        await self.session.execute(
            delete(ResolutionAttributeOverrideRecord).where(
                ResolutionAttributeOverrideRecord.policy_id == policy_id
            )
        )
        for item in schema_priorities:
            if await self.session.get(ProfileSchemaRecord, item["schema_id"]) is None:
                raise ResourceNotFoundError(f"schema {item['schema_id']} was not found")
            self.session.add(
                ResolutionPolicySchemaPriorityRecord(
                    id=f"{policy_id}:{item['priority']}",
                    policy_id=policy_id,
                    schema_id=item["schema_id"],
                    priority=item["priority"],
                )
            )
        for item in attribute_overrides:
            if await self.session.get(PreferenceDefinitionRecord, item["attribute_id"]) is None:
                raise ResourceNotFoundError(f"preference {item['attribute_id']} was not found")
            for schema_id in item["schema_precedence"]:
                if await self.session.get(ProfileSchemaRecord, schema_id) is None:
                    raise ResourceNotFoundError(f"schema {schema_id} was not found")
            self.session.add(
                ResolutionAttributeOverrideRecord(
                    id=f"{policy_id}:{item['attribute_id']}",
                    policy_id=policy_id,
                    attribute_id=item["attribute_id"],
                    schema_precedence=item["schema_precedence"],
                    rules=item["rules"],
                )
            )
        await self.session.flush()

    async def _require_existing_organization(self, organization_id: str) -> OrganizationRecord:
        organization = await self.session.get(OrganizationRecord, organization_id)
        if organization is None:
            raise ResourceNotFoundError(f"organization {organization_id} was not found")
        return organization

    async def _require_project_ownership(
        self, organization_id: str, project_id: str
    ) -> ProjectRecord:
        project = await self.session.get(ProjectRecord, project_id)
        if project is None:
            raise ResourceNotFoundError(f"project {project_id} was not found")
        if project.organization_id != organization_id:
            raise ResourceConflictError(
                f"project {project_id} does not belong to organization {organization_id}"
            )
        return project

    async def _require_existing_domain(self, domain_id: str) -> MemoryDomainRecord:
        domain = await self.session.get(MemoryDomainRecord, domain_id)
        if domain is None:
            raise ResourceNotFoundError(f"domain {domain_id} was not found")
        return domain

    async def update_resource(
        self,
        principal: AdminPrincipal,
        resource: str,
        resource_id: str,
        payload: ResourceUpdate,
    ) -> dict[str, Any]:
        record = await self._get(resource, resource_id)
        domain_id = await self._domain_for(resource, record)
        if domain_id:
            self.authorizer.require_domain(principal, domain_id)
        else:
            self.authorizer.require_platform(principal)
        before = _record_data(record)

        changes = {CHANGE_ALIASES.get(key, key): value for key, value in payload.changes.items()}
        schema_priorities = changes.pop("schema_priorities", None)
        attribute_overrides = changes.pop("attribute_overrides", None)
        if schema_priorities is not None:
            schema_priorities = [
                {
                    "schema_id": item.get("schema_id", item.get("schemaId")),
                    "priority": item["priority"],
                }
                for item in schema_priorities
            ]
        if attribute_overrides is not None:
            attribute_overrides = [
                {
                    "attribute_id": item.get("attribute_id", item.get("attributeId")),
                    "schema_precedence": item.get(
                        "schema_precedence", item.get("schemaPrecedence")
                    ),
                    "rules": item.get("rules", {}),
                }
                for item in attribute_overrides
            ]
        unknown = set(changes).difference(UPDATABLE_FIELDS[resource])
        if unknown:
            raise ValueError(f"fields cannot be updated for {resource}: {sorted(unknown)}")
        for field, value in changes.items():
            setattr(record, field, value)

        if resource == "resolution-policies" and (
            schema_priorities is not None or attribute_overrides is not None
        ):
            current = await self._resolution_policy_data(record)
            await self._replace_resolution_controls(
                record.id,
                schema_priorities=(
                    schema_priorities
                    if schema_priorities is not None
                    else current["schema_priorities"]
                ),
                attribute_overrides=(
                    attribute_overrides
                    if attribute_overrides is not None
                    else current["attribute_overrides"]
                ),
            )

        if payload.status is not None:
            if not hasattr(record, "status"):
                raise ValueError(f"{resource} does not support lifecycle status")
            current = LifecycleStatus(record.status)
            target = LifecycleStatus(payload.status)
            if target != current and target not in LIFECYCLE_TRANSITIONS[current]:
                raise ResourceConflictError(
                    f"invalid lifecycle transition for {resource}: {current} -> {target}"
                )
            record.status = target.value
            if resource == "schemas":
                versions = await self.session.scalars(
                    select(ProfileSchemaVersionRecord).where(
                        ProfileSchemaVersionRecord.schema_id == record.id
                    )
                )
                for version in versions:
                    version.status = target.value

        await self.session.flush()
        await self.session.refresh(record)
        after = await self.get_resource(principal, resource, resource_id)
        await self._audit(principal, f"{resource}.updated", resource, resource_id, before, after)
        return after

    async def submit_domain_change(
        self,
        principal: AdminPrincipal,
        domain_id: str,
        payload: ResourceUpdate,
    ) -> dict[str, Any]:
        domain = await self._require_existing_domain(domain_id)
        self.authorizer.require_domain(principal, domain.id, AdminRole.DOMAIN_ADMIN)
        if payload.status is not None:
            raise ValueError("domain lifecycle changes are not supported by this approval flow")
        changes = {CHANGE_ALIASES.get(key, key): value for key, value in payload.changes.items()}
        unknown = set(changes).difference(UPDATABLE_FIELDS["domains"])
        if unknown:
            raise ValueError(f"fields cannot be updated for domains: {sorted(unknown)}")
        before = _record_data(domain)
        changes = {key: value for key, value in changes.items() if before.get(key) != value}
        if not changes:
            raise ValueError("domain change request does not contain any changed values")
        pending = await self.session.scalar(
            select(ResourceChangeRequestRecord).where(
                ResourceChangeRequestRecord.resource_type == "domains",
                ResourceChangeRequestRecord.resource_id == domain.id,
                ResourceChangeRequestRecord.status == "PENDING",
            )
        )
        if pending is not None:
            raise ResourceConflictError("a pending domain change request already exists")
        record = ResourceChangeRequestRecord(
            id=str(uuid4()),
            resource_type="domains",
            resource_id=domain.id,
            organization_id=domain.organization_id,
            project_id=domain.project_id,
            domain_id=domain.id,
            before_values=_audit_metadata(before) or {},
            proposed_changes=changes,
            requested_by=principal.principal,
            requested_at=datetime.now(UTC),
            status="PENDING",
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal, "domain.change_requested", "resource_change_request", record.id, None, after
        )
        return after

    async def submit_schema_version_change(
        self,
        principal: AdminPrincipal,
        schema_id: str,
        payload: SchemaVersionChange,
    ) -> dict[str, Any]:
        schema = await self._get("schemas", schema_id)
        domain = await self._require_existing_domain(schema.domain_id)
        self.authorizer.require_domain(
            principal, domain.id, AdminRole.SCHEMA_OWNER, AdminRole.DOMAIN_ADMIN
        )
        if schema.status != LifecycleStatus.ACTIVE.value:
            raise ResourceConflictError("only an active schema can be versioned")
        pending = await self.session.scalar(
            select(ResourceChangeRequestRecord).where(
                ResourceChangeRequestRecord.resource_type == "schemas",
                ResourceChangeRequestRecord.resource_id == schema.id,
                ResourceChangeRequestRecord.status == "PENDING",
            )
        )
        if pending:
            raise ResourceConflictError("a pending schema version change already exists")
        active = await self.session.scalar(
            select(ProfileSchemaVersionRecord)
            .where(
                ProfileSchemaVersionRecord.schema_id == schema.id,
                ProfileSchemaVersionRecord.status == LifecycleStatus.ACTIVE.value,
            )
            .order_by(ProfileSchemaVersionRecord.version.desc())
            .limit(1)
        )
        if active is None:
            raise ResourceConflictError("schema has no active version to edit")
        values = payload.model_dump(by_alias=False)
        if values["scope_definition_id"] not in {None, active.scope_definition_id}:
            raise ResourceConflictError(
                "schema scope is protected; create a governed migration to change it"
            )
        active_mappings = (
            await self.session.scalars(
                select(SchemaPreferenceMappingRecord).where(
                    SchemaPreferenceMappingRecord.schema_version_id == active.id
                )
            )
        ).all()
        protected_mappings = {item.attribute_id: item.profile_field for item in active_mappings}
        proposed_mappings = {
            item["attribute_id"]: item["profile_field"] for item in values["mappings"]
        }
        removed_or_renamed = {
            attribute_id
            for attribute_id, profile_field in protected_mappings.items()
            if proposed_mappings.get(attribute_id) != profile_field
        }
        if removed_or_renamed:
            raise ResourceConflictError(
                "active schema mappings cannot be removed or renamed in the additive edit flow: "
                f"{sorted(removed_or_renamed)}"
            )
        requested_definition = values["vertex_schema_definition"] or active.vertex_schema_definition
        active_properties = dict(active.vertex_schema_definition.get("properties", {}))
        requested_properties = dict(requested_definition.get("properties", {}))
        safe_properties = {
            **active_properties,
            **{
                field: definition
                for field, definition in requested_properties.items()
                if field not in active_properties
            },
        }
        safe_definition = {
            **active.vertex_schema_definition,
            "type": "object",
            "properties": safe_properties,
        }
        details = {
            "version": values["version"],
            "scope_definition_id": active.scope_definition_id,
            "vertex_schema_definition": safe_definition,
            "generation_config": active.generation_config,
            "mappings": values["mappings"],
            "retention_days": active.retention_days,
            "allowed_purposes": active.allowed_purposes,
        }
        if await self.session.get(ProfileSchemaVersionRecord, f"{schema.id}:{details['version']}"):
            raise ResourceConflictError(
                f"schema version {schema.id}:{details['version']} already exists"
            )
        await self._create_schema_version(schema, details)
        draft_id = f"{schema.id}:{details['version']}"
        record = ResourceChangeRequestRecord(
            id=str(uuid4()),
            resource_type="schemas",
            resource_id=schema.id,
            organization_id=domain.organization_id,
            project_id=domain.project_id,
            domain_id=domain.id,
            before_values={"active_version_id": active.id, "version": active.version},
            proposed_changes={
                "draft_version_id": draft_id,
                "version": details["version"],
                "mapping_count": len(details["mappings"]),
            },
            requested_by=principal.principal,
            requested_at=datetime.now(UTC),
            status="PENDING",
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal,
            "schema.version_change_requested",
            "resource_change_request",
            record.id,
            None,
            after,
        )
        return after

    async def list_resource_change_requests(
        self, principal: AdminPrincipal
    ) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        result = await self.session.scalars(
            select(ResourceChangeRequestRecord).order_by(
                ResourceChangeRequestRecord.requested_at.desc()
            )
        )
        return [_record_data(record) for record in result]

    async def decide_resource_change(
        self,
        principal: AdminPrincipal,
        request_id: str,
        decision: str,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self.authorizer.require_platform(principal)
        record = await self.session.get(ResourceChangeRequestRecord, request_id)
        if record is None:
            raise ResourceNotFoundError(f"resource change request {request_id} was not found")
        if record.status != "PENDING":
            raise ResourceConflictError("only a pending resource change request can be decided")
        if decision not in {"APPROVED", "REJECTED"}:
            raise ValueError(f"unsupported resource change decision {decision}")
        before = _record_data(record)
        if decision == "APPROVED" and record.resource_type == "domains":
            domain = await self._require_existing_domain(record.domain_id)
            for field in record.proposed_changes:
                if record.before_values.get(field) != getattr(domain, field):
                    raise ResourceConflictError(
                        "domain changed after this request was submitted; reject it and submit a new edit"
                    )
            for field, value in record.proposed_changes.items():
                setattr(domain, field, value)
            domain_after = _record_data(domain)
            await self.session.flush()
            await self._audit(
                principal,
                "domains.updated",
                "domains",
                domain.id,
                record.before_values,
                domain_after,
            )
        elif record.resource_type == "schemas":
            draft = await self.session.get(
                ProfileSchemaVersionRecord, record.proposed_changes["draft_version_id"]
            )
            active = await self.session.get(
                ProfileSchemaVersionRecord, record.before_values["active_version_id"]
            )
            if draft is None or draft.status != LifecycleStatus.DRAFT.value:
                raise ResourceConflictError("schema draft is missing or no longer editable")
            if active is None or active.status != LifecycleStatus.ACTIVE.value:
                raise ResourceConflictError(
                    "active schema version changed after this request was submitted"
                )
            if decision == "APPROVED":
                active.status = LifecycleStatus.DEPRECATED.value
                draft.status = LifecycleStatus.ACTIVE.value
            else:
                draft.status = LifecycleStatus.RETIRED.value
        elif record.resource_type != "domains":
            raise ResourceConflictError(f"unsupported resource change type {record.resource_type}")
        record.status = decision
        record.decided_by = principal.principal
        record.decided_at = datetime.now(UTC)
        record.decision_reason = reason
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal,
            f"{record.resource_type}.change_{decision.lower()}",
            "resource_change_request",
            record.id,
            before,
            after,
        )
        return after

    async def create_access_request(
        self, principal: AdminPrincipal, payload: AccessRequestCreate
    ) -> dict[str, Any]:
        permission = AccessPermission(payload.requested_permission)
        if permission == AccessPermission.NONE:
            raise ValueError("requestedPermission must grant READ, WRITE, or READ_WRITE")
        agent = await self.session.get(RegisteredAgentRecord, payload.requesting_agent_id)
        if agent is None:
            raise ResourceNotFoundError(f"agent {payload.requesting_agent_id} was not found")
        self.authorizer.require_domain(
            principal, agent.domain_id, AdminRole.AGENT_OWNER, AdminRole.DOMAIN_ADMIN
        )
        target_schema = await self.session.get(ProfileSchemaRecord, payload.target_schema_id)
        if target_schema is None:
            raise ResourceNotFoundError(f"schema {payload.target_schema_id} was not found")
        attributes = sorted(set(payload.attributes)) if payload.attributes else None
        if permission != AccessPermission.READ and target_schema.domain_id != agent.domain_id:
            # Delegated write: only named attributes of another domain's schema, never health data.
            if not attributes:
                raise ValueError(
                    "write access to another domain's schema must name the attributes to write"
                )
            health = [
                attribute
                for attribute in attributes
                if (definition := await self.session.get(PreferenceDefinitionRecord, attribute))
                and (definition.validation_rules or {}).get("health")
            ]
            if health:
                raise ValueError(
                    f"health data cannot be written from another domain: {', '.join(health)}"
                )
        if attributes:
            unknown = set(attributes) - await self.active_schema_attributes(
                payload.target_schema_id
            )
            if unknown:
                raise ValueError(
                    f"schema {payload.target_schema_id} does not map: {', '.join(sorted(unknown))}"
                )
        pending = await self.session.scalar(
            select(AccessRequestRecord).where(
                AccessRequestRecord.requesting_agent_id == payload.requesting_agent_id,
                AccessRequestRecord.target_schema_id == payload.target_schema_id,
                AccessRequestRecord.status == AccessRequestStatus.PENDING.value,
            )
        )
        if pending:
            raise ResourceConflictError("a pending access request already exists")

        now = datetime.now(UTC)
        if payload.expiration and _utc(payload.expiration) <= now:
            raise ValueError("expiration must be in the future")
        record = AccessRequestRecord(
            id=str(uuid4()),
            requesting_agent_id=payload.requesting_agent_id,
            requesting_team=payload.requesting_team,
            target_schema_id=payload.target_schema_id,
            requested_permission=permission.value,
            attributes=attributes,
            business_reason=payload.business_reason,
            requested_by=principal.principal,
            requested_at=now,
            status=AccessRequestStatus.PENDING.value,
            expiration=payload.expiration,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal, "access_request.created", "access_request", record.id, None, after
        )
        return after

    async def active_schema_attributes(self, schema_id: str) -> set[str]:
        """Attribute ids mapped by the schema's latest active version."""
        version = await self.session.scalar(
            select(ProfileSchemaVersionRecord)
            .where(
                ProfileSchemaVersionRecord.schema_id == schema_id,
                ProfileSchemaVersionRecord.status == LifecycleStatus.ACTIVE.value,
            )
            .order_by(ProfileSchemaVersionRecord.version.desc())
            .limit(1)
        )
        if version is None:
            return set()
        return set(
            await self.session.scalars(
                select(SchemaPreferenceMappingRecord.attribute_id).where(
                    SchemaPreferenceMappingRecord.schema_version_id == version.id
                )
            )
        )

    async def list_access_requests(self, principal: AdminPrincipal) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        records = await self.session.scalars(
            select(AccessRequestRecord).order_by(AccessRequestRecord.requested_at.desc())
        )
        return [_record_data(record) for record in records]

    async def organization_approvals(
        self, principal: AdminPrincipal, organization_id: str
    ) -> dict[str, Any]:
        await self._require_existing_organization(organization_id)
        await self._require_organization_access(principal, organization_id)
        requests = list(
            (
                await self.session.scalars(
                    select(AccessRequestRecord).order_by(AccessRequestRecord.requested_at.desc())
                )
            ).all()
        )
        enriched: list[dict[str, Any]] = []
        for request in requests:
            agent = await self.session.get(RegisteredAgentRecord, request.requesting_agent_id)
            schema = await self.session.get(ProfileSchemaRecord, request.target_schema_id)
            target_domain = (
                await self.session.get(MemoryDomainRecord, schema.domain_id) if schema else None
            )
            item = _record_data(request)
            item.update(
                {
                    "requesting_organization_id": agent.organization_id if agent else None,
                    "requesting_project_id": agent.project_id if agent else None,
                    "requesting_agent_name": agent.display_name if agent else None,
                    "owning_organization_id": (
                        target_domain.organization_id if target_domain else None
                    ),
                    "owning_domain_id": target_domain.id if target_domain else None,
                }
            )
            enriched.append(item)
        incoming = [
            item
            for item in enriched
            if item["owning_organization_id"] == organization_id
            and item["status"] == AccessRequestStatus.PENDING.value
        ]
        outgoing = [
            item
            for item in enriched
            if item["requesting_organization_id"] == organization_id
            and item["status"] == AccessRequestStatus.PENDING.value
        ]
        history = [
            item
            for item in enriched
            if (
                item["owning_organization_id"] == organization_id
                or item["requesting_organization_id"] == organization_id
            )
            and item["status"] != AccessRequestStatus.PENDING.value
        ]
        return {"incoming": incoming, "outgoing": outgoing, "history": history}

    async def decide_access_request(
        self,
        principal: AdminPrincipal,
        request_id: str,
        decision: AccessRequestStatus,
        *,
        expiration: datetime | None = None,
        reason: str | None = None,
        attributes: list[str] | None = None,
    ) -> dict[str, Any]:
        record = await self.session.get(AccessRequestRecord, request_id)
        if record is None:
            raise ResourceNotFoundError(f"access request {request_id} was not found")
        schema = await self.session.get(ProfileSchemaRecord, record.target_schema_id)
        if schema is None:
            raise ResourceNotFoundError(f"schema {record.target_schema_id} was not found")
        target_domain = await self._require_existing_domain(schema.domain_id)
        membership = await self._organization_membership(principal, target_domain.organization_id)
        if not (
            AdminRole.PLATFORM_ADMIN in principal.roles
            or membership is not None
            and membership.role in {"OWNER", "ADMIN"}
        ):
            self.authorizer.require_domain(
                principal, schema.domain_id, AdminRole.SCHEMA_OWNER, AdminRole.DOMAIN_ADMIN
            )
        before = _record_data(record)
        now = datetime.now(UTC)

        if decision in {AccessRequestStatus.APPROVED, AccessRequestStatus.REJECTED}:
            if record.status != AccessRequestStatus.PENDING.value:
                raise ResourceConflictError("only a pending access request can be decided")
            if expiration and _utc(expiration) <= now:
                raise ValueError("expiration must be in the future")
            if attributes is not None:
                if decision != AccessRequestStatus.APPROVED:
                    raise ValueError("attributes can only be chosen when approving")
                # The owner may approve some of the requested attributes and deny the rest.
                requested = set(record.attributes or []) or await self.active_schema_attributes(
                    record.target_schema_id
                )
                extra = set(attributes) - requested
                if extra:
                    raise ValueError(
                        f"cannot approve attributes that were not requested: "
                        f"{', '.join(sorted(extra))}"
                    )
                record.approved_attributes = sorted(set(attributes))
            elif decision == AccessRequestStatus.APPROVED:
                record.approved_attributes = record.attributes
            record.status = decision.value
            record.approved_by = principal.principal
            record.approved_at = now
            if expiration is not None:
                record.expiration = expiration
            if decision == AccessRequestStatus.APPROVED:
                await self._require_purpose(record)
                await self._activate_grant(record, principal, now)
        elif decision in {AccessRequestStatus.REVOKED, AccessRequestStatus.EXPIRED}:
            if record.status != AccessRequestStatus.APPROVED.value:
                raise ResourceConflictError(
                    "only an approved access request can be revoked or expired"
                )
            if decision == AccessRequestStatus.EXPIRED and (
                record.expiration is None or _utc(record.expiration) > now
            ):
                raise ResourceConflictError("access request has not reached its expiration")
            record.status = decision.value
            await self._disable_grant(record, decision, principal)
        else:
            raise ValueError(f"unsupported access decision {decision}")

        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        if reason:
            after["decision_reason"] = reason
        await self._audit(
            principal,
            f"access_request.{decision.value.lower()}",
            "access_request",
            record.id,
            before,
            after,
        )
        return after

    async def _require_purpose(self, request: AccessRequestRecord) -> None:
        """Purpose limitation: the agent's declared purpose must be one the schema allows, and
        advertising is never allowed for per-member (possibly minor) or health data."""
        agent = await self.session.get(RegisteredAgentRecord, request.requesting_agent_id)
        if agent is None:
            return
        version = await self.session.scalar(
            select(ProfileSchemaVersionRecord)
            .where(ProfileSchemaVersionRecord.schema_id == request.target_schema_id)
            .order_by(
                (ProfileSchemaVersionRecord.status == LifecycleStatus.ACTIVE.value).desc(),
                ProfileSchemaVersionRecord.version.desc(),
            )
            .limit(1)
        )
        if version is None:
            return
        purpose = agent.purpose or "personalization"
        allowed = list(version.allowed_purposes or ["personalization"])
        if purpose not in allowed:
            raise PermissionError(
                f"agent {agent.id!r} declares purpose {purpose!r}, which schema "
                f"{request.target_schema_id!r} does not allow (allowed: {', '.join(allowed)})"
            )
        if purpose != RESTRICTED_PURPOSE:
            return
        scope = await self.session.get(ScopeDefinitionRecord, version.scope_definition_id)
        mappings = await self.session.scalars(
            select(SchemaPreferenceMappingRecord).where(
                SchemaPreferenceMappingRecord.schema_version_id == version.id
            )
        )
        health = False
        for mapping in mappings:
            granted = request.approved_attributes
            if granted and mapping.attribute_id not in granted:
                continue
            preference = await self.session.get(PreferenceDefinitionRecord, mapping.attribute_id)
            health = health or bool(preference and (preference.validation_rules or {}).get("health"))
        if health or (scope is not None and "member_id" in scope.scope_keys):
            raise PermissionError(
                f"{purpose} use is never allowed for per-member or health data "
                f"(schema {request.target_schema_id!r})"
            )

    async def _activate_grant(
        self, request: AccessRequestRecord, principal: AdminPrincipal, now: datetime
    ) -> None:
        grant_id = f"{request.requesting_agent_id}:{request.target_schema_id}"
        grant = await self.session.get(AgentSchemaGrantRecord, grant_id)
        before = _record_data(grant) if grant else None
        if grant is None:
            grant = AgentSchemaGrantRecord(
                id=grant_id,
                agent_id=request.requesting_agent_id,
                schema_id=request.target_schema_id,
            )
            self.session.add(grant)
        grant.permission = request.requested_permission
        grant.attributes = request.approved_attributes
        grant.status = LifecycleStatus.ACTIVE.value
        grant.approved_by = principal.principal
        grant.approved_at = now
        grant.expires_at = request.expiration
        await self.session.flush()
        await self.session.refresh(grant)
        await self._audit(
            principal,
            "schema_grant.activated",
            "agent_schema_grant",
            grant.id,
            before,
            _record_data(grant),
        )

    async def _disable_grant(
        self,
        request: AccessRequestRecord,
        decision: AccessRequestStatus,
        principal: AdminPrincipal,
    ) -> None:
        grant_id = f"{request.requesting_agent_id}:{request.target_schema_id}"
        grant = await self.session.get(AgentSchemaGrantRecord, grant_id)
        if grant is None:
            raise ResourceConflictError("approved access request has no schema grant")
        before = _record_data(grant)
        grant.status = decision.value
        await self.session.flush()
        await self.session.refresh(grant)
        await self._audit(
            principal,
            f"schema_grant.{decision.value.lower()}",
            "agent_schema_grant",
            grant.id,
            before,
            _record_data(grant),
        )

    async def list_audit(self, principal: AdminPrincipal) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        records = await self.session.scalars(
            select(AuditEventRecord).order_by(AuditEventRecord.timestamp.desc())
        )
        return [_record_data(record) for record in records]
