"""Slice 4 — the client passes an optional dependentId through the runtime scope."""

from __future__ import annotations

import pytest
from memory_agent.client import ControlPlaneApiClient

RESOLVE_STUB = {
    "agentId": "grocery-agent",
    "scope": {"userId": "u1", "appName": "app", "domain": "grocery"},
    "sessionId": "s",
    "preferences": {},
    "snapshotVersion": "v",
    "policyVersion": "1.0",
    "schemaVersions": {},
    "generatedAt": "2026-01-01T00:00:00Z",
}
MUTATION_STUB = {"status": "updated", "reference": "r", "profileVersion": 1}


def test_scope_includes_dependent_id_only_when_set() -> None:
    assert ControlPlaneApiClient._scope("u1", "app", "grocery") == {
        "userId": "u1",
        "appName": "app",
        "domain": "grocery",
    }
    with_dep = ControlPlaneApiClient._scope("u1", "app", "grocery", "child1")
    assert with_dep["dependentId"] == "child1"


@pytest.mark.asyncio
async def test_resolve_and_update_forward_dependent_id(monkeypatch) -> None:
    client = ControlPlaneApiClient(base_url="http://control-plane")
    captured: dict[str, dict] = {}

    async def fake_request(method, path, *, agent_id, payload):
        captured["payload"] = payload
        return RESOLVE_STUB if path.endswith("/resolve") else MUTATION_STUB

    monkeypatch.setattr(client, "_request", fake_request)

    await client.resolve_preferences(
        user_id="u1",
        session_id="s",
        app_name="app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        dependent_id="child1",
    )
    assert captured["payload"]["scope"]["dependentId"] == "child1"

    await client.update_preference(
        user_id="u1",
        app_name="app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        attribute="grocery.allergies",
        value="peanut",
        dependent_id="child1",
    )
    assert captured["payload"]["scope"]["dependentId"] == "child1"

    # Member-scoped calls carry no dependentId.
    await client.update_preference(
        user_id="u1",
        app_name="app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        attribute="grocery.preferred_snack",
        value="mango chips",
    )
    assert "dependentId" not in captured["payload"]["scope"]

    # A household-member write forwards memberId (the person the write is for).
    await client.update_preference(
        user_id="u1",
        app_name="app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        attribute="grocery.member_allergies",
        value="peanut",
        member_id="kid1",
    )
    assert captured["payload"]["scope"]["memberId"] == "kid1"
    assert "dependentId" not in captured["payload"]["scope"]
