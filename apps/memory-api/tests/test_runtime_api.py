from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from app.shared_memory.contracts import load_contracts
from memory_api.application import create_app
from memory_api.config import MemoryApiSettings
from memory_api.integrations import MockMemoryStore
from memory_api.persistence import Database
from memory_api.services import ContractBootstrapService

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest_asyncio.fixture
async def runtime_client(tmp_path: Path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}")
    await database.create_schema()
    async with database.session() as session:
        await ContractBootstrapService(session).import_bundle(
            load_contracts(PROJECT_ROOT / "config" / "contracts")
        )
    app = create_app(
        MemoryApiSettings(
            database_url="unused",
            auth_enabled=False,
            google_id_token_audience=None,
            include_legacy_routes=False,
        ),
        database=database,
        store=MockMemoryStore(),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await database.dispose()


def scope(user_id: str = "u1", domain: str = "grocery") -> dict[str, str]:
    return {"userId": user_id, "appName": "grocery-app", "domain": domain}


@pytest.mark.asyncio
async def test_explicit_write_then_resolve_returns_versioned_snapshot(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent", "X-Correlation-ID": "phase4-test"}
    update = await runtime_client.put(
        "/api/v1/runtime/preferences/grocery.preferred_snack",
        headers=headers,
        json={
            "scope": scope(),
            "schemaId": "grocery-preferences-v1",
            "value": "mango chips",
        },
    )
    assert update.status_code == 200, update.text
    assert update.json()["profileVersion"] == 1
    assert update.headers["x-correlation-id"] == "phase4-test"

    resolved = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=headers,
        json={
            "scope": scope(),
            "sessionId": "s1",
            "includeProvenance": True,
            "agentId": "grocery-agent",
        },
    )
    assert resolved.status_code == 200, resolved.text
    payload = resolved.json()
    assert payload["agentId"] == "grocery-agent"
    assert payload["preferences"]["preferred_snack"]["value"] == "mango chips"
    assert payload["preferences"]["preferred_snack"]["provenance"]["schema_id"] == (
        "grocery-preferences-v1"
    )
    assert len(payload["snapshotVersion"]) == 24
    assert payload["policyVersion"] == "1.0"


@pytest.mark.asyncio
async def test_identity_spoofing_and_cross_domain_writes_are_denied(runtime_client) -> None:
    spoofed = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers={"X-Agent-ID": "grocery-agent"},
        json={"scope": scope(), "sessionId": "s1", "agentId": "delivery-agent"},
    )
    assert spoofed.status_code == 403
    assert spoofed.json()["code"] == "PERMISSION_DENIED"

    customer_write = await runtime_client.put(
        "/api/v1/runtime/preferences/diet",
        headers={"X-Agent-ID": "grocery-agent"},
        json={"scope": scope(), "schemaId": "customer-preferences-v1", "value": "vegan"},
    )
    assert customer_write.status_code == 403
    assert "lacks WRITE" in customer_write.json()["message"]


@pytest.mark.asyncio
async def test_authentication_and_capability_failures_are_structured(runtime_client) -> None:
    missing_identity = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        json={"scope": scope(), "sessionId": "s1"},
    )
    assert missing_identity.status_code == 401
    assert missing_identity.json()["code"] == "UNAUTHENTICATED"
    assert missing_identity.headers["x-correlation-id"]

    readonly_write = await runtime_client.put(
        "/api/v1/runtime/preferences/allow_substitutions",
        headers={"X-Agent-ID": "grocery-readonly-agent"},
        json={
            "scope": scope(),
            "schemaId": "grocery-preferences-v1",
            "value": True,
        },
    )
    assert readonly_write.status_code == 403
    assert "lacks capability submit_candidates" in readonly_write.json()["message"]


@pytest.mark.asyncio
async def test_user_scopes_do_not_leak(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}
    await runtime_client.put(
        "/api/v1/runtime/preferences/grocery.preferred_snack",
        headers=headers,
        json={
            "scope": scope("first-user"),
            "schemaId": "grocery-preferences-v1",
            "value": "mango chips",
        },
    )
    second = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=headers,
        json={"scope": scope("second-user"), "sessionId": "s2"},
    )
    assert second.status_code == 200
    assert "preferred_snack" not in second.json()["preferences"]


@pytest.mark.asyncio
async def test_event_ingestion_raw_profiles_and_refresh(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}
    event = await runtime_client.post(
        "/api/v1/runtime/memory/events",
        headers=headers,
        json={
            "scope": scope("event-user"),
            "text": "I prefer potato chips as my snack.",
            "candidates": [
                {
                    "schemaId": "grocery-preferences-v1",
                    "attribute": "grocery.preferred_snack",
                    "value": "potato chips",
                }
            ],
        },
    )
    assert event.status_code == 200, event.text
    assert event.json()["status"] == "accepted"

    profiles = await runtime_client.post(
        "/api/v1/runtime/profiles",
        headers=headers,
        json={
            "scope": scope("event-user"),
            "schemaIds": ["grocery-preferences-v1"],
        },
    )
    assert profiles.status_code == 200, profiles.text
    assert profiles.json()["profiles"][0]["values"] == {"preferred_snack": "potato chips"}

    refreshed = await runtime_client.post(
        "/api/v1/runtime/preferences/refresh",
        headers=headers,
        json={"scope": scope("event-user"), "sessionId": "refresh-session"},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["preferences"]["preferred_snack"]["value"] == "potato chips"


@pytest.mark.asyncio
async def test_raw_profiles_require_provenance_capability(runtime_client) -> None:
    denied = await runtime_client.post(
        "/api/v1/runtime/profiles",
        headers={"X-Agent-ID": "grocery-readonly-agent"},
        json={
            "scope": scope(),
            "schemaIds": ["grocery-preferences-v1"],
        },
    )
    assert denied.status_code == 403
    assert "lacks capability inspect_provenance" in denied.json()["message"]
