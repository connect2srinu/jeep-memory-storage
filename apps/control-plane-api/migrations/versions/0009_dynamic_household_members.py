"""Dynamic household members: roster identity fields, aliases, consent ledger, purpose, retention.

Revision ID: 0009_dynamic_household_members
Revises: 0008_household_members
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_dynamic_household_members"
down_revision = "0008_household_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("household_members") as table:
        table.add_column(
            sa.Column(
                "member_kind", sa.String(length=32), nullable=False, server_default="PROXY_ADULT"
            )
        )
        table.add_column(
            sa.Column("minor", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        table.add_column(sa.Column("login_id", sa.String(length=255), nullable=True))
        table.add_column(sa.Column("normalized_name", sa.String(length=255), nullable=True))
        table.add_column(
            sa.Column("provenance", sa.String(length=32), nullable=False, server_default="ADMIN")
        )
        table.add_column(sa.Column("match_confidence", sa.Float(), nullable=True))
        table.add_column(sa.Column("authoritative_id", sa.String(length=255), nullable=True))
        table.add_column(sa.Column("merged_into_member_id", sa.String(length=255), nullable=True))
        table.add_column(sa.Column("created_by_agent_id", sa.String(length=127), nullable=True))
        table.add_column(sa.Column("source_session_id", sa.String(length=255), nullable=True))
        table.add_column(sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "uq_household_members_login",
        "household_members",
        ["organization_id", "login_id"],
        unique=True,
        postgresql_where=sa.text("login_id IS NOT NULL"),
    )
    op.create_index(
        "ix_household_members_name",
        "household_members",
        ["organization_id", "household_id", "normalized_name"],
    )

    op.create_table(
        "household_member_aliases",
        sa.Column("organization_id", sa.String(length=127), nullable=False),
        sa.Column("household_id", sa.String(length=255), nullable=False),
        sa.Column("member_id", sa.String(length=255), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="match"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "household_id",
            "member_id",
            "alias",
            name="pk_household_member_aliases",
        ),
    )
    op.create_index(
        "ix_household_member_aliases_alias",
        "household_member_aliases",
        ["organization_id", "household_id", "alias"],
    )

    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=127), nullable=False),
        sa.Column("household_id", sa.String(length=255), nullable=True),
        sa.Column("subject_member_id", sa.String(length=255), nullable=True),
        sa.Column("granted_by_member_id", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="health"),
        sa.Column("attribute_id", sa.String(length=191), nullable=False),
        sa.Column("value_digest", sa.String(length=64), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("agent_id", sa.String(length=127), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_consent_records"),
    )
    op.create_index(
        "ix_consent_records_household", "consent_records", ["organization_id", "household_id"]
    )

    with op.batch_alter_table("profile_schema_versions") as table:
        table.add_column(sa.Column("retention_days", sa.Integer(), nullable=True))
        table.add_column(
            sa.Column(
                "allowed_purposes",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[\"personalization\"]'"),
            )
        )
    with op.batch_alter_table("registered_agents") as table:
        table.add_column(
            sa.Column(
                "purpose", sa.String(length=32), nullable=False, server_default="personalization"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("registered_agents") as table:
        table.drop_column("purpose")
    with op.batch_alter_table("profile_schema_versions") as table:
        table.drop_column("allowed_purposes")
        table.drop_column("retention_days")
    op.drop_index("ix_consent_records_household", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_index("ix_household_member_aliases_alias", table_name="household_member_aliases")
    op.drop_table("household_member_aliases")
    op.drop_index("ix_household_members_name", table_name="household_members")
    op.drop_index("uq_household_members_login", table_name="household_members")
    with op.batch_alter_table("household_members") as table:
        for column in (
            "confirmed_at",
            "source_session_id",
            "created_by_agent_id",
            "merged_into_member_id",
            "authoritative_id",
            "match_confidence",
            "provenance",
            "normalized_name",
            "login_id",
            "minor",
            "member_kind",
        ):
            table.drop_column(column)
