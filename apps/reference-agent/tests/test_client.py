import httpx
import pytest
from reference_agent.client import MemoryApiClient


@pytest.mark.asyncio
async def test_resolve_uses_api_contract_and_bearer_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/runtime/preferences/resolve"
        assert request.headers["Authorization"] == "Bearer test-token"
        payload = request.content.decode()
        assert '"userId":"user-1"' in payload
        assert '"appName":"grocery-app"' in payload
        return httpx.Response(200, json={"snapshotVersion": "v1", "preferences": {}})

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
    assert result["snapshotVersion"] == "v1"
