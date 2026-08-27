from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from control_plane_api.api.runtime.models import RuntimeScope
from control_plane_api.application import create_app
from control_plane_api.config import ControlPlaneApiSettings
from control_plane_api.domain.control_plane import AccessPermission
from control_plane_api.domain.runtime import RuntimeAgent, RuntimeSchemaGrant
from control_plane_api.integrations import MockMemoryStore
from control_plane_api.persistence import Database
from control_plane_api.services.runtime_service import RuntimeMemoryService
from control_plane_api.services.scope_registry import ScopeRegistry
from db_seed import seed_control_plane


@pytest_asyncio.fixture
async def runtime_client(tmp_path: Path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}")
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
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await database.dispose()


def scope(user_id: str = "u1", domain: str = "grocery") -> dict[str, str]:
    return {"userId": user_id, "appName": "grocery-app", "domain": domain}


@pytest.mark.asyncio
async def test_explicit_write_then_resolve_returns_versioned_snapshot(
    runtime_client, caplog
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="uvicorn.error.control_plane_api.preference_resolution",
    )
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
    assert "grocery.preferred_snack" in payload["writablePreferences"]
    assert "agent_capability_scope_and_grants_validated" in caplog.text
    assert "authorized_memory_profiles_read_completed" in caplog.text
    assert "configured_resolution_policy_applied" in caplog.text
    assert "effective_preference_snapshot_returned" in caplog.text


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
async def test_schema_less_writes_resolve_the_owned_writable_schema(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}
    update = await runtime_client.put(
        "/api/v1/runtime/preferences/grocery.preferred_snack",
        headers=headers,
        json={"scope": scope("schema-less-update"), "value": "pretzels"},
    )
    assert update.status_code == 200, update.text
    assert update.json()["reference"] == ("grocery-preferences-v1:grocery.preferred_snack")

    event = await runtime_client.post(
        "/api/v1/runtime/memory/events",
        headers=headers,
        json={
            "scope": scope("schema-less-event"),
            "text": "I prefer potato chips as my snack.",
            "candidates": [{"attribute": "preferred_snack", "value": "potato chips"}],
        },
    )
    assert event.status_code == 200, event.text


@pytest.mark.asyncio
async def test_schema_less_write_does_not_escalate_to_shared_or_unknown_schema(
    runtime_client,
) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}
    shared = await runtime_client.put(
        "/api/v1/runtime/preferences/customer.diet",
        headers=headers,
        json={"scope": scope("shared-write"), "value": "vegan"},
    )
    assert shared.status_code == 403
    assert "no same-domain WRITE access" in shared.json()["message"]

    unknown = await runtime_client.put(
        "/api/v1/runtime/preferences/grocery.not_onboarded",
        headers=headers,
        json={"scope": scope("unknown-write"), "value": "anything"},
    )
    assert unknown.status_code == 400
    assert "not registered in a writable schema" in unknown.json()["message"]


def test_schema_less_write_rejects_ambiguous_owned_mappings() -> None:
    service = RuntimeMemoryService(None, MockMemoryStore(), None)  # type: ignore[arg-type]
    agent = RuntimeAgent(
        id="grocery-agent",
        organization_id="retail",
        project_id="shopping",
        domain_id="grocery",
        principal=None,
        capabilities=frozenset({"submit_candidates"}),
    )
    grants = tuple(
        RuntimeSchemaGrant(
            schema_id=schema_id,
            owner_organization_id="retail",
            domain_id="grocery",
            schema_version="1",
            permission=AccessPermission.READ_WRITE,
            scope_keys=("organization_id", "user_id"),
            field_to_attribute={"preferred_snack": "grocery.preferred_snack"},
        )
        for schema_id in ("grocery-preferences-v1", "grocery-preferences-v2")
    )

    with pytest.raises(ValueError, match="multiple writable schemas"):
        service._resolve_write_grant(
            agent,
            grants,
            "grocery.preferred_snack",
            "grocery",
            None,
        )


def test_foreign_schema_reads_use_owner_organization_scope() -> None:
    service = RuntimeMemoryService(None, MockMemoryStore(), ScopeRegistry())  # type: ignore[arg-type]
    grant = RuntimeSchemaGrant(
        schema_id="grocery-preferences-v1",
        owner_organization_id="default-org",
        domain_id="grocery",
        schema_version="1",
        permission=AccessPermission.READ,
        scope_keys=("organization_id", "user_id"),
        field_to_attribute={"preferred_brand": "grocery.preferred_brand"},
    )

    resolved = service._owner_scope(RuntimeScope(userId="demo-user-123"), grant)

    assert resolved.organization_id == "default-org"
    assert resolved.user_id == "demo-user-123"


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
