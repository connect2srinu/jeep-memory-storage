from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_api.domain.control_plane import AccessPermission
from control_plane_api.domain.governance import PENDING_CONSENT_TTL
from control_plane_api.domain.household_identity import member_kind_for, normalize_name
from control_plane_api.domain.runtime import (
    HouseholdMember,
    RuntimeAgent,
    RuntimeDynamicPolicy,
    RuntimeResolutionConfig,
    RuntimeSchemaGrant,
)
from control_plane_api.persistence.models import (
    AgentSchemaGrantRecord,
    ConsentRecord,
    DynamicMemoryPolicyRecord,
    HouseholdMemberAliasRecord,
    HouseholdMemberRecord,
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

    async def get_member_by_login(
        self, organization_id: str, login_id: str
    ) -> HouseholdMember | None: ...

    async def create_household_root(
        self,
        *,
        organization_id: str,
        login_id: str,
        agent_id: str,
        session_id: str | None,
    ) -> HouseholdMember: ...

    async def list_household_members(
        self, organization_id: str, household_id: str, *, include_provisional: bool = False
    ) -> tuple[HouseholdMember, ...]: ...

    async def get_household_member(
        self,
        organization_id: str,
        household_id: str,
        member_id: str,
        *,
        include_provisional: bool = False,
    ) -> HouseholdMember | None: ...

    async def create_household_member(
        self,
        *,
        organization_id: str,
        household_id: str,
        display_name: str,
        normalized_name: str,
        relationship: str,
        member_kind: str,
        minor: bool,
        status: str,
        provenance: str,
        agent_id: str,
        match_confidence: float | None = None,
    ) -> HouseholdMember: ...

    async def update_household_member(
        self, organization_id: str, household_id: str, member_id: str, **changes: Any
    ) -> HouseholdMember: ...

    async def add_member_alias(
        self,
        organization_id: str,
        household_id: str,
        member_id: str,
        alias: str,
        source: str,
    ) -> None: ...

    async def move_member_aliases(
        self, organization_id: str, household_id: str, from_member_id: str, to_member_id: str
    ) -> None: ...

    async def create_pending_consent(
        self,
        *,
        organization_id: str,
        household_id: str | None,
        subject_member_id: str | None,
        granted_by_member_id: str,
        attribute_id: str,
        value_digest: str,
        prompt_text: str,
        agent_id: str,
    ) -> str: ...

    async def grant_pending_consent(
        self,
        *,
        organization_id: str,
        household_id: str | None,
        subject_member_id: str | None,
        attribute_id: str,
        value_digest: str,
    ) -> bool: ...

    async def withdraw_consents(
        self,
        *,
        organization_id: str,
        household_id: str | None,
        subject_member_id: str | None,
        attribute_id: str,
    ) -> int: ...

    async def upsert_household_member(
        self,
        *,
        organization_id: str,
        household_id: str,
        member_id: str,
        display_name: str | None,
        relationship: str,
        has_login: bool,
        is_guardian: bool,
    ) -> None: ...

    async def deactivate_household_member(
        self, *, organization_id: str, household_id: str, member_id: str
    ) -> bool: ...


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
            purpose=record.purpose or "personalization",
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
            attribute_descriptions: dict[str, str] = {}
            health_attributes: set[str] = set()
            for attribute_id in set(field_to_attribute.values()):
                definition = await self.session.get(PreferenceDefinitionRecord, attribute_id)
                if definition is not None:
                    attribute_sensitivity[attribute_id] = definition.sensitivity_classification
                    if definition.description:
                        attribute_descriptions[attribute_id] = definition.description
                    if (definition.validation_rules or {}).get("health"):
                        health_attributes.add(attribute_id)
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
                    attribute_descriptions=attribute_descriptions,
                    health_attributes=frozenset(health_attributes),
                    allowed_purposes=tuple(version.allowed_purposes or ("personalization",)),
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
        definitions = {
            str(topic): str(text)
            for topic, text in (record.topic_definitions or {}).items()
            if str(text).strip()
        }
        return RuntimeDynamicPolicy(
            policy_id=record.id,
            domain_id=domain_id,
            enabled=record.enabled,
            approved_topics=tuple(approved_topics),
            confidence_threshold=record.confidence_threshold,
            confirmation_required=record.confirmation_required,
            retention_days=retention.get("retention_days"),
            topic_sensitivity=topic_sensitivity,
            topic_descriptions=definitions,
        )

    @staticmethod
    def _to_household_member(
        record: HouseholdMemberRecord, aliases: tuple[str, ...] = ()
    ) -> HouseholdMember:
        return HouseholdMember(
            member_id=record.member_id,
            display_name=record.display_name,
            relationship=record.relationship,
            has_login=record.has_login,
            is_guardian=record.is_guardian,
            household_id=record.household_id,
            member_kind=record.member_kind,
            minor=record.minor,
            status=record.status,
            login_id=record.login_id,
            provenance=record.provenance,
            aliases=aliases,
        )

    async def _aliases(
        self, organization_id: str, household_id: str, member_id: str | None = None
    ) -> dict[str, tuple[str, ...]]:
        query = select(HouseholdMemberAliasRecord).where(
            HouseholdMemberAliasRecord.organization_id == organization_id,
            HouseholdMemberAliasRecord.household_id == household_id,
        )
        if member_id is not None:
            query = query.where(HouseholdMemberAliasRecord.member_id == member_id)
        grouped: dict[str, list[str]] = {}
        for item in await self.session.scalars(query.order_by(HouseholdMemberAliasRecord.alias)):
            grouped.setdefault(item.member_id, []).append(item.alias)
        return {key: tuple(values) for key, values in grouped.items()}

    @staticmethod
    def _statuses(include_provisional: bool) -> tuple[str, ...]:
        return ("active", "provisional") if include_provisional else ("active",)

    async def get_member_by_login(
        self, organization_id: str, login_id: str
    ) -> HouseholdMember | None:
        record = await self.session.scalar(
            select(HouseholdMemberRecord)
            .where(
                HouseholdMemberRecord.organization_id == organization_id,
                HouseholdMemberRecord.login_id == login_id,
                HouseholdMemberRecord.status == "active",
            )
            .limit(1)
        )
        if record is None:
            return None
        aliases = await self._aliases(organization_id, record.household_id, record.member_id)
        return self._to_household_member(record, aliases.get(record.member_id, ()))

    async def create_household_root(
        self,
        *,
        organization_id: str,
        login_id: str,
        agent_id: str,
        session_id: str | None,
    ) -> HouseholdMember:
        """Create a household and its root member for a login on first use.

        Surrogate ids decouple identity from the login. A concurrent first request for the same
        login loses the unique-login race and reuses the winner's household.
        """
        record = HouseholdMemberRecord(
            organization_id=organization_id,
            household_id=f"hh_{uuid4().hex[:16]}",
            member_id=f"mbr_{uuid4().hex[:16]}",
            display_name=None,
            relationship="account_holder",
            has_login=True,
            is_guardian=True,
            status="active",
            member_kind="ROOT",
            minor=False,
            login_id=login_id,
            provenance="AUTHENTICATED",
            created_by_agent_id=agent_id,
            source_session_id=session_id,
            confirmed_at=datetime.now(UTC),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(record)
        except IntegrityError:
            existing = await self.get_member_by_login(organization_id, login_id)
            if existing is None:
                raise
            return existing
        return self._to_household_member(record)

    async def list_household_members(
        self, organization_id: str, household_id: str, *, include_provisional: bool = False
    ) -> tuple[HouseholdMember, ...]:
        records = await self.session.scalars(
            select(HouseholdMemberRecord)
            .where(
                HouseholdMemberRecord.organization_id == organization_id,
                HouseholdMemberRecord.household_id == household_id,
                HouseholdMemberRecord.status.in_(self._statuses(include_provisional)),
            )
            .order_by(HouseholdMemberRecord.member_id)
        )
        aliases = await self._aliases(organization_id, household_id)
        return tuple(
            self._to_household_member(record, aliases.get(record.member_id, ()))
            for record in records
        )

    async def get_household_member(
        self,
        organization_id: str,
        household_id: str,
        member_id: str,
        *,
        include_provisional: bool = False,
    ) -> HouseholdMember | None:
        record = await self.session.get(
            HouseholdMemberRecord, (organization_id, household_id, member_id)
        )
        if record is None or record.status not in self._statuses(include_provisional):
            return None
        aliases = await self._aliases(organization_id, household_id, member_id)
        return self._to_household_member(record, aliases.get(member_id, ()))

    async def create_household_member(
        self,
        *,
        organization_id: str,
        household_id: str,
        display_name: str,
        normalized_name: str,
        relationship: str,
        member_kind: str,
        minor: bool,
        status: str,
        provenance: str,
        agent_id: str,
        match_confidence: float | None = None,
    ) -> HouseholdMember:
        record = HouseholdMemberRecord(
            organization_id=organization_id,
            household_id=household_id,
            member_id=f"mbr_{uuid4().hex[:16]}",
            display_name=display_name,
            normalized_name=normalized_name,
            relationship=relationship,
            has_login=False,
            is_guardian=False,
            status=status,
            member_kind=member_kind,
            minor=minor,
            provenance=provenance,
            match_confidence=match_confidence,
            created_by_agent_id=agent_id,
            confirmed_at=datetime.now(UTC) if status == "active" else None,
        )
        self.session.add(record)
        await self.session.flush()
        return self._to_household_member(record)

    async def update_household_member(
        self, organization_id: str, household_id: str, member_id: str, **changes: Any
    ) -> HouseholdMember:
        record = await self.session.get(
            HouseholdMemberRecord, (organization_id, household_id, member_id)
        )
        if record is None:
            raise LookupError(f"member {member_id!r} was not found in household {household_id!r}")
        for key, value in changes.items():
            setattr(record, key, value)
        await self.session.flush()
        aliases = await self._aliases(organization_id, household_id, member_id)
        return self._to_household_member(record, aliases.get(member_id, ()))

    async def add_member_alias(
        self,
        organization_id: str,
        household_id: str,
        member_id: str,
        alias: str,
        source: str,
    ) -> None:
        if not alias:
            return
        key = (organization_id, household_id, member_id, alias)
        if await self.session.get(HouseholdMemberAliasRecord, key) is None:
            self.session.add(
                HouseholdMemberAliasRecord(
                    organization_id=organization_id,
                    household_id=household_id,
                    member_id=member_id,
                    alias=alias,
                    source=source,
                )
            )
            await self.session.flush()

    async def move_member_aliases(
        self, organization_id: str, household_id: str, from_member_id: str, to_member_id: str
    ) -> None:
        moved = await self._aliases(organization_id, household_id, from_member_id)
        for alias in moved.get(from_member_id, ()):
            await self.add_member_alias(
                organization_id, household_id, to_member_id, alias, "merge"
            )
        records = await self.session.scalars(
            select(HouseholdMemberAliasRecord).where(
                HouseholdMemberAliasRecord.organization_id == organization_id,
                HouseholdMemberAliasRecord.household_id == household_id,
                HouseholdMemberAliasRecord.member_id == from_member_id,
            )
        )
        for record in records:
            await self.session.delete(record)
        await self.session.flush()

    @staticmethod
    def _consent_filter(
        organization_id: str,
        household_id: str | None,
        subject_member_id: str | None,
        attribute_id: str,
    ) -> list[Any]:
        return [
            ConsentRecord.organization_id == organization_id,
            ConsentRecord.household_id.is_(None)
            if household_id is None
            else ConsentRecord.household_id == household_id,
            ConsentRecord.subject_member_id.is_(None)
            if subject_member_id is None
            else ConsentRecord.subject_member_id == subject_member_id,
            ConsentRecord.attribute_id == attribute_id,
        ]

    async def create_pending_consent(
        self,
        *,
        organization_id: str,
        household_id: str | None,
        subject_member_id: str | None,
        granted_by_member_id: str,
        attribute_id: str,
        value_digest: str,
        prompt_text: str,
        agent_id: str,
    ) -> str:
        consent_id = f"cns_{uuid4().hex}"
        self.session.add(
            ConsentRecord(
                id=consent_id,
                organization_id=organization_id,
                household_id=household_id,
                subject_member_id=subject_member_id,
                granted_by_member_id=granted_by_member_id,
                category="health",
                attribute_id=attribute_id,
                value_digest=value_digest,
                prompt_text=prompt_text,
                status="PENDING",
                agent_id=agent_id,
                requested_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return consent_id

    async def grant_pending_consent(
        self,
        *,
        organization_id: str,
        household_id: str | None,
        subject_member_id: str | None,
        attribute_id: str,
        value_digest: str,
    ) -> bool:
        """Turn the matching unexpired PENDING consent into GRANTED. False if none is pending."""
        cutoff = datetime.now(UTC) - PENDING_CONSENT_TTL
        record = await self.session.scalar(
            select(ConsentRecord)
            .where(
                *self._consent_filter(
                    organization_id, household_id, subject_member_id, attribute_id
                ),
                ConsentRecord.value_digest == value_digest,
                ConsentRecord.status == "PENDING",
                ConsentRecord.requested_at >= cutoff,
            )
            .order_by(ConsentRecord.requested_at.desc())
            .limit(1)
        )
        if record is None:
            return False
        record.status = "GRANTED"
        record.granted_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def withdraw_consents(
        self,
        *,
        organization_id: str,
        household_id: str | None,
        subject_member_id: str | None,
        attribute_id: str,
    ) -> int:
        result = await self.session.execute(
            update(ConsentRecord)
            .where(
                *self._consent_filter(
                    organization_id, household_id, subject_member_id, attribute_id
                ),
                ConsentRecord.status.in_(("GRANTED", "PENDING")),
            )
            .values(status="WITHDRAWN", withdrawn_at=datetime.now(UTC))
        )
        return result.rowcount or 0

    async def upsert_household_member(
        self,
        *,
        organization_id: str,
        household_id: str,
        member_id: str,
        display_name: str | None,
        relationship: str,
        has_login: bool,
        is_guardian: bool,
    ) -> None:
        # Operator enrolment: a member with a login signs in with its member id.
        member_kind, minor = member_kind_for(relationship, has_login=has_login)
        fields = {
            "display_name": display_name,
            "normalized_name": normalize_name(display_name) if display_name else None,
            "relationship": relationship,
            "has_login": has_login,
            "is_guardian": is_guardian,
            "status": "active",
            "member_kind": member_kind,
            "minor": minor,
            "login_id": member_id if has_login else None,
            "provenance": "ADMIN",
        }
        record = await self.session.get(
            HouseholdMemberRecord, (organization_id, household_id, member_id)
        )
        if record is None:
            self.session.add(
                HouseholdMemberRecord(
                    organization_id=organization_id,
                    household_id=household_id,
                    member_id=member_id,
                    confirmed_at=datetime.now(UTC),
                    **fields,
                )
            )
        else:
            for key, value in fields.items():
                setattr(record, key, value)
        await self.session.flush()

    async def deactivate_household_member(
        self, *, organization_id: str, household_id: str, member_id: str
    ) -> bool:
        record = await self.session.get(
            HouseholdMemberRecord, (organization_id, household_id, member_id)
        )
        if record is None or record.status != "active":
            return False
        record.status = "inactive"
        return True
