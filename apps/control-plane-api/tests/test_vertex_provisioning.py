from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from control_plane_api.persistence import Database
from control_plane_api.services.vertex_provisioning import (
    VertexContextProvisioner,
    build_vertex_context_spec,
)
from db_seed import seed_control_plane


@pytest.mark.asyncio
async def test_only_active_approved_schema_versions_are_exported(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'provisioning.db'}")
    await database.create_schema()
    try:
        await seed_control_plane(database)
        async with database.session() as session:
            spec = await build_vertex_context_spec(session)
    finally:
        await database.dispose()

    configs = spec["memory_bank_config"]["structured_memory_configs"]
    assert configs
    assert configs[0]["scope_keys"] == ["organization_id", "user_id"]
    schema_ids = {item["id"] for group in configs for item in group["schema_configs"]}
    assert {"customer-preferences-v1", "grocery-preferences-v1"} <= schema_ids


@pytest.mark.asyncio
async def test_context_provisioner_performs_context_only_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'vertex-update.db'}")
    await database.create_schema()
    await seed_control_plane(database)

    calls: list[dict[str, object]] = []

    class FakeRuntimes:
        def update(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                name="projects/test/locations/us-central1/reasoningEngines/123"
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.runtimes = FakeRuntimes()

    monkeypatch.setitem(sys.modules, "agentplatform", SimpleNamespace(Client=FakeClient))
    try:
        async with database.session() as session:
            result = await VertexContextProvisioner(
                project="test", location="us-central1", resource_id="123"
            ).provision(session)
    finally:
        await database.dispose()

    assert result["status"] == "PROVISIONED"
    assert result["profileInstancesCreated"] == 0
    assert calls[0]["name"].endswith("/reasoningEngines/123")
    assert calls[0]["config"]["context_spec"]["memory_bank_config"]
    assert "agent" not in calls[0]
