from __future__ import annotations

from pathlib import Path

import pytest
from app.shared_memory.contracts import load_contracts
from memory_api.persistence import Database
from memory_api.services.contract_bootstrap import ContractBootstrapService
from memory_api.services.vertex_provisioning import build_vertex_context_spec

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_only_active_approved_schema_versions_are_exported(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'provisioning.db'}")
    await database.create_schema()
    try:
        async with database.session() as session:
            await ContractBootstrapService(session).import_bundle(
                load_contracts(PROJECT_ROOT / "config" / "contracts")
            )
        async with database.session() as session:
            spec = await build_vertex_context_spec(session)
    finally:
        await database.dispose()

    configs = spec["memory_bank_config"]["structured_memory_configs"]
    assert configs
    assert configs[0]["scope_keys"] == ["user_id", "app_name", "domain"]
    schema_ids = {item["id"] for group in configs for item in group["schema_configs"]}
    assert {"customer-preferences-v1", "grocery-preferences-v1"} <= schema_ids
