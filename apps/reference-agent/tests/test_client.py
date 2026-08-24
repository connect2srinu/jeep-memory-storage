import json

import httpx
import pytest
from reference_agent.client import (
    GoogleIdTokenProvider,
    MemoryApiClient,
    PreferenceCandidate,
)


def snapshot_payload(value: str = "mango") -> dict:
    return {
        "agentId": "grocery-agent",
        "scope": {"userId": "user-1", "appName": "grocery-app", "domain": "grocery"},
        "sessionId": "session-1",
        "preferences": {
            "grocery.preferred_snack": {
                "value": value,
                "source": "MEMORY_PROFILE",
                "ownerDomain": "grocery",
                "resolutionReason": "DOMAIN_AUTHORITY",
            }
        },
        "snapshotVersion": "v1",
        "policyVersion": "p1",
        "schemaVersions": {"grocery-preferences-v1": "1"},
        "writablePreferences": ["grocery.preferred_snack"],
        "generatedAt": "2026-08-22T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_resolve_uses_typed_contract_and_bearer_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/runtime/preferences/resolve"
        assert request.headers["Authorization"] == "Bearer test-token"
        payload = json.loads(request.content)
        assert payload["scope"] == {
            "userId": "user-1",
            "appName": "grocery-app",
            "domain": "grocery",
        }
        assert payload["sessionId"] == "session-1"
        return httpx.Response(200, json=snapshot_payload())

    client = MemoryApiClient(
        base_url="http://memory-api",
        token="test-token",
        transport=httpx.MockTransport(handler),
    )
    result = await client.resolve_preferences(
        user_id="user-1",
        session_id="session-1",
        app_name="grocery-app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
    )
    assert result.snapshot_version == "v1"
    assert result.preferences["grocery.preferred_snack"].value == "mango"


@pytest.mark.asyncio
async def test_refresh_update_and_event_use_runtime_routes() -> None:
    requests: list[tuple[str, str, dict]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((request.method, request.url.path, payload))
        if request.url.path.endswith("/refresh"):
            return httpx.Response(200, json=snapshot_payload("potato chips"))
        return httpx.Response(
            200,
            json={"status": "accepted", "reference": "ref-1", "profileVersion": 2},
        )

    client = MemoryApiClient(
        base_url="http://memory-api",
        transport=httpx.MockTransport(handler),
    )
    await client.update_preference(
        user_id="user-1",
        app_name="grocery-app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        attribute="grocery.preferred_snack",
        value="potato chips",
    )
    await client.ingest_event(
        user_id="user-1",
        app_name="grocery-app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        text="I prefer potato chips.",
        candidates=[
            PreferenceCandidate(
                attribute="grocery.preferred_snack",
                value="potato chips",
            )
        ],
    )
    refreshed = await client.refresh_preferences(
        user_id="user-1",
        session_id="session-1",
        app_name="grocery-app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
    )

    assert [item[:2] for item in requests] == [
        ("PUT", "/api/v1/runtime/preferences/grocery.preferred_snack"),
        ("POST", "/api/v1/runtime/memory/events"),
        ("POST", "/api/v1/runtime/preferences/refresh"),
    ]
    assert "schemaId" not in requests[0][2]
    assert "schemaId" not in requests[1][2]["candidates"][0]
    assert refreshed.preferences["grocery.preferred_snack"].value == "potato chips"


@pytest.mark.asyncio
async def test_google_token_provider_mints_for_every_request() -> None:
    minted: list[str] = []

    def fetcher(_request, audience: str) -> str:
        minted.append(audience)
        return f"token-{len(minted)}"

    seen_authorization: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_authorization.append(request.headers["Authorization"])
        return httpx.Response(200, json=snapshot_payload())

    client = MemoryApiClient(
        base_url="http://memory-api",
        token_provider=GoogleIdTokenProvider("https://memory-api", fetcher=fetcher),
        transport=httpx.MockTransport(handler),
    )
    arguments = {
        "user_id": "user-1",
        "session_id": "session-1",
        "app_name": "grocery-app",
        "consumer_domain": "grocery",
        "agent_id": "grocery-agent",
    }
    await client.resolve_preferences(**arguments)
    await client.resolve_preferences(**arguments)

    assert minted == ["https://memory-api", "https://memory-api"]
    assert seen_authorization == ["Bearer token-1", "Bearer token-2"]
