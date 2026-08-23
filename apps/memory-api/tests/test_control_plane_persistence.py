from __future__ import annotations

from pathlib import Path

import pytest
from app.shared_memory.contracts import load_contracts
from memory_api.persistence import Database, SqlAlchemyControlPlaneRepository
from memory_api.persistence.models import (
    AgentSchemaGrantRecord,
    AuditEventRecord,
    Base,
    MemoryDomainRecord,
    PreferenceDefinitionRecord,
    ProfileSchemaRecord,
    RegisteredAgentRecord,
)
from memory_api.services import ContractBootstrapService
from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[3]


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


@pytest.mark.asyncio
async def test_yaml_contract_bootstrap_is_normalized_and_idempotent(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'control-plane.db'}")
    await database.create_schema()
    bundle = load_contracts(PROJECT_ROOT / "config" / "contracts")
    try:
        async with database.session() as session:
            first = await ContractBootstrapService(session).import_bundle(bundle)
        async with database.session() as session:
            second = await ContractBootstrapService(session).import_bundle(bundle)
        assert first == second
        assert first.domains == len(bundle.domains)
        assert first.preferences == sum(len(item.preferences) for item in bundle.catalogs)
        assert first.schemas == sum(len(item.profiles) for item in bundle.profiles)
        assert first.agents == sum(len(item.consumers) for item in bundle.consumers)

        async with database.session() as session:
            counts = {
                "domains": await session.scalar(select(func.count()).select_from(MemoryDomainRecord)),
                "preferences": await session.scalar(
                    select(func.count()).select_from(PreferenceDefinitionRecord)
                ),
                "schemas": await session.scalar(select(func.count()).select_from(ProfileSchemaRecord)),
                "agents": await session.scalar(select(func.count()).select_from(RegisteredAgentRecord)),
                "grants": await session.scalar(
                    select(func.count()).select_from(AgentSchemaGrantRecord)
                ),
                "audits": await session.scalar(select(func.count()).select_from(AuditEventRecord)),
            }
            repository = SqlAlchemyControlPlaneRepository(session)
            grocery = await repository.get_domain("grocery")
            domains = await repository.list_domains()
        assert counts == {
            "domains": first.domains,
            "preferences": first.preferences,
            "schemas": first.schemas,
            "agents": first.agents,
            "grants": first.grants,
            "audits": 1,
        }
        assert grocery is not None
        assert grocery.owner_team == "grocery-platform"
        assert [domain.id for domain in domains] == sorted(domain.id for domain in domains)
    finally:
        await database.dispose()
