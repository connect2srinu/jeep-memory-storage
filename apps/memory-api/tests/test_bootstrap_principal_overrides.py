from __future__ import annotations

from pathlib import Path

import pytest
from db_seed import seed_control_plane
from memory_api.persistence import Database
from memory_api.persistence.models import RegisteredAgentRecord
from memory_api.services.principal_overrides import apply_principal_overrides


@pytest.mark.asyncio
async def test_deployment_principal_overrides_are_validated_and_persisted(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'principals.db'}")
    await database.create_schema()
    try:
        await seed_control_plane(database)
        async with database.session() as session:
            count = await apply_principal_overrides(
                session,
                '{"grocery-agent":"grocery-agent@example.iam.gserviceaccount.com"}',
            )
            assert count == 1
        async with database.session() as session:
            agent = await session.get(RegisteredAgentRecord, "grocery-agent")
            assert agent is not None
            assert agent.principal == "grocery-agent@example.iam.gserviceaccount.com"
            with pytest.raises(ValueError, match="unknown agent"):
                await apply_principal_overrides(session, '{"missing":"principal"}')
    finally:
        await database.dispose()
