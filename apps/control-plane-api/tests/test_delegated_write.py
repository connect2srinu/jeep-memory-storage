"""Cross-domain (delegated) writes: an agent may write another domain's attributes only when the
owner approved writing those specific attributes, and only customer-stated, non-health values."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from control_plane_api.application import create_app
from control_plane_api.config import ControlPlaneApiSettings
from control_plane_api.integrations import MockMemoryStore
from control_plane_api.persistence import Database
from control_plane_api.persistence.models import PreferenceDefinitionRecord
from db_seed import seed_control_plane

PLATFORM = {"X-Admin-User": "platform@example.com", "X-Admin-Roles": "PLATFORM_ADMIN"}
GROCERY = {"X-Agent-ID": "grocery-agent"}
CUSTOMER = {"X-Agent-ID": "customer-agent"}


def scope(domain: str) -> dict[str, str]:
    return {"userId": "delegated-user", "appName": "delegated", "domain": domain}


def write_request(attributes: list[str] | None, permission: str = "READ_WRITE") -> dict:
    return {
        "requestingAgentId": "grocery-agent",
        "requestingTeam": "grocery-platform",
        "targetSchemaId": "customer-preferences-v1",
        "requestedPermission": permission,
        "businessReason": "Save the customer's store choice for the customer profile",
        **({"attributes": attributes} if attributes else {}),
    }


@pytest.mark.asyncio
async def test_delegated_write_lands_in_the_owner_schema_within_its_guardrails(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'delegated.db'}")
    await database.create_schema()
    await seed_control_plane(database)
    app = create_app(
        ControlPlaneApiSettings(
            database_url="unused", auth_enabled=False, google_id_token_audience=None
        ),
        database=database,
        store=MockMemoryStore(),
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Whole-schema write access to another domain is never granted.
            whole = await client.post(
                "/api/v1/admin/access-requests", headers=PLATFORM, json=write_request(None)
            )
            assert whole.status_code == 400
            assert "must name the attributes" in whole.text

            requested = await client.post(
                "/api/v1/admin/access-requests",
                headers=PLATFORM,
                json=write_request(["customer.preferred_store", "customer.diet"]),
            )
            assert requested.status_code == 201, requested.text
            request_id = requested.json()["data"]["id"]
            approved = await client.post(
                f"/api/v1/admin/access-requests/{request_id}/approve", headers=PLATFORM, json={}
            )
            assert approved.status_code == 200, approved.text

            snapshot = await client.post(
                "/api/v1/runtime/preferences/resolve",
                headers=GROCERY,
                json={"scope": scope("grocery"), "sessionId": "s1"},
            )
            assert "customer.preferred_store" in snapshot.json()["writablePreferences"]

            saved = await client.put(
                "/api/v1/runtime/preferences/customer.preferred_store",
                headers=GROCERY,
                json={"scope": scope("grocery"), "value": "Store-Z"},
            )
            assert saved.status_code == 200, saved.text
            assert saved.json()["reference"] == "customer-preferences-v1:customer.preferred_store"

            # The owner reads the value the other domain saved: one value, not a copy.
            owner_view = await client.post(
                "/api/v1/runtime/preferences/resolve",
                headers=CUSTOMER,
                json={"scope": scope("customer"), "sessionId": "s2"},
            )
            store = owner_view.json()["preferences"]["preferred_store"]
            assert (store["value"], store["ownerDomain"]) == ("Store-Z", "customer")

            inferred = await client.put(
                "/api/v1/runtime/preferences/customer.preferred_store",
                headers=GROCERY,
                json={"scope": scope("grocery"), "value": "Store-Y", "source": "inference"},
            )
            assert inferred.status_code == 403
            assert "only values the customer stated" in inferred.text

            not_granted = await client.put(
                "/api/v1/runtime/preferences/customer.fruit",
                headers=GROCERY,
                json={"scope": scope("grocery"), "value": "mango"},
            )
            assert not_granted.status_code in {400, 403}

            # An attribute flagged as health data is never written from another domain.
            async with database.session() as session:
                diet = await session.get(PreferenceDefinitionRecord, "customer.diet")
                assert diet is not None
                diet.validation_rules = {**(diet.validation_rules or {}), "health": True}
            health = await client.put(
                "/api/v1/runtime/preferences/customer.diet",
                headers=GROCERY,
                json={"scope": scope("grocery"), "value": "low sodium"},
            )
            assert health.status_code == 403
            assert "health data" in health.text
            health_request = await client.post(
                "/api/v1/admin/access-requests",
                headers=PLATFORM,
                json=write_request(["customer.diet"], permission="WRITE"),
            )
            assert health_request.status_code == 400
            assert "health data cannot be written" in health_request.text

            revoked = await client.post(
                f"/api/v1/admin/access-requests/{request_id}/revoke", headers=PLATFORM, json={}
            )
            assert revoked.status_code == 200, revoked.text
            after_revoke = await client.put(
                "/api/v1/runtime/preferences/customer.preferred_store",
                headers=GROCERY,
                json={"scope": scope("grocery"), "value": "Store-X"},
            )
            assert after_revoke.status_code in {400, 403}
    finally:
        await database.dispose()
