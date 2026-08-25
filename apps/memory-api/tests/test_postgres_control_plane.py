from __future__ import annotations

import os

import pytest
from db_seed import PREFERENCES, seed_control_plane
from memory_api.persistence import Database, SqlAlchemyControlPlaneRepository


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
    reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 with a disposable PostgreSQL DATABASE_URL",
)
async def test_db_native_control_plane_against_postgres() -> None:
    database_url = os.environ["DATABASE_URL"]
    database = Database(database_url)
    try:
        await database.create_schema()
        await seed_control_plane(database)
        async with database.session() as session:
            domains = await SqlAlchemyControlPlaneRepository(session).list_domains()
        assert len(domains) == len(PREFERENCES) + 1
    finally:
        await database.dispose()
