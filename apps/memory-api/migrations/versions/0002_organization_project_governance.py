"""Add organization and project governance boundaries.

Revision ID: 0002_org_project_governance
Revises: 0001_control_plane
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_org_project_governance"
down_revision = "0001_control_plane"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(63), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_contact", sa.String(320)),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String(63), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(63),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_team", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("organization_id", "name", name="uq_projects_organization_id"),
    )

    op.execute(
        "INSERT INTO organizations (id, name, description, status) "
        "VALUES ('default-org', 'Default Organization', "
        "'Migrated control-plane organization', 'ACTIVE')"
    )
    op.execute(
        "INSERT INTO projects (id, organization_id, name, description, owner_team, status) "
        "VALUES ('default-project', 'default-org', 'Default Project', "
        "'Migrated control-plane project', 'platform-team', 'ACTIVE')"
    )

    for table in ("memory_domains", "registered_agents"):
        op.add_column(table, sa.Column("organization_id", sa.String(63), nullable=True))
        op.add_column(table, sa.Column("project_id", sa.String(63), nullable=True))
        op.execute(
            sa.text(
                f"UPDATE {table} SET organization_id = 'default-org', "
                "project_id = 'default-project'"
            )
        )
        op.alter_column(table, "organization_id", nullable=False)
        op.alter_column(table, "project_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_organization_id_organizations",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_foreign_key(
            f"fk_{table}_project_id_projects",
            table,
            "projects",
            ["project_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.execute(
        "UPDATE scope_definitions "
        "SET scope_keys = '[\"organization_id\", \"user_id\"]'"
    )


def downgrade() -> None:
    for table in ("registered_agents", "memory_domains"):
        op.drop_constraint(f"fk_{table}_project_id_projects", table, type_="foreignkey")
        op.drop_constraint(
            f"fk_{table}_organization_id_organizations", table, type_="foreignkey"
        )
        op.drop_column(table, "project_id")
        op.drop_column(table, "organization_id")
    op.drop_table("projects")
    op.drop_table("organizations")
