"""Add the member_dependents roster (Option C — dependent-scoped memory).

Revision ID: 0007_member_dependents
Revises: 0006_dynamic_topic_definitions
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_member_dependents"
down_revision = "0006_dynamic_topic_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_dependents",
        sa.Column("organization_id", sa.String(length=127), nullable=False),
        sa.Column("member_user_id", sa.String(length=255), nullable=False),
        sa.Column("dependent_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("relationship", sa.String(length=64), nullable=False, server_default="child"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "member_user_id", "dependent_id", name="pk_member_dependents"
        ),
    )


def downgrade() -> None:
    op.drop_table("member_dependents")
