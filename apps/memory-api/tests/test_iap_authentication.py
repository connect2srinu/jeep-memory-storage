from __future__ import annotations

import pytest
from fastapi import Request
from memory_api.security.authentication import AuthenticationError, IapJwtAuthenticator


def request(token: str | None = None) -> Request:
    headers = [] if token is None else [(b"x-goog-iap-jwt-assertion", token.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


@pytest.mark.asyncio
async def test_iap_authenticator_uses_verified_email(monkeypatch) -> None:
    authenticator = IapJwtAuthenticator("/projects/1/global/backendServices/2")
    monkeypatch.setattr(
        authenticator,
        "_verify",
        lambda _: {
            "iss": "https://cloud.google.com/iap",
            "sub": "accounts.google.com:123",
            "email": "admin@example.com",
        },
    )
    principal = await authenticator.authenticate(request("signed"))
    assert principal.principal == "admin@example.com"


@pytest.mark.asyncio
async def test_iap_authenticator_rejects_missing_or_wrong_issuer(monkeypatch) -> None:
    authenticator = IapJwtAuthenticator("/projects/1/global/backendServices/2")
    with pytest.raises(AuthenticationError, match="required"):
        await authenticator.authenticate(request())
    monkeypatch.setattr(
        authenticator,
        "_verify",
        lambda _: {"iss": "https://accounts.google.com", "sub": "1", "email": "a@example.com"},
    )
    with pytest.raises(AuthenticationError, match="issuer"):
        await authenticator.authenticate(request("signed"))
