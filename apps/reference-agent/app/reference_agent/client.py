from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from google.auth.transport.requests import Request
from google.oauth2.id_token import fetch_id_token
from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class RuntimeScope(ApiModel):
    user_id: str = Field(alias="userId")
    app_name: str = Field(alias="appName")
    domain: str


class PreferenceValue(ApiModel):
    value: Any
    source: str
    owner_domain: str = Field(alias="ownerDomain")
    resolution_reason: str = Field(alias="resolutionReason")
    provenance: dict[str, Any] | None = None


class EffectivePreferenceSnapshot(ApiModel):
    agent_id: str = Field(alias="agentId")
    scope: RuntimeScope
    session_id: str = Field(alias="sessionId")
    preferences: dict[str, PreferenceValue]
    snapshot_version: str = Field(alias="snapshotVersion")
    policy_version: str = Field(alias="policyVersion")
    schema_versions: dict[str, str] = Field(alias="schemaVersions")
    writable_preferences: tuple[str, ...] = Field(default=(), alias="writablePreferences")
    generated_at: str = Field(alias="generatedAt")


class PreferenceCandidate(ApiModel):
    schema_id: str | None = Field(default=None, alias="schemaId")
    attribute: str
    value: Any


class RuntimeMutation(ApiModel):
    status: str
    reference: str
    profile_version: int | None = Field(default=None, alias="profileVersion")


class TokenProvider(Protocol):
    async def get_token(self) -> str | None:
        """Return a bearer token, or None when local agent-ID auth is enabled."""


class StaticTokenProvider:
    def __init__(self, token: str | None) -> None:
        self._token = token

    async def get_token(self) -> str | None:
        return self._token


class GoogleIdTokenProvider:
    """Mint a Google ID token per request so long-lived agents do not use stale tokens."""

    def __init__(
        self,
        audience: str,
        *,
        fetcher: Callable[[Request, str], str] = fetch_id_token,
    ) -> None:
        if not audience:
            raise ValueError("Google ID-token audience must not be empty")
        self._audience = audience
        self._fetcher = fetcher

    async def get_token(self) -> str:
        return await asyncio.to_thread(self._fetcher, Request(), self._audience)


class MemoryApiClient:
    """Typed async client for the Shared Memory runtime API."""

    def __init__(
        self,
        *,
        base_url: str,
        token_provider: TokenProvider | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        if token_provider is not None and token is not None:
            raise ValueError("Configure token_provider or token, not both")
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider or StaticTokenProvider(token)
        self.transport = transport
        self.timeout = timeout

    async def _headers(self, agent_id: str) -> dict[str, str]:
        token = await self.token_provider.get_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {"X-Agent-ID": agent_id}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        agent_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=await self._headers(agent_id),
            transport=self.transport,
            timeout=self.timeout,
        ) as client:
            response = await client.request(method, path, json=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _scope(user_id: str, app_name: str, consumer_domain: str) -> dict[str, str]:
        return {"userId": user_id, "appName": app_name, "domain": consumer_domain}

    async def _resolve(
        self,
        path: str,
        *,
        user_id: str,
        session_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        include_provenance: bool = False,
    ) -> EffectivePreferenceSnapshot:
        payload = await self._request(
            "POST",
            path,
            agent_id=agent_id,
            payload={
                "scope": self._scope(user_id, app_name, consumer_domain),
                "sessionId": session_id,
                "agentId": agent_id,
                "includeProvenance": include_provenance,
            },
        )
        return EffectivePreferenceSnapshot.model_validate(payload)

    async def resolve_preferences(
        self,
        *,
        user_id: str,
        session_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        include_provenance: bool = False,
    ) -> EffectivePreferenceSnapshot:
        return await self._resolve(
            "/api/v1/runtime/preferences/resolve",
            user_id=user_id,
            session_id=session_id,
            app_name=app_name,
            consumer_domain=consumer_domain,
            agent_id=agent_id,
            include_provenance=include_provenance,
        )

    async def refresh_preferences(
        self,
        *,
        user_id: str,
        session_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        include_provenance: bool = False,
    ) -> EffectivePreferenceSnapshot:
        return await self._resolve(
            "/api/v1/runtime/preferences/refresh",
            user_id=user_id,
            session_id=session_id,
            app_name=app_name,
            consumer_domain=consumer_domain,
            agent_id=agent_id,
            include_provenance=include_provenance,
        )

    async def update_preference(
        self,
        *,
        user_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        attribute: str,
        value: Any,
        schema_id: str | None = None,
    ) -> RuntimeMutation:
        body = {
            "scope": self._scope(user_id, app_name, consumer_domain),
            "value": value,
        }
        if schema_id is not None:
            body["schemaId"] = schema_id
        payload = await self._request(
            "PUT",
            f"/api/v1/runtime/preferences/{quote(attribute, safe='.')}",
            agent_id=agent_id,
            payload=body,
        )
        return RuntimeMutation.model_validate(payload)

    async def ingest_event(
        self,
        *,
        user_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        text: str,
        candidates: list[PreferenceCandidate],
    ) -> RuntimeMutation:
        payload = await self._request(
            "POST",
            "/api/v1/runtime/memory/events",
            agent_id=agent_id,
            payload={
                "scope": self._scope(user_id, app_name, consumer_domain),
                "text": text,
                "candidates": [
                    candidate.model_dump(by_alias=True, mode="json", exclude_none=True)
                    for candidate in candidates
                ],
            },
        )
        return RuntimeMutation.model_validate(payload)
