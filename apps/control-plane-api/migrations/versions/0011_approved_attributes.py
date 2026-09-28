"""Per-attribute approval: record which requested attributes the owner approved.

Revision ID: 0011_approved_attributes
Revises: 0010_attribute_level_grants
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_approved_attributes"
down_revision = "0010_attribute_level_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("access_requests") as table:
        table.add_column(sa.Column("approved_attributes", sa.JSON(), nullable=True))
    # Requests approved before this revision granted everything they asked for.
    op.execute(
        "UPDATE access_requests SET approved_attributes = attributes "
        "WHERE status IN ('APPROVED', 'REVOKED', 'EXPIRED') AND attributes IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("access_requests") as table:
        table.drop_column("approved_attributes")
