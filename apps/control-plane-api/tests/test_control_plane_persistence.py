from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from control_plane_api.persistence import Database, SqlAlchemyControlPlaneRepository
from control_plane_api.persistence.models import (
    AgentSchemaGrantRecord,
    AuditEventRecord,
    Base,
    MemoryDomainRecord,
    PreferenceDefinitionRecord,
    ProfileSchemaRecord,
    RegisteredAgentRecord,
)
from db_seed import PREFERENCES, seed_control_plane
from sqlalchemy import func, select


def test_normalized_control_plane_tables_are_declared() -> None:
    assert {
        "memory_domains",
        "profile_schemas",
        "profile_schema_versions",
        "preference_definitions",
        "schema_preference_mappings",
        "scope_definitions",
        "registered_agents",
        "agent_schema_grants",
        "access_requests",
        "resolution_policies",
        "resolution_policy_schema_priorities",
        "resolution_attribute_overrides",
        "dynamic_memory_policies",
        "audit_events",
    } <= set(Base.metadata.tables)


def test_database_constraint_names_are_globally_unique() -> None:
    names = [
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if constraint.name is not None
    ]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    assert duplicates == []


@pytest.mark.asyncio
async def test_db_native_fixture_is_normalized_and_idempotent(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'control-plane.db'}")
    await database.create_schema()
    try:
        await seed_control_plane(database)
        await seed_control_plane(database)

        async with database.session() as session:
            counts = {
                "domains": await session.scalar(
                    select(func.count()).select_from(MemoryDomainRecord)
                ),
                "preferences": await session.scalar(
                    select(func.count()).select_from(PreferenceDefinitionRecord)
                ),
                "schemas": await session.scalar(
                    select(func.count()).select_from(ProfileSchemaRecord)
                ),
                "agents": await session.scalar(
                    select(func.count()).select_from(RegisteredAgentRecord)
                ),
                "grants": await session.scalar(
                    select(func.count()).select_from(AgentSchemaGrantRecord)
                ),
                "audits": await session.scalar(select(func.count()).select_from(AuditEventRecord)),
            }
            repository = SqlAlchemyControlPlaneRepository(session)
            grocery = await repository.get_domain("grocery")
            domains = await repository.list_domains()
        assert counts == {
            "domains": len(PREFERENCES) + 1,
            # +1 for the dependent-scoped grocery.allergies attribute / schema / grant (Option C).
            "preferences": sum(len(fields) for fields in PREFERENCES.values()) + 1,
            "schemas": len(PREFERENCES) + 1,
            "agents": 6,
            "grants": 16,
            "audits": 1,
        }
        assert grocery is not None
        assert grocery.owner_team == "grocery-platform"
        assert [domain.id for domain in domains] == sorted(domain.id for domain in domains)
    finally:
        await database.dispose()
