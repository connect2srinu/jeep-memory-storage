"""Add the household_members roster (household-scoped memory).

Revision ID: 0008_household_members
Revises: 0006_dynamic_topic_definitions
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_household_members"
down_revision = "0006_dynamic_topic_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "household_members",
        sa.Column("organization_id", sa.String(length=127), nullable=False),
        sa.Column("household_id", sa.String(length=255), nullable=False),
        sa.Column("member_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("relationship", sa.String(length=64), nullable=False, server_default="member"),
        sa.Column("has_login", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_guardian", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "household_id", "member_id", name="pk_household_members"
        ),
    )
    op.create_index(
        "ix_household_members_member", "household_members", ["organization_id", "member_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_household_members_member", table_name="household_members")
    op.drop_table("household_members")
