"""Attribute-level schema grants: an access request and its grant can name the attributes shared.

Revision ID: 0010_attribute_level_grants
Revises: 0009_dynamic_household_members
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_attribute_level_grants"
down_revision = "0009_dynamic_household_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("access_requests", "agent_schema_grants"):
        with op.batch_alter_table(table_name) as table:
            table.add_column(sa.Column("attributes", sa.JSON(), nullable=True))


def downgrade() -> None:
    for table_name in ("agent_schema_grants", "access_requests"):
        with op.batch_alter_table(table_name) as table:
            table.drop_column("attributes")
