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
    # Schemas are grouped by their scope shape; the member scope is one of the groups.
    scope_key_groups = [tuple(group["scope_keys"]) for group in configs]
    assert ("organization_id", "user_id") in scope_key_groups
    assert ("organization_id", "household_id", "member_id") in scope_key_groups
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
                project="test",
                location="us-central1",
                resource_id="123",
                generation_model="gemini-2.5-flash",
            ).provision(session)
    finally:
        await database.dispose()

    assert result["status"] == "PROVISIONED"
    assert result["profileInstancesCreated"] == 0
    assert calls[0]["name"].endswith("/reasoningEngines/123")
    memory_bank_config = calls[0]["config"]["context_spec"]["memory_bank_config"]
    assert memory_bank_config["structured_memory_configs"]
    # A bare model id is resolved to a Google publisher-model resource.
    assert memory_bank_config["generation_config"] == {
        "model": "projects/test/locations/us-central1/publishers/google/models/gemini-2.5-flash"
    }
    assert result["generationModel"].endswith("/publishers/google/models/gemini-2.5-flash")
    assert "agent" not in calls[0]


@pytest.mark.asyncio
async def test_generation_model_defaults_to_provider_and_accepts_full_resource(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'genmodel.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    try:
        async with database.session() as session:
            # No generation model configured → provider default, no generation_config key.
            default_spec = await build_vertex_context_spec(session)
            assert "generation_config" not in default_spec["memory_bank_config"]

            # A full resource path is passed through unchanged.
            full = (
                "projects/other/locations/europe-west1/publishers/google/models/gemini-2.5-pro"
            )
            passthrough = await build_vertex_context_spec(session, generation_model=full)
            assert passthrough["memory_bank_config"]["generation_config"] == {"model": full}
    finally:
        await database.dispose()
