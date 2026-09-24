"""Minimal async client for the Control Plane runtime API (long-term memory).

Self-contained on purpose: the memory-agent image only copies ``apps/memory-agent``, so it cannot
import the reference-agent package. This reuses the same runtime-API contract (``X-Agent-ID`` /
Bearer auth, ``{userId, appName, domain}`` scope) and keeps only the calls this agent needs:
resolve the snapshot, write/forget/move preferences, and manage household members.
"""

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
    writable_preference_details: tuple[dict[str, Any], ...] = Field(
        default=(), alias="writablePreferenceDetails"
    )
    approved_topics: tuple[str, ...] = Field(default=(), alias="approvedTopics")
    approved_topic_details: tuple[dict[str, Any], ...] = Field(
        default=(), alias="approvedTopicDetails"
    )
    household_id: str | None = Field(default=None, alias="householdId")
    household_members: tuple[dict[str, Any], ...] = Field(default=(), alias="householdMembers")
    acting_member_id: str | None = Field(default=None, alias="actingMemberId")
    resolved_member_id: str | None = Field(default=None, alias="resolvedMemberId")
    generated_at: str = Field(alias="generatedAt")


class RuntimeMutation(ApiModel):
    # Written: updated / accepted / added / merged / moved / forgotten / exists. Not written:
    # needs_confirmation (ask confirmationPrompt), ambiguous (ask which candidate), not_allowed.
    status: str
    reference: str | None = None
    profile_version: int | None = Field(default=None, alias="profileVersion")
    member_id: str | None = Field(default=None, alias="memberId")
    confirmation_prompt: str | None = Field(default=None, alias="confirmationPrompt")
    candidates: tuple[dict[str, Any], ...] = ()
    message: str | None = None


class ControlPlaneApiError(RuntimeError):
    """Actionable runtime API failure safe to surface in ADK traces."""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(f"Control Plane API request failed: {code}: {message} (HTTP {status_code})")


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


class ControlPlaneApiClient:
    """Typed async client for the Control Plane API runtime plane (resolve + update)."""

    def __init__(
        self,
        *,
        base_url: str,
        token_provider: TokenProvider | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider or StaticTokenProvider(None)
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
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        headers = await self._headers(agent_id)
        if correlation_id:
            # The control plane logs this id on its side, so both logs can be joined.
            headers["X-Correlation-ID"] = correlation_id
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
        ) as client:
            response = await client.request(method, path, json=payload)
            if response.is_error:
                try:
                    error = response.json()
                except ValueError:
                    error = {}
                raise ControlPlaneApiError(
                    status_code=response.status_code,
                    code=str(error.get("code") or f"HTTP_{response.status_code}"),
                    message=str(error.get("message") or response.reason_phrase),
                )
            return response.json()

    @staticmethod
    def _scope(
        user_id: str,
        app_name: str,
        consumer_domain: str,
        member_id: str | None = None,
    ) -> dict[str, str]:
        scope = {"userId": user_id, "appName": app_name, "domain": consumer_domain}
        if member_id:
            scope["memberId"] = member_id
        return scope

    async def resolve_preferences(
        self,
        *,
        user_id: str,
        session_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        include_provenance: bool = False,
        member_id: str | None = None,
    ) -> EffectivePreferenceSnapshot:
        payload = await self._request(
            "POST",
            "/api/v1/runtime/preferences/resolve",
            agent_id=agent_id,
            payload={
                "scope": self._scope(user_id, app_name, consumer_domain, member_id),
                "sessionId": session_id,
                "agentId": agent_id,
                "includeProvenance": include_provenance,
            },
        )
        return EffectivePreferenceSnapshot.model_validate(payload)

    async def write_dynamic_memory(
        self,
        *,
        user_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        topic: str,
        value: Any,
        confidence: float = 1.0,
        correlation_id: str | None = None,
    ) -> RuntimeMutation:
        payload = await self._request(
            "POST",
            "/api/v1/runtime/memory/dynamic",
            agent_id=agent_id,
            payload={
                "scope": self._scope(user_id, app_name, consumer_domain),
                "topic": topic,
                "value": value,
                "confidence": confidence,
            },
            correlation_id=correlation_id,
        )
        return RuntimeMutation.model_validate(payload)

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
        member_id: str | None = None,
        member_name: str | None = None,
        relationship: str | None = None,
        confirmed: bool = False,
        correlation_id: str | None = None,
    ) -> RuntimeMutation:
        body: dict[str, Any] = {
            "scope": self._scope(user_id, app_name, consumer_domain, member_id),
            "value": value,
        }
        if schema_id is not None:
            body["schemaId"] = schema_id
        if member_name:
            body["memberName"] = member_name
        if relationship:
            body["relationship"] = relationship
        if confirmed:
            body["confirmed"] = True
        payload = await self._request(
            "PUT",
            f"/api/v1/runtime/preferences/{quote(attribute, safe='.')}",
            agent_id=agent_id,
            payload=body,
            correlation_id=correlation_id,
        )
        return RuntimeMutation.model_validate(payload)

    async def forget_preference(
        self,
        *,
        user_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        attribute: str,
        member_id: str | None = None,
    ) -> RuntimeMutation:
        payload = await self._request(
            "POST",
            f"/api/v1/runtime/preferences/{quote(attribute, safe='.')}/forget",
            agent_id=agent_id,
            payload={"scope": self._scope(user_id, app_name, consumer_domain, member_id)},
        )
        return RuntimeMutation.model_validate(payload)

    async def move_preference(
        self,
        *,
        user_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        attribute: str,
        from_member_id: str | None,
        to_member_id: str,
        confirmed: bool = False,
    ) -> RuntimeMutation:
        payload = await self._request(
            "POST",
            f"/api/v1/runtime/preferences/{quote(attribute, safe='.')}/move",
            agent_id=agent_id,
            payload={
                "scope": self._scope(user_id, app_name, consumer_domain, from_member_id),
                "toMemberId": to_member_id,
                "confirmed": confirmed,
            },
        )
        return RuntimeMutation.model_validate(payload)

    async def add_household_member(
        self,
        *,
        user_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        name: str,
        relationship: str | None = None,
        member_id: str | None = None,
        confirmed: bool = False,
    ) -> RuntimeMutation:
        body: dict[str, Any] = {
            "scope": self._scope(user_id, app_name, consumer_domain),
            "name": name,
            "confirmed": confirmed,
        }
        if relationship:
            body["relationship"] = relationship
        if member_id:
            body["memberId"] = member_id
        payload = await self._request(
            "POST", "/api/v1/runtime/household/members", agent_id=agent_id, payload=body
        )
        return RuntimeMutation.model_validate(payload)

    async def update_household_member(
        self,
        *,
        user_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        member_id: str,
        display_name: str | None = None,
        minor: bool | None = None,
    ) -> RuntimeMutation:
        body: dict[str, Any] = {"scope": self._scope(user_id, app_name, consumer_domain)}
        if display_name:
            body["displayName"] = display_name
        if minor is not None:
            body["minor"] = minor
        payload = await self._request(
            "PATCH",
            f"/api/v1/runtime/household/members/{quote(member_id, safe='')}",
            agent_id=agent_id,
            payload=body,
        )
        return RuntimeMutation.model_validate(payload)

    async def merge_household_members(
        self,
        *,
        user_id: str,
        app_name: str,
        consumer_domain: str,
        agent_id: str,
        keep_member_id: str,
        merge_member_id: str,
        confirmed: bool = False,
    ) -> RuntimeMutation:
        payload = await self._request(
            "POST",
            "/api/v1/runtime/household/members/merge",
            agent_id=agent_id,
            payload={
                "scope": self._scope(user_id, app_name, consumer_domain),
                "keepMemberId": keep_member_id,
                "mergeMemberId": merge_member_id,
                "confirmed": confirmed,
            },
        )
        return RuntimeMutation.model_validate(payload)
