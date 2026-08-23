"""Create normalized control-plane tables.

Revision ID: 0001_control_plane
Revises: none
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_control_plane"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "memory_domains",
        sa.Column("id", sa.String(63), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_team", sa.String(255), nullable=False),
        sa.Column("owner_contact", sa.String(320)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("contract_version", sa.String(64), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "scope_definitions",
        sa.Column("id", sa.String(127), primary_key=True),
        sa.Column("scope_type", sa.String(64), nullable=False),
        sa.Column("scope_keys", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "owner_domain_id",
            sa.String(63),
            sa.ForeignKey("memory_domains.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "profile_schemas",
        sa.Column("id", sa.String(127), primary_key=True),
        sa.Column(
            "domain_id",
            sa.String(63),
            sa.ForeignKey("memory_domains.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_team", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "profile_schema_versions",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column(
            "schema_id",
            sa.String(127),
            sa.ForeignKey("profile_schemas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "scope_definition_id",
            sa.String(127),
            sa.ForeignKey("scope_definitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("vertex_schema_definition", sa.JSON(), nullable=False),
        sa.Column("generation_config", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("schema_id", "version"),
    )
    op.create_table(
        "preference_definitions",
        sa.Column("attribute_id", sa.String(191), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column("allowed_values", sa.JSON(), nullable=False),
        sa.Column("sensitivity_classification", sa.String(32), nullable=False),
        sa.Column(
            "canonical_owner_id",
            sa.String(63),
            sa.ForeignKey("memory_domains.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("validation_rules", sa.JSON(), nullable=False),
        sa.Column("default_resolution_behavior", sa.JSON(), nullable=False),
        sa.Column("catalog_version", sa.String(64), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "schema_preference_mappings",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "schema_version_id",
            sa.String(191),
            sa.ForeignKey("profile_schema_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attribute_id",
            sa.String(191),
            sa.ForeignKey("preference_definitions.attribute_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("profile_field", sa.String(127), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "schema_version_id",
            "attribute_id",
            name="uq_schema_preference_mapping_attribute",
        ),
        sa.UniqueConstraint(
            "schema_version_id",
            "profile_field",
            name="uq_schema_preference_mapping_field",
        ),
    )
    op.create_table(
        "registered_agents",
        sa.Column("id", sa.String(127), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "domain_id",
            sa.String(63),
            sa.ForeignKey("memory_domains.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("runtime_type", sa.String(64), nullable=False),
        sa.Column("identity_type", sa.String(64), nullable=False),
        sa.Column("principal", sa.String(512), unique=True),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "agent_schema_grants",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(127),
            sa.ForeignKey("registered_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schema_id",
            sa.String(127),
            sa.ForeignKey("profile_schemas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("permission", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approved_by", sa.String(255)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("agent_id", "schema_id"),
    )
    op.create_table(
        "access_requests",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column(
            "requesting_agent_id",
            sa.String(127),
            sa.ForeignKey("registered_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requesting_team", sa.String(255), nullable=False),
        sa.Column(
            "target_schema_id",
            sa.String(127),
            sa.ForeignKey("profile_schemas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_permission", sa.String(16), nullable=False),
        sa.Column("business_reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approved_by", sa.String(255)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("expiration", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_table(
        "resolution_policies",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(127),
            sa.ForeignKey("registered_agents.id", ondelete="CASCADE"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("default_rules", sa.JSON(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("agent_id", "version"),
    )
    op.create_table(
        "resolution_policy_schema_priorities",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "policy_id",
            sa.String(191),
            sa.ForeignKey("resolution_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schema_id",
            sa.String(127),
            sa.ForeignKey("profile_schemas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.UniqueConstraint("policy_id", "priority"),
    )
    op.create_table(
        "resolution_attribute_overrides",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "policy_id",
            sa.String(191),
            sa.ForeignKey("resolution_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attribute_id",
            sa.String(191),
            sa.ForeignKey("preference_definitions.attribute_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_precedence", sa.JSON(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.UniqueConstraint("policy_id", "attribute_id"),
    )
    op.create_table(
        "dynamic_memory_policies",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column("level", sa.String(32), nullable=False),
        sa.Column(
            "domain_id",
            sa.String(63),
            sa.ForeignKey("memory_domains.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "schema_id",
            sa.String(127),
            sa.ForeignKey("profile_schemas.id", ondelete="CASCADE"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("confidence_threshold", sa.Float(), nullable=False),
        sa.Column("memory_topics", sa.JSON(), nullable=False),
        sa.Column("retention_policy", sa.JSON(), nullable=False),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("allowed_dynamic_categories", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(127), nullable=False),
        sa.Column("target_type", sa.String(127), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("correlation_id", sa.String(191), nullable=False),
        sa.Column("before_metadata", sa.JSON()),
        sa.Column("after_metadata", sa.JSON()),
    )


def downgrade() -> None:
    for table_name in (
        "audit_events",
        "dynamic_memory_policies",
        "resolution_attribute_overrides",
        "resolution_policy_schema_priorities",
        "resolution_policies",
        "access_requests",
        "agent_schema_grants",
        "registered_agents",
        "schema_preference_mappings",
        "preference_definitions",
        "profile_schema_versions",
        "profile_schemas",
        "scope_definitions",
        "memory_domains",
    ):
        op.drop_table(table_name)
