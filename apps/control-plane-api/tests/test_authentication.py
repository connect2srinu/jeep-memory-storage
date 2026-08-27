from __future__ import annotations

import pytest
from control_plane_api.security import AuthenticationError, GoogleIdTokenAuthenticator
from fastapi import Request


def request(authorization: str = "Bearer token") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", authorization.encode())],
        }
    )


@pytest.mark.asyncio
async def test_google_authenticator_accepts_verified_service_account(monkeypatch) -> None:
    authenticator = GoogleIdTokenAuthenticator("https://control-plane-api.example")
    monkeypatch.setattr(
        authenticator,
        "_verify",
        lambda _: {
            "iss": "https://accounts.google.com",
            "sub": "123456",
            "email": "grocery-agent@example.iam.gserviceaccount.com",
        },
    )
    principal = await authenticator.authenticate(request())
    assert principal.principal == "grocery-agent@example.iam.gserviceaccount.com"
    assert principal.claimed_agent_id is None


@pytest.mark.asyncio
async def test_google_authenticator_rejects_unapproved_issuer(monkeypatch) -> None:
    authenticator = GoogleIdTokenAuthenticator("https://control-plane-api.example")
    monkeypatch.setattr(
        authenticator,
        "_verify",
        lambda _: {"iss": "https://attacker.example", "sub": "1", "email": "fake@example"},
    )
    with pytest.raises(AuthenticationError, match="issuer"):
        await authenticator.authenticate(request())
