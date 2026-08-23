from __future__ import annotations

from typing import Any

import httpx


class MemoryApiClient:
    """Small transport client; it has no Google Memory Bank dependency."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport
        self.timeout = timeout

    def _headers(self, agent_id: str) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {"X-Agent-ID": agent_id}

    async def resolve_preferences(
        self,
        *,
        user_id: str,
        session_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(agent_id),
            transport=self.transport,
            timeout=self.timeout,
        ) as client:
            response = await client.post(
                "/api/v1/runtime/preferences/resolve",
                json={
                    "scope": {
                        "userId": user_id,
                        "appName": app_name,
                        "domain": consumer_domain,
                    },
                    "sessionId": session_id,
                    "agentId": agent_id,
                    "includeProvenance": bool((context or {}).get("includeProvenance", False)),
                },
            )
            response.raise_for_status()
            return response.json()
