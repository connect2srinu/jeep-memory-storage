"""Add approval requests for governed resource changes.

Revision ID: 0004_resource_change_approvals
Revises: 0003_membership_governance
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_resource_change_approvals"
down_revision = "0003_membership_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_change_requests",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(191), nullable=False),
        sa.Column(
            "organization_id",
            sa.String(63),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(63),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "domain_id",
            sa.String(63),
            sa.ForeignKey("memory_domains.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("before_values", sa.JSON(), nullable=False),
        sa.Column("proposed_changes", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decided_by", sa.String(255)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_resource_change_requests_target_status",
        "resource_change_requests",
        ["resource_type", "resource_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resource_change_requests_target_status", table_name="resource_change_requests"
    )
    op.drop_table("resource_change_requests")
