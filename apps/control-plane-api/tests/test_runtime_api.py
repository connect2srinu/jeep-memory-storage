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


@pytest.mark.asyncio
async def test_dynamic_memory_is_topic_gated_and_surfaces_in_resolution(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}

    # Approved topic, sufficient confidence -> accepted.
    accepted = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={
            "scope": scope(),
            "topic": "shopping",
            "value": "shops early Sunday mornings",
            "confidence": 0.9,
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"

    # Approved topic, low confidence -> stored but filtered from resolution by the 0.7 gate.
    low = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={
            "scope": scope(),
            "topic": "fulfillment",
            "value": "prefers locker pickup",
            "confidence": 0.5,
        },
    )
    assert low.status_code == 200, low.text

    # Unapproved topic -> rejected (the platform, not the agent, controls what may be retained).
    denied = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={"scope": scope(), "topic": "health", "value": "vegetarian", "confidence": 0.95},
    )
    assert denied.status_code == 403, denied.text
    assert "not an approved dynamic-memory topic" in denied.json()["message"]

    # Sensitive content, even within an approved topic -> rejected.
    sensitive = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={
            "scope": scope(),
            "topic": "shopping",
            "value": "call me at 555-123-4567",
            "confidence": 0.99,
        },
    )
    assert sensitive.status_code == 400, sensitive.text
    assert "restricted content" in sensitive.json()["message"]

    resolved = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=headers,
        json={"scope": scope(), "sessionId": "s1", "agentId": "grocery-agent"},
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert set(body["approvedTopics"]) == {"shopping", "fulfillment", "wellness"}
    prefs = body["preferences"]
    # High-confidence approved topic surfaces as DYNAMIC_MEMORY (below canonical in priority).
    assert prefs["topic:shopping"]["value"] == "shops early Sunday mornings"
    assert prefs["topic:shopping"]["source"] == "DYNAMIC_MEMORY"
    # The low-confidence entry is dropped by the confidence gate; the rejected ones never persisted.
    assert "topic:fulfillment" not in prefs


async def _dyn(client, headers, user, topic, value):
    return await client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={"scope": scope(user), "topic": topic, "value": value, "confidence": 0.9},
    )


@pytest.mark.asyncio
async def test_admin_declared_topic_sensitivity_is_enforced(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}
    # "wellness" is declared sensitive in the policy, even though the value is benign content.
    inferred = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={"scope": scope("u1"), "topic": "wellness", "value": "walks daily", "source": "inference"},
    )
    assert inferred.status_code == 403, inferred.text

    directed = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={"scope": scope("u1"), "topic": "wellness", "value": "walks daily", "source": "user_directed"},
    )
    assert directed.status_code == 200, directed.text

    resolved = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=headers,
        json={"scope": scope("u1"), "sessionId": "s", "agentId": "grocery-agent"},
    )
    assert resolved.json()["preferences"]["topic:wellness"]["sensitivity"] == "sensitive"


@pytest.mark.asyncio
async def test_restricted_content_is_blocked_on_all_writes(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}
    # Weapons -> restricted, blocked on a dynamic write to an approved topic.
    weapons = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={"scope": scope("u1"), "topic": "shopping", "value": "wishes he could bring guns in"},
    )
    assert weapons.status_code == 400, weapons.text
    assert "restricted content" in weapons.json()["message"]

    # PII -> restricted, blocked on a canonical write too.
    pii = await runtime_client.put(
        "/api/v1/runtime/preferences/grocery.preferred_store",
        headers=headers,
        json={"scope": scope("u1"), "value": "call me at 555-123-4567"},
    )
    assert pii.status_code == 400, pii.text


@pytest.mark.asyncio
async def test_sensitive_memory_only_stored_when_user_directed(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}
    # grocery.dietary_preference is a sensitive attribute; inferred -> rejected.
    inferred = await runtime_client.put(
        "/api/v1/runtime/preferences/grocery.dietary_preference",
        headers=headers,
        json={"scope": scope("u1"), "value": "kosher", "source": "inference"},
    )
    assert inferred.status_code == 403, inferred.text

    # User-directed -> stored.
    directed = await runtime_client.put(
        "/api/v1/runtime/preferences/grocery.dietary_preference",
        headers=headers,
        json={"scope": scope("u1"), "value": "kosher", "source": "user_directed"},
    )
    assert directed.status_code == 200, directed.text

    # Sensitive *content* (protected class) via dynamic: inferred rejected, user-directed stored.
    inf = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={"scope": scope("u2"), "topic": "shopping", "value": "user is Muslim", "source": "inference"},
    )
    assert inf.status_code == 403, inf.text
    ok = await runtime_client.post(
        "/api/v1/runtime/memory/dynamic",
        headers=headers,
        json={"scope": scope("u2"), "topic": "shopping", "value": "user is Muslim", "source": "user_directed"},
    )
    assert ok.status_code == 200, ok.text

    # Resolve surfaces the sensitivity (and, for dynamic, the source).
    canonical = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=headers,
        json={"scope": scope("u1"), "sessionId": "s", "agentId": "grocery-agent"},
    )
    assert canonical.json()["preferences"]["dietary_preference"]["sensitivity"] == "sensitive"

    dynamic = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=headers,
        json={"scope": scope("u2"), "sessionId": "s", "agentId": "grocery-agent"},
    )
    entry = dynamic.json()["preferences"]["topic:shopping"]
    assert entry["sensitivity"] == "sensitive"
    assert entry["memorySource"] == "user_directed"


@pytest.mark.asyncio
async def test_forget_deletes_all_of_a_users_memories(runtime_client) -> None:
    headers = {"X-Agent-ID": "grocery-agent"}
    await runtime_client.put(
        "/api/v1/runtime/preferences/grocery.preferred_store",
        headers=headers,
        json={"scope": scope("u1"), "value": "Kroger"},
    )
    assert (await _dyn(runtime_client, headers, "u1", "shopping", "weekly bulk run")).status_code == 200

    forget = await runtime_client.post(
        "/api/v1/runtime/memory/forget", headers=headers, json={"scope": scope("u1")}
    )
    assert forget.status_code == 200, forget.text
    assert forget.json()["status"] == "forgotten"
    assert forget.json()["deleted"] >= 2

    resolved = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=headers,
        json={"scope": scope("u1"), "sessionId": "s", "agentId": "grocery-agent"},
    )
    assert resolved.json()["preferences"] == {}


@pytest.mark.asyncio
async def test_operator_purge_is_capability_gated_previewed_then_executed(runtime_client) -> None:
    admin = {"X-Agent-ID": "grocery-agent"}  # seeded with administer_memory
    await _dyn(runtime_client, admin, "u1", "shopping", "weekly bulk run")
    await _dyn(runtime_client, admin, "u2", "shopping", "fortnightly run")

    # Requires the ADMINISTER_MEMORY capability.
    denied = await runtime_client.post(
        "/api/v1/runtime/memory/purge",
        headers={"X-Agent-ID": "grocery-readonly-agent"},
        json={"topic": "shopping", "dryRun": True},
    )
    assert denied.status_code == 403, denied.text

    # A filter is required.
    empty = await runtime_client.post(
        "/api/v1/runtime/memory/purge", headers=admin, json={"dryRun": True}
    )
    assert empty.status_code == 400, empty.text

    # Dry run previews both users without deleting.
    preview = await runtime_client.post(
        "/api/v1/runtime/memory/purge", headers=admin, json={"topic": "shopping", "dryRun": True}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "preview"
    assert preview.json()["matched"] == 2
    still = await runtime_client.post(
        "/api/v1/runtime/preferences/resolve",
        headers=admin,
        json={"scope": scope("u1"), "sessionId": "s", "agentId": "grocery-agent"},
    )
    assert "topic:shopping" in still.json()["preferences"]

    # Execute the purge across the organization.
    purged = await runtime_client.post(
        "/api/v1/runtime/memory/purge", headers=admin, json={"topic": "shopping", "dryRun": False}
    )
    assert purged.json()["status"] == "purged"
    assert purged.json()["matched"] == 2
    for user in ("u1", "u2"):
        gone = await runtime_client.post(
            "/api/v1/runtime/preferences/resolve",
            headers=admin,
            json={"scope": scope(user), "sessionId": "s", "agentId": "grocery-agent"},
        )
        assert "topic:shopping" not in gone.json()["preferences"]
