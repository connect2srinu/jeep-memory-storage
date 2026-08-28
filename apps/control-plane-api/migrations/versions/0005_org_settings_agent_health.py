"""Add organization governance settings and project agent health.

Revision ID: 0005_org_settings_agent_health
Revises: 0004_resource_change_approvals
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_org_settings_agent_health"
down_revision = "0004_resource_change_approvals"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "organization_settings",
        sa.Column(
            "organization_id",
            sa.String(63),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("budget_amount", sa.Float()),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("budget_period", sa.String(16), nullable=False),
        sa.Column("budget_enabled", sa.Boolean(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("email_recipients", sa.JSON(), nullable=False),
        sa.Column("monitoring_channel_ids", sa.JSON(), nullable=False),
        sa.Column("pubsub_topic", sa.String(512)),
        sa.Column("billing_account_id", sa.String(128)),
        sa.Column("billing_project_ids", sa.JSON(), nullable=False),
        sa.Column("external_budget_name", sa.String(512)),
        sa.Column("sync_status", sa.String(32), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "project_settings",
        sa.Column(
            "project_id",
            sa.String(63),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("health_refresh_seconds", sa.Integer(), nullable=False),
        sa.Column("latency_warning_ms", sa.Float(), nullable=False),
        sa.Column("error_rate_warning", sa.Float(), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False),
        sa.Column("notification_channel_ids", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "agent_runtime_bindings",
        sa.Column(
            "agent_id",
            sa.String(191),
            sa.ForeignKey("registered_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("gcp_project_id", sa.String(63)),
        sa.Column("location", sa.String(64)),
        sa.Column("resource_name", sa.String(512)),
        sa.Column("endpoint_url", sa.String(1024)),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "agent_health_snapshots",
        sa.Column(
            "agent_id",
            sa.String(191),
            sa.ForeignKey("registered_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("health_status", sa.String(32), nullable=False),
        sa.Column("provider_status", sa.String(64), nullable=False),
        sa.Column("request_count", sa.Integer()),
        sa.Column("error_rate", sa.Float()),
        sa.Column("p95_latency_ms", sa.Float()),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("agent_health_snapshots")
    op.drop_table("agent_runtime_bindings")
    op.drop_table("project_settings")
    op.drop_table("organization_settings")
