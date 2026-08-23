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

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def resolve_preferences(
        self,
        *,
        user_id: str,
        session_id: str,
        consumer_domain: str,
        agent_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            transport=self.transport,
            timeout=self.timeout,
        ) as client:
            response = await client.post(
                "/v1/memory/context/resolve",
                json={
                    "userId": user_id,
                    "sessionId": session_id,
                    "consumerDomain": consumer_domain,
                    "agentId": agent_id,
                    "context": context or {},
                },
            )
            response.raise_for_status()
            return response.json()
