from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OrganizationRecord(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(63), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_contact: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class ProjectRecord(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    id: Mapped[str] = mapped_column(String(63), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_team: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class OrganizationMembershipRecord(TimestampMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("organization_id", "member_principal"),)

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    member_principal: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class ProjectMembershipRecord(TimestampMixin, Base):
    __tablename__ = "project_memberships"
    __table_args__ = (UniqueConstraint("project_id", "member_principal"),)

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    member_principal: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class OrganizationSettingsRecord(TimestampMixin, Base):
    __tablename__ = "organization_settings"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    budget_amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    budget_period: Mapped[str] = mapped_column(String(16), nullable=False, default="MONTHLY")
    budget_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thresholds: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    email_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    monitoring_channel_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    pubsub_topic: Mapped[str | None] = mapped_column(String(512))
    billing_account_id: Mapped[str | None] = mapped_column(String(128))
    billing_project_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    external_budget_name: Mapped[str | None] = mapped_column(String(512))
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="LOCAL_ONLY")


class ProjectSettingsRecord(TimestampMixin, Base):
    __tablename__ = "project_settings"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    health_refresh_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    latency_warning_ms: Mapped[float] = mapped_column(Float, nullable=False, default=2000)
    error_rate_warning: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notification_channel_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class AgentRuntimeBindingRecord(TimestampMixin, Base):
    __tablename__ = "agent_runtime_bindings"

    agent_id: Mapped[str] = mapped_column(
        ForeignKey("registered_agents.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    gcp_project_id: Mapped[str | None] = mapped_column(String(63))
    location: Mapped[str | None] = mapped_column(String(64))
    resource_name: Mapped[str | None] = mapped_column(String(512))
    endpoint_url: Mapped[str | None] = mapped_column(String(1024))
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="development")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CONFIGURED")


class AgentHealthSnapshotRecord(TimestampMixin, Base):
    __tablename__ = "agent_health_snapshots"

    agent_id: Mapped[str] = mapped_column(
        ForeignKey("registered_agents.id", ondelete="CASCADE"), primary_key=True
    )
    health_status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(64), nullable=False)
    request_count: Mapped[int | None] = mapped_column(Integer)
    error_rate: Mapped[float | None] = mapped_column(Float)
    p95_latency_ms: Mapped[float | None] = mapped_column(Float)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class MemoryDomainRecord(TimestampMixin, Base):
    __tablename__ = "memory_domains"

    id: Mapped[str] = mapped_column(String(63), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_team: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_contact: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0")


class ScopeDefinitionRecord(TimestampMixin, Base):
    __tablename__ = "scope_definitions"

    id: Mapped[str] = mapped_column(String(127), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_domain_id: Mapped[str] = mapped_column(
        ForeignKey("memory_domains.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class ProfileSchemaRecord(TimestampMixin, Base):
    __tablename__ = "profile_schemas"

    id: Mapped[str] = mapped_column(String(127), primary_key=True)
    domain_id: Mapped[str] = mapped_column(
        ForeignKey("memory_domains.id", ondelete="RESTRICT"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner_team: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class ProfileSchemaVersionRecord(TimestampMixin, Base):
    __tablename__ = "profile_schema_versions"
    __table_args__ = (UniqueConstraint("schema_id", "version"),)

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    schema_id: Mapped[str] = mapped_column(
        ForeignKey("profile_schemas.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    scope_definition_id: Mapped[str] = mapped_column(
        ForeignKey("scope_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    vertex_schema_definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generation_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class PreferenceDefinitionRecord(TimestampMixin, Base):
    __tablename__ = "preference_definitions"

    attribute_id: Mapped[str] = mapped_column(String(191), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_values: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    sensitivity_classification: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_owner_id: Mapped[str] = mapped_column(
        ForeignKey("memory_domains.id", ondelete="RESTRICT"), nullable=False
    )
    validation_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    default_resolution_behavior: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")


class SchemaPreferenceMappingRecord(TimestampMixin, Base):
    __tablename__ = "schema_preference_mappings"
    __table_args__ = (
        UniqueConstraint(
            "schema_version_id",
            "attribute_id",
            name="uq_schema_preference_mapping_attribute",
        ),
        UniqueConstraint(
            "schema_version_id",
            "profile_field",
            name="uq_schema_preference_mapping_field",
        ),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    schema_version_id: Mapped[str] = mapped_column(
        ForeignKey("profile_schema_versions.id", ondelete="CASCADE"), nullable=False
    )
    attribute_id: Mapped[str] = mapped_column(
        ForeignKey("preference_definitions.attribute_id", ondelete="RESTRICT"), nullable=False
    )
    profile_field: Mapped[str] = mapped_column(String(127), nullable=False)


class RegisteredAgentRecord(TimestampMixin, Base):
    __tablename__ = "registered_agents"

    id: Mapped[str] = mapped_column(String(127), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    domain_id: Mapped[str] = mapped_column(
        ForeignKey("memory_domains.id", ondelete="RESTRICT"), nullable=False
    )
    runtime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    principal: Mapped[str | None] = mapped_column(String(512), unique=True)
    capabilities: Mapped[dict[str, bool]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class AgentSchemaGrantRecord(TimestampMixin, Base):
    __tablename__ = "agent_schema_grants"
    __table_args__ = (UniqueConstraint("agent_id", "schema_id"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("registered_agents.id", ondelete="CASCADE"), nullable=False
    )
    schema_id: Mapped[str] = mapped_column(
        ForeignKey("profile_schemas.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccessRequestRecord(TimestampMixin, Base):
    __tablename__ = "access_requests"

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    requesting_agent_id: Mapped[str] = mapped_column(
        ForeignKey("registered_agents.id", ondelete="CASCADE"), nullable=False
    )
    requesting_team: Mapped[str] = mapped_column(String(255), nullable=False)
    target_schema_id: Mapped[str] = mapped_column(
        ForeignKey("profile_schemas.id", ondelete="CASCADE"), nullable=False
    )
    requested_permission: Mapped[str] = mapped_column(String(16), nullable=False)
    business_reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResourceChangeRequestRecord(TimestampMixin, Base):
    __tablename__ = "resource_change_requests"

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(191), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    domain_id: Mapped[str] = mapped_column(
        ForeignKey("memory_domains.id", ondelete="CASCADE"), nullable=False
    )
    before_values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    proposed_changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)


class ResolutionPolicyRecord(TimestampMixin, Base):
    __tablename__ = "resolution_policies"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("registered_agents.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    default_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ResolutionPolicySchemaPriorityRecord(Base):
    __tablename__ = "resolution_policy_schema_priorities"
    __table_args__ = (UniqueConstraint("policy_id", "priority"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("resolution_policies.id", ondelete="CASCADE"), nullable=False
    )
    schema_id: Mapped[str] = mapped_column(
        ForeignKey("profile_schemas.id", ondelete="CASCADE"), nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)


class ResolutionAttributeOverrideRecord(Base):
    __tablename__ = "resolution_attribute_overrides"
    __table_args__ = (UniqueConstraint("policy_id", "attribute_id"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("resolution_policies.id", ondelete="CASCADE"), nullable=False
    )
    attribute_id: Mapped[str] = mapped_column(
        ForeignKey("preference_definitions.attribute_id", ondelete="CASCADE"), nullable=False
    )
    schema_precedence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class DynamicMemoryPolicyRecord(TimestampMixin, Base):
    __tablename__ = "dynamic_memory_policies"

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    domain_id: Mapped[str | None] = mapped_column(
        ForeignKey("memory_domains.id", ondelete="CASCADE")
    )
    schema_id: Mapped[str | None] = mapped_column(
        ForeignKey("profile_schemas.id", ondelete="CASCADE")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    memory_topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    retention_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allowed_dynamic_categories: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(191), primary_key=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(127), nullable=False)
    target_type: Mapped[str] = mapped_column(String(127), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(191), nullable=False)
    before_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
