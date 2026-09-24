"""The client passes an optional memberId through the runtime scope (household model)."""

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


def test_scope_includes_member_id_only_when_set() -> None:
    assert ControlPlaneApiClient._scope("u1", "app", "grocery") == {
        "userId": "u1",
        "appName": "app",
        "domain": "grocery",
    }
    with_member = ControlPlaneApiClient._scope("u1", "app", "grocery", "kid1")
    assert with_member["memberId"] == "kid1"


@pytest.mark.asyncio
async def test_resolve_and_update_forward_member_id(monkeypatch) -> None:
    client = ControlPlaneApiClient(base_url="http://control-plane")
    captured: dict[str, dict] = {}

    async def fake_request(method, path, *, agent_id, payload, correlation_id=None):
        captured["payload"] = payload
        return RESOLVE_STUB if path.endswith("/resolve") else MUTATION_STUB

    monkeypatch.setattr(client, "_request", fake_request)

    await client.resolve_preferences(
        user_id="u1",
        session_id="s",
        app_name="app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        member_id="kid1",
    )
    assert captured["payload"]["scope"]["memberId"] == "kid1"

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

    # Member/household-level calls carry no memberId.
    await client.update_preference(
        user_id="u1",
        app_name="app",
        consumer_domain="grocery",
        agent_id="grocery-agent",
        attribute="grocery.preferred_snack",
        value="mango chips",
    )
    assert "memberId" not in captured["payload"]["scope"]
    assert "confirmed" not in captured["payload"]


@pytest.mark.asyncio
async def test_reference_writes_and_confirmation_round_trip(monkeypatch) -> None:
    client = ControlPlaneApiClient(base_url="http://control-plane")
    calls: list[tuple[str, str, dict]] = []
    proposal = {
        "status": "needs_confirmation",
        "memberId": "mbr_1",
        "confirmationPrompt": "Should I add Ryan (your son) to your household?",
    }

    async def fake_request(method, path, *, agent_id, payload, correlation_id=None):
        calls.append((method, path, payload))
        return proposal

    monkeypatch.setattr(client, "_request", fake_request)
    common = {
        "user_id": "u1",
        "app_name": "app",
        "consumer_domain": "familygrocery",
        "agent_id": "a",
    }

    result = await client.update_preference(
        **common,
        attribute="familygrocery.dislikes",
        value="peanuts",
        member_name="Ryan",
        relationship="son",
    )
    assert result.status == "needs_confirmation" and result.member_id == "mbr_1"
    assert result.confirmation_prompt.startswith("Should I add Ryan")
    body = calls[-1][2]
    assert (body["memberName"], body["relationship"]) == ("Ryan", "son")

    await client.update_preference(
        **common,
        attribute="familygrocery.dislikes",
        value="peanuts",
        member_id="mbr_1",
        confirmed=True,
    )
    assert calls[-1][2]["confirmed"] is True and calls[-1][2]["scope"]["memberId"] == "mbr_1"

    await client.add_household_member(**common, name="Maya", relationship="daughter")
    assert calls[-1][:2] == ("POST", "/api/v1/runtime/household/members")
    await client.merge_household_members(
        **common, keep_member_id="m1", merge_member_id="m2", confirmed=True
    )
    assert calls[-1][2]["keepMemberId"] == "m1" and calls[-1][2]["confirmed"] is True
    await client.move_preference(
        **common,
        attribute="familygrocery.dislikes",
        from_member_id="m2",
        to_member_id="m1",
    )
    assert calls[-1][1].endswith("/familygrocery.dislikes/move")
    await client.forget_preference(**common, attribute="familygrocery.allergies", member_id="m1")
    assert calls[-1][1].endswith("/familygrocery.allergies/forget")
    await client.update_household_member(**common, member_id="m1", minor=False)
    assert calls[-1][0] == "PATCH" and calls[-1][2]["minor"] is False
