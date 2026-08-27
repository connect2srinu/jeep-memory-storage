from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_api.api.admin.models import (
    AccessRequestCreate,
    AgentCreate,
    DomainCreate,
    DynamicMemoryPolicyCreate,
    MembershipCreate,
    OrganizationCreate,
    PreferenceCreate,
    ProjectCreate,
    ResolutionPolicyCreate,
    ResourceUpdate,
    SchemaCreate,
    ScopeCreate,
)
from control_plane_api.domain import AccessPermission, AccessRequestStatus, LifecycleStatus
from control_plane_api.observability.runtime import correlation_id_context
from control_plane_api.persistence.models import (
    AccessRequestRecord,
    AgentSchemaGrantRecord,
    AuditEventRecord,
    DynamicMemoryPolicyRecord,
    MemoryDomainRecord,
    OrganizationMembershipRecord,
    OrganizationRecord,
    PreferenceDefinitionRecord,
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
    ProjectMembershipRecord,
    ProjectRecord,
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
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.authorizer = AdminAuthorizer()

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
        self, principal: AdminPrincipal, resource: str
    ) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        model = RESOURCE_MODELS[resource]
        id_column = getattr(model, RESOURCE_IDS[resource])
        records = await self.session.scalars(select(model).order_by(id_column))
        return [_record_data(record) for record in records]

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

        projects_by_organization: dict[str, list[dict[str, Any]]] = {}
        for project in projects:
            project_data = _record_data(project)
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
        self.authorizer.require_platform(principal)
        await self._require_existing_organization(organization_id)
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

    async def add_project_member(
        self,
        principal: AdminPrincipal,
        project_id: str,
        payload: MembershipCreate,
    ) -> dict[str, Any]:
        self.authorizer.require_platform(principal)
        project = await self.session.get(ProjectRecord, project_id)
        if project is None:
            raise ResourceNotFoundError(f"project {project_id} was not found")
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
        for attribute_id in attributes:
            preference = await self.session.get(PreferenceDefinitionRecord, attribute_id)
            if preference is None:
                raise ResourceNotFoundError(f"preference {attribute_id} was not found")
            if preference.canonical_owner_id != schema.domain_id:
                raise ResourceConflictError(
                    f"preference {attribute_id} is not owned by domain {schema.domain_id}"
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
        if decision == "APPROVED":
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
        record.status = decision
        record.decided_by = principal.principal
        record.decided_at = datetime.now(UTC)
        record.decision_reason = reason
        await self.session.flush()
        await self.session.refresh(record)
        after = _record_data(record)
        await self._audit(
            principal,
            f"domain.change_{decision.lower()}",
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
        if await self.session.get(ProfileSchemaRecord, payload.target_schema_id) is None:
            raise ResourceNotFoundError(f"schema {payload.target_schema_id} was not found")
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

    async def list_access_requests(self, principal: AdminPrincipal) -> list[dict[str, Any]]:
        self.authorizer.require_read(principal)
        records = await self.session.scalars(
            select(AccessRequestRecord).order_by(AccessRequestRecord.requested_at.desc())
        )
        return [_record_data(record) for record in records]

    async def decide_access_request(
        self,
        principal: AdminPrincipal,
        request_id: str,
        decision: AccessRequestStatus,
        *,
        expiration: datetime | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        record = await self.session.get(AccessRequestRecord, request_id)
        if record is None:
            raise ResourceNotFoundError(f"access request {request_id} was not found")
        schema = await self.session.get(ProfileSchemaRecord, record.target_schema_id)
        if schema is None:
            raise ResourceNotFoundError(f"schema {record.target_schema_id} was not found")
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
            record.status = decision.value
            record.approved_by = principal.principal
            record.approved_at = now
            if expiration is not None:
                record.expiration = expiration
            if decision == AccessRequestStatus.APPROVED:
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
