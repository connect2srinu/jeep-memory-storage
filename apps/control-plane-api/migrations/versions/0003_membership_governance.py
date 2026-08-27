"""Add organization and project memberships.

Revision ID: 0003_membership_governance
Revises: 0002_org_project_governance
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_membership_governance"
down_revision = "0002_org_project_governance"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
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
        "organization_memberships",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(63),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_principal", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "organization_id",
            "member_principal",
            name="uq_organization_memberships_organization_id",
        ),
    )
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.String(191), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(63),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_principal", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "project_id",
            "member_principal",
            name="uq_project_memberships_project_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("project_memberships")
    op.drop_table("organization_memberships")
