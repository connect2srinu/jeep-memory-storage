from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.shared_memory.contracts import load_contracts
from memory_api.persistence import Database, SqlAlchemyControlPlaneRepository
from memory_api.services import ContractBootstrapService

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
    reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 with a disposable PostgreSQL DATABASE_URL",
)
async def test_contract_bootstrap_against_postgres() -> None:
    database_url = os.environ["DATABASE_URL"]
    database = Database(database_url)
    try:
        await database.create_schema()
        bundle = load_contracts(PROJECT_ROOT / "config" / "contracts")
        async with database.session() as session:
            result = await ContractBootstrapService(session).import_bundle(
                bundle,
                actor="postgres-contract-test",
                correlation_id="postgres-contract-test",
            )
        async with database.session() as session:
            domains = await SqlAlchemyControlPlaneRepository(session).list_domains()
        assert result.domains == 5
        assert len(domains) == 5
    finally:
        await database.dispose()
