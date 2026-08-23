from __future__ import annotations

import pytest
from fastapi import Request
from memory_api.security.admin import AdminAuthenticator, AdminRole
from memory_api.security.authentication import AuthenticatedPrincipal, AuthenticationError


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
