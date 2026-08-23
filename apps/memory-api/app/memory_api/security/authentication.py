from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import Request


class AuthenticationError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    subject: str
    principal: str
    issuer: str
    claimed_agent_id: str | None = None


class AgentAuthenticator(Protocol):
    async def authenticate(self, request: Request) -> AuthenticatedPrincipal: ...


class LocalAgentAuthenticator:
    """Explicit development-only identity supplied through X-Agent-ID."""

    async def authenticate(self, request: Request) -> AuthenticatedPrincipal:
        agent_id = request.headers.get("x-agent-id", "").strip()
        if not agent_id:
            raise AuthenticationError("X-Agent-ID is required when AUTH_ENABLED=false")
        return AuthenticatedPrincipal(
            subject=f"local:{agent_id}",
            principal=f"local:{agent_id}",
            issuer="local-development",
            claimed_agent_id=agent_id,
        )


class GoogleIdTokenAuthenticator:
    def __init__(self, audience: str) -> None:
        if not audience.strip():
            raise ValueError("GOOGLE_ID_TOKEN_AUDIENCE is required when authentication is enabled")
        self.audience = audience

    async def authenticate(self, request: Request) -> AuthenticatedPrincipal:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthenticationError("Bearer ID token is required")
        try:
            claims = await asyncio.to_thread(self._verify, token)
        except Exception as exc:
            raise AuthenticationError("Google ID token verification failed") from exc
        issuer = str(claims.get("iss", ""))
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            raise AuthenticationError("Google ID token issuer is not allowed")
        subject = str(claims.get("sub", "")).strip()
        principal = str(claims.get("email", "")).strip()
        if not subject or not principal:
            raise AuthenticationError("verified token lacks subject or service-account email")
        return AuthenticatedPrincipal(subject=subject, principal=principal, issuer=issuer)

    def _verify(self, token: str) -> dict[str, Any]:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        return id_token.verify_oauth2_token(token, GoogleRequest(), self.audience)
