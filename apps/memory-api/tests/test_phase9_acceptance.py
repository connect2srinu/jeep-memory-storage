from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from db_seed import seed_control_plane
from memory_api.application import create_app
from memory_api.config import MemoryApiSettings
from memory_api.integrations import MockMemoryStore
from memory_api.persistence import Database
from memory_api.persistence.models import AgentSchemaGrantRecord

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads(
    (PROJECT_ROOT / "packages" / "test-fixtures" / "user-1001-acceptance.json").read_text(
        encoding="utf-8"
    )
)


def agent(agent_id: str) -> dict[str, str]:
    return {"X-Agent-ID": agent_id}


def admin(role: str, domain: str) -> dict[str, str]:
    return {
        "X-Admin-User": f"phase9-{domain}@example.com",
        "X-Admin-Roles": role,
        "X-Admin-Domains": domain,
    }


def scope(domain: str) -> dict[str, str]:
    return {"userId": FIXTURE["userId"], "appName": FIXTURE["appName"], "domain": domain}


@pytest.mark.asyncio
async def test_user_1001_approval_resolution_update_and_refresh(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'phase9.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    async with database.session() as session:
        customer_grant = await session.get(
            AgentSchemaGrantRecord, "grocery-agent:customer-preferences-v1"
        )
        assert customer_grant is not None
        customer_grant.status = "REVOKED"
    app = create_app(
        MemoryApiSettings(database_url="unused", auth_enabled=False, google_id_token_audience=None),
        database=database,
        store=MockMemoryStore(),
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            domain_agents = {
                "grocery": ("grocery-agent", "grocery-preferences-v1"),
                "customer": ("customer-agent", "customer-preferences-v1"),
                "inventory": ("inventory-agent", "inventory-preferences-v1"),
            }
            for domain, values in FIXTURE["profiles"].items():
                agent_id, schema_id = domain_agents[domain]
                for attribute, value in values.items():
                    response = await client.put(
                        f"/api/v1/runtime/preferences/{attribute}",
                        headers=agent(agent_id),
                        json={"scope": scope(domain), "schemaId": schema_id, "value": value},
                    )
                    assert response.status_code == 200, response.text

            denied = await client.post(
                "/api/v1/runtime/preferences/resolve",
                headers=agent("grocery-agent"),
                json={"scope": scope("grocery"), "sessionId": FIXTURE["sessionId"]},
            )
            assert "fulfillment_preference" not in denied.json()["preferences"]

            requested = await client.post(
                "/api/v1/admin/access-requests",
                headers=admin("AGENT_OWNER", "grocery"),
                json={
                    "requestingAgentId": "grocery-agent",
                    "requestingTeam": "grocery-platform",
                    "targetSchemaId": "customer-preferences-v1",
                    "requestedPermission": "READ",
                    "businessReason": "Phase 9 acceptance resolution",
                },
            )
            assert requested.status_code == 201, requested.text
            request_id = requested.json()["data"]["id"]
            approved = await client.post(
                f"/api/v1/admin/access-requests/{request_id}/approve",
                headers=admin("SCHEMA_OWNER", "customer"),
                json={},
            )
            assert approved.status_code == 200, approved.text

            resolved = await client.post(
                "/api/v1/runtime/preferences/resolve",
                headers=agent("grocery-agent"),
                json={
                    "scope": scope("grocery"),
                    "sessionId": FIXTURE["sessionId"],
                    "includeProvenance": True,
                    "agentId": "grocery-agent",
                },
            )
            assert resolved.status_code == 200, resolved.text
            initial = resolved.json()
            expected = FIXTURE["expected"]
            assert initial["preferences"]["preferred_store"]["value"] == expected["preferred_store"]
            assert initial["preferences"]["preferred_store"]["ownerDomain"] == "customer"
            assert initial["preferences"]["preferred_store"]["resolutionReason"] == (
                "DOMAIN_AUTHORITY"
            )
            assert initial["preferences"]["dietary_preference"]["value"] == "vegetarian"
            assert initial["preferences"]["fulfillment_preference"]["value"] == "pickup"
            assert initial["preferences"]["preferred_store"]["provenance"]["schema_id"] == (
                "customer-preferences-v1"
            )

            update = await client.put(
                "/api/v1/runtime/preferences/grocery.dietary_preference",
                headers=agent("grocery-agent"),
                json={
                    "scope": scope("grocery"),
                    "schemaId": "grocery-preferences-v1",
                    "value": "vegan",
                },
            )
            assert update.status_code == 200
            assert update.json()["profileVersion"] == 3
            refreshed = await client.post(
                "/api/v1/runtime/preferences/refresh",
                headers=agent("grocery-agent"),
                json={"scope": scope("grocery"), "sessionId": FIXTURE["sessionId"]},
            )
            assert refreshed.status_code == 200
            current = refreshed.json()
            assert current["snapshotVersion"] != initial["snapshotVersion"]
            assert current["preferences"]["dietary_preference"]["value"] == "vegan"
            assert current["schemaVersions"] == {
                "customer-preferences-v1": "1.0",
                "grocery-preferences-v1": "1.0",
                "inventory-preferences-v1": "1.0",
                "store-preferences-v1": "1.0",
                "delivery-preferences-v1": "1.0",
            }
    finally:
        await database.dispose()
