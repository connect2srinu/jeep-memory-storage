from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from control_plane_api.application import create_app
from control_plane_api.config import ControlPlaneApiSettings
from control_plane_api.integrations import MockMemoryStore
from control_plane_api.persistence import Database
from db_seed import seed_control_plane

PLATFORM = {"X-Admin-User": "platform@example.com", "X-Admin-Roles": "PLATFORM_ADMIN"}
BASE = "/api/v1/admin/organizations/retail/households"


async def _client(tmp_path: Path) -> tuple[httpx.AsyncClient, Database]:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'households.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused",
            auth_enabled=False,
            google_id_token_audience=None,
        ),
        database=database,
        store=MockMemoryStore(),
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return client, database


@pytest.mark.asyncio
async def test_admin_household_roster_crud(tmp_path: Path) -> None:
    client, database = await _client(tmp_path)
    async with client:
        alice = await client.put(
            f"{BASE}/smith/members/alice",
            headers=PLATFORM,
            json={
                "displayName": "Alice",
                "relationship": "account_holder",
                "hasLogin": True,
                "isGuardian": True,
            },
        )
        assert alice.status_code == 200, alice.text
        assert alice.json()["data"]["is_guardian"] is True

        timmy = await client.put(
            f"{BASE}/smith/members/timmy",
            headers=PLATFORM,
            json={"displayName": "Timmy", "relationship": "child"},
        )
        assert timmy.status_code == 200, timmy.text

        households = await client.get(BASE, headers=PLATFORM)
        assert households.status_code == 200, households.text
        summary = {item["household_id"]: item for item in households.json()["items"]}
        assert summary["smith"]["member_count"] == 2
        assert summary["smith"]["guardian_count"] == 1

        members = await client.get(f"{BASE}/smith/members", headers=PLATFORM)
        assert {item["member_id"] for item in members.json()["items"]} == {"alice", "timmy"}

        removed = await client.delete(f"{BASE}/smith/members/timmy", headers=PLATFORM)
        assert removed.status_code == 200, removed.text
        assert removed.json()["data"]["status"] == "inactive"

        households_after = await client.get(BASE, headers=PLATFORM)
        summary_after = {item["household_id"]: item for item in households_after.json()["items"]}
        assert summary_after["smith"]["member_count"] == 1
    await database.dispose()


@pytest.mark.asyncio
async def test_admin_household_member_requires_platform(tmp_path: Path) -> None:
    client, database = await _client(tmp_path)
    async with client:
        response = await client.put(
            f"{BASE}/smith/members/alice",
            headers={"X-Admin-User": "viewer@example.com", "X-Admin-Roles": "VIEWER"},
            json={"displayName": "Alice"},
        )
        assert response.status_code == 403, response.text
    await database.dispose()
