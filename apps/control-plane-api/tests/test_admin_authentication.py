from __future__ import annotations

import pytest
from control_plane_api.security.admin import AdminAuthenticator, AdminRole
from control_plane_api.security.authentication import (
    AuthenticatedPrincipal,
    AuthenticationError,
    EntraAccessTokenAuthenticator,
)
from fastapi import Request


class VerifiedAuthenticator:
    async def authenticate(self, _request: Request) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            subject="google-subject",
            principal="owner@example.com",
            issuer="https://accounts.google.com",
        )


def request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


@pytest.mark.asyncio
async def test_verified_admin_uses_trusted_role_binding() -> None:
    authenticator = AdminAuthenticator(
        auth_enabled=True,
        google_authenticator=VerifiedAuthenticator(),
        role_bindings_json=(
            '{"owner@example.com":{"roles":["SCHEMA_OWNER"],"domains":["customer"]}}'
        ),
    )
    principal = await authenticator.authenticate(request())
    assert principal.roles == frozenset({AdminRole.SCHEMA_OWNER})
    assert principal.domain_ids == frozenset({"customer"})


@pytest.mark.asyncio
async def test_verified_admin_without_binding_is_rejected() -> None:
    authenticator = AdminAuthenticator(
        auth_enabled=True,
        google_authenticator=VerifiedAuthenticator(),
    )
    with pytest.raises(AuthenticationError, match="no role binding"):
        await authenticator.authenticate(request())


class VerifiedEntraAuthenticator:
    async def authenticate(self, _request: Request) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            subject="entra-object-id",
            principal="platform.admin@example.com",
            issuer="https://login.microsoftonline.com/tenant-id/v2.0",
            claims={"roles": ["Platform.Admin"]},
        )


@pytest.mark.asyncio
async def test_entra_app_role_maps_to_internal_platform_role() -> None:
    authenticator = AdminAuthenticator(
        auth_enabled=True,
        google_authenticator=VerifiedEntraAuthenticator(),
        token_role_mapping={
            "Platform.Admin": AdminRole.PLATFORM_ADMIN,
            "Platform.User": AdminRole.PLATFORM_USER,
        },
    )
    principal = await authenticator.authenticate(request())
    assert principal.roles == frozenset({AdminRole.PLATFORM_ADMIN})
    assert principal.principal == "platform.admin@example.com"


@pytest.mark.asyncio
async def test_entra_token_requires_configured_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    authenticator = EntraAccessTokenAuthenticator(
        tenant_id="tenant-id", audience="api-client-id", required_scope="access_as_user"
    )
    monkeypatch.setattr(
        authenticator,
        "_verify",
        lambda _token: {
            "tid": "tenant-id",
            "oid": "user-object-id",
            "preferred_username": "User@Example.com",
            "scp": "openid profile",
        },
    )
    bearer_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", b"Bearer token")],
        }
    )
    with pytest.raises(AuthenticationError, match="lacks delegated scope"):
        await authenticator.authenticate(bearer_request)
