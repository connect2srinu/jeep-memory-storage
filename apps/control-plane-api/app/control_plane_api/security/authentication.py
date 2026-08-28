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
    claims: dict[str, Any] | None = None


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


class IapJwtAuthenticator:
    """Verify the JWT assertion added by Google Cloud Identity-Aware Proxy."""

    CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"

    def __init__(self, audience: str) -> None:
        if not audience.strip():
            raise ValueError("IAP_JWT_AUDIENCE is required when ADMIN_AUTH_MODE=iap")
        self.audience = audience

    async def authenticate(self, request: Request) -> AuthenticatedPrincipal:
        token = request.headers.get("x-goog-iap-jwt-assertion", "").strip()
        if not token:
            raise AuthenticationError("IAP JWT assertion is required")
        try:
            claims = await asyncio.to_thread(self._verify, token)
        except Exception as exc:
            raise AuthenticationError("IAP JWT verification failed") from exc
        if claims.get("iss") != "https://cloud.google.com/iap":
            raise AuthenticationError("IAP JWT issuer is not allowed")
        subject = str(claims.get("sub", "")).strip()
        principal = str(claims.get("email", "")).strip()
        if not subject or not principal:
            raise AuthenticationError("verified IAP JWT lacks subject or email")
        return AuthenticatedPrincipal(
            subject=subject,
            principal=principal,
            issuer="https://cloud.google.com/iap",
        )

    def _verify(self, token: str) -> dict[str, Any]:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        return id_token.verify_token(
            token,
            GoogleRequest(),
            audience=self.audience,
            certs_url=self.CERTS_URL,
        )


class EntraAccessTokenAuthenticator:
    """Validate tenant-specific Microsoft Entra v2 access tokens for the admin API."""

    def __init__(
        self,
        *,
        tenant_id: str,
        audience: str,
        required_scope: str = "access_as_user",
    ) -> None:
        if not tenant_id.strip() or tenant_id in {"common", "organizations", "consumers"}:
            raise ValueError("ENTRA_TENANT_ID must be a concrete tenant ID")
        if not audience.strip():
            raise ValueError("ENTRA_API_AUDIENCE is required when Entra authentication is enabled")
        self.tenant_id = tenant_id.strip()
        self.audience = audience.strip()
        self.required_scope = required_scope.strip()
        self.issuer = f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"
        self.jwks_url = f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"

    async def authenticate(self, request: Request) -> AuthenticatedPrincipal:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthenticationError("Microsoft Entra Bearer access token is required")
        try:
            claims = await asyncio.to_thread(self._verify, token)
        except Exception as exc:
            raise AuthenticationError("Microsoft Entra access token verification failed") from exc
        if str(claims.get("tid", "")) != self.tenant_id:
            raise AuthenticationError("Microsoft Entra token tenant is not allowed")
        scopes = {value for value in str(claims.get("scp", "")).split() if value}
        if self.required_scope and self.required_scope not in scopes:
            raise AuthenticationError(
                f"Microsoft Entra token lacks delegated scope {self.required_scope}"
            )
        subject = str(claims.get("oid") or claims.get("sub") or "").strip()
        principal = str(
            claims.get("preferred_username") or claims.get("upn") or claims.get("email") or subject
        ).strip()
        if not subject or not principal:
            raise AuthenticationError("verified Microsoft Entra token lacks user identity")
        return AuthenticatedPrincipal(
            subject=subject,
            principal=principal.casefold(),
            issuer=self.issuer,
            claims=claims,
        )

    def _verify(self, token: str) -> dict[str, Any]:
        import jwt

        signing_key = jwt.PyJWKClient(self.jwks_url, cache_keys=True).get_signing_key_from_jwt(
            token
        )
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "tid"]},
        )
