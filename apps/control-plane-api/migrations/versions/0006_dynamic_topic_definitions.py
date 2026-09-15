"""Add per-topic definitions to dynamic memory policies.

Revision ID: 0006_dynamic_topic_definitions
Revises: 0005_org_settings_agent_health
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_dynamic_topic_definitions"
down_revision = "0005_org_settings_agent_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dynamic_memory_policies",
        sa.Column("topic_definitions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("dynamic_memory_policies", "topic_definitions")
