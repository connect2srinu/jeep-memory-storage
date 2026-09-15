from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_api.domain.control_plane import AccessPermission
from control_plane_api.domain.runtime import (
    RuntimeAgent,
    RuntimeDynamicPolicy,
    RuntimeResolutionConfig,
    RuntimeSchemaGrant,
)
from control_plane_api.persistence.models import (
    AgentSchemaGrantRecord,
    DynamicMemoryPolicyRecord,
    MemoryDomainRecord,
    PreferenceDefinitionRecord,
    ProfileSchemaRecord,
    ProfileSchemaVersionRecord,
    RegisteredAgentRecord,
    ResolutionAttributeOverrideRecord,
    ResolutionPolicyRecord,
    SchemaPreferenceMappingRecord,
    ScopeDefinitionRecord,
)


class RuntimeControlPlaneRepository(Protocol):
    async def resolve_agent(
        self, *, principal: str, local_agent_id: str | None = None
    ) -> RuntimeAgent | None: ...

    async def list_schema_grants(self, agent_id: str) -> tuple[RuntimeSchemaGrant, ...]: ...

    async def get_resolution_config(
        self, agent_id: str, domain_id: str
    ) -> RuntimeResolutionConfig | None: ...

    async def get_dynamic_memory_policy(
        self, domain_id: str
    ) -> RuntimeDynamicPolicy | None: ...


class SqlAlchemyRuntimeControlPlaneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve_agent(
        self, *, principal: str, local_agent_id: str | None = None
    ) -> RuntimeAgent | None:
        query = select(RegisteredAgentRecord).where(RegisteredAgentRecord.status == "ACTIVE")
        query = query.where(
            RegisteredAgentRecord.id == local_agent_id
            if local_agent_id
            else RegisteredAgentRecord.principal == principal
        )
        record = await self.session.scalar(query)
        if record is None:
            return None
        return RuntimeAgent(
            id=record.id,
            organization_id=record.organization_id,
            project_id=record.project_id,
            domain_id=record.domain_id,
            principal=record.principal,
            capabilities=frozenset(
                name for name, enabled in record.capabilities.items() if enabled
            ),
        )

    async def list_schema_grants(self, agent_id: str) -> tuple[RuntimeSchemaGrant, ...]:
        now = datetime.now(UTC)
        grant_rows = (
            await self.session.scalars(
                select(AgentSchemaGrantRecord)
                .where(
                    AgentSchemaGrantRecord.agent_id == agent_id,
                    AgentSchemaGrantRecord.status == "ACTIVE",
                    or_(
                        AgentSchemaGrantRecord.expires_at.is_(None),
                        AgentSchemaGrantRecord.expires_at > now,
                    ),
                )
                .order_by(AgentSchemaGrantRecord.schema_id)
            )
        ).all()
        result = []
        for grant in grant_rows:
            schema = await self.session.get(ProfileSchemaRecord, grant.schema_id)
            if schema is None or schema.status != "ACTIVE":
                continue
            domain = await self.session.get(MemoryDomainRecord, schema.domain_id)
            if domain is None or domain.status != "ACTIVE":
                continue
            version = await self.session.scalar(
                select(ProfileSchemaVersionRecord)
                .where(
                    ProfileSchemaVersionRecord.schema_id == schema.id,
                    ProfileSchemaVersionRecord.status == "ACTIVE",
                )
                .order_by(ProfileSchemaVersionRecord.version.desc())
                .limit(1)
            )
            if version is None:
                continue
            scope = await self.session.get(ScopeDefinitionRecord, version.scope_definition_id)
            if scope is None or scope.status != "ACTIVE":
                continue
            mappings = (
                await self.session.scalars(
                    select(SchemaPreferenceMappingRecord)
                    .where(SchemaPreferenceMappingRecord.schema_version_id == version.id)
                    .order_by(SchemaPreferenceMappingRecord.profile_field)
                )
            ).all()
            field_to_attribute = {item.profile_field: item.attribute_id for item in mappings}
            attribute_sensitivity: dict[str, str] = {}
            for attribute_id in set(field_to_attribute.values()):
                definition = await self.session.get(PreferenceDefinitionRecord, attribute_id)
                if definition is not None:
                    attribute_sensitivity[attribute_id] = definition.sensitivity_classification
            result.append(
                RuntimeSchemaGrant(
                    schema_id=schema.id,
                    owner_organization_id=domain.organization_id,
                    domain_id=schema.domain_id,
                    schema_version=version.version,
                    permission=AccessPermission(grant.permission),
                    scope_keys=tuple(scope.scope_keys),
                    field_to_attribute=field_to_attribute,
                    attribute_sensitivity=attribute_sensitivity,
                )
            )
        return tuple(result)

    async def get_resolution_config(
        self, agent_id: str, domain_id: str
    ) -> RuntimeResolutionConfig | None:
        policy = await self.session.scalar(
            select(ResolutionPolicyRecord)
            .where(
                ResolutionPolicyRecord.status == "ACTIVE",
                or_(
                    ResolutionPolicyRecord.agent_id == agent_id,
                    ResolutionPolicyRecord.id.like(f"{domain_id}:%"),
                ),
            )
            .order_by(ResolutionPolicyRecord.agent_id.desc().nullslast())
            .limit(1)
        )
        if policy is None:
            return None
        overrides = (
            await self.session.scalars(
                select(ResolutionAttributeOverrideRecord)
                .where(ResolutionAttributeOverrideRecord.policy_id == policy.id)
                .order_by(ResolutionAttributeOverrideRecord.attribute_id)
            )
        ).all()
        return RuntimeResolutionConfig(
            policy_id=policy.id,
            version=policy.version,
            defaults=dict(policy.default_rules),
            attribute_rules={
                item.attribute_id: {
                    **item.rules,
                    "schema_precedence": list(item.schema_precedence),
                }
                for item in overrides
            },
        )

    async def get_dynamic_memory_policy(self, domain_id: str) -> RuntimeDynamicPolicy | None:
        # Schema-scoped policies (if any) take precedence over the domain-level policy.
        record = await self.session.scalar(
            select(DynamicMemoryPolicyRecord)
            .where(
                DynamicMemoryPolicyRecord.status == "ACTIVE",
                DynamicMemoryPolicyRecord.domain_id == domain_id,
            )
            .order_by(DynamicMemoryPolicyRecord.schema_id.desc().nullslast())
            .limit(1)
        )
        if record is None:
            return None
        retention = record.retention_policy or {}
        # Each memory_topics entry is "topic" (defaults to normal) or "topic:tier" where tier is a
        # declared sensitivity classification (normal | sensitive | restricted).
        approved_topics: list[str] = []
        topic_sensitivity: dict[str, str] = {}
        for entry in record.memory_topics or ():
            topic, _, tier = str(entry).partition(":")
            topic = topic.strip()
            if not topic:
                continue
            approved_topics.append(topic)
            tier = tier.strip().lower()
            if tier in {"normal", "sensitive", "restricted"}:
                topic_sensitivity[topic] = tier
        return RuntimeDynamicPolicy(
            policy_id=record.id,
            domain_id=domain_id,
            enabled=record.enabled,
            approved_topics=tuple(approved_topics),
            confidence_threshold=record.confidence_threshold,
            confirmation_required=record.confirmation_required,
            retention_days=retention.get("retention_days"),
            topic_sensitivity=topic_sensitivity,
        )
