"""The agent logs every memory decision, masking health, sensitive, and rejected values."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from memory_agent import agent as memory_agent
from memory_agent.client import ControlPlaneApiError, RuntimeMutation

SNAPSHOT = {
    "writablePreferenceDetails": [
        {"attribute": "familygrocery.dislikes", "level": "household_member", "health": False},
        {"attribute": "familygrocery.allergies", "level": "household_member", "health": True},
    ],
    "approvedTopicDetails": [],
}


def tool_context() -> SimpleNamespace:
    return SimpleNamespace(
        state={memory_agent.SNAPSHOT_STATE_KEY: SNAPSHOT},
        session=SimpleNamespace(user_id="priya", id="s1"),
        user_id="priya",
    )


def decisions(caplog) -> list[dict]:
    return [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "memory_agent.memory_decision"
    ]


@pytest.fixture
def control_plane(monkeypatch):
    """A fake client whose update_preference returns or raises what the test sets."""
    outcome: dict[str, object] = {}

    class FakeClient:
        async def update_preference(self, **kwargs: object) -> RuntimeMutation:
            outcome["correlation_id"] = kwargs["correlation_id"]
            if isinstance(outcome["result"], Exception):
                raise outcome["result"]
            return outcome["result"]

    async def no_refresh(tool_context, mutation, member_id=None):
        return {}

    monkeypatch.setattr(memory_agent, "build_control_plane_api_client", FakeClient)
    monkeypatch.setattr(memory_agent, "_result", no_refresh)
    return outcome


@pytest.mark.asyncio
async def test_saved_value_is_logged_with_its_key_type_and_version(control_plane, caplog) -> None:
    caplog.set_level(logging.INFO)
    control_plane["result"] = RuntimeMutation(
        status="updated",
        reference="familygrocery-member-preferences-v1:familygrocery.dislikes",
        profileVersion=3,
        memberId="mbr_1",
    )
    await memory_agent.save_preference("familygrocery.dislikes", "olives", tool_context())
    [event] = decisions(caplog)
    assert (event["decision"], event["key"], event["value"]) == (
        "updated",
        "familygrocery.dislikes",
        "olives",
    )
    assert (event["preference_type"], event["level"], event["value_version"]) == (
        "canonical",
        "household_member",
        3,
    )
    assert event["reference"].startswith("familygrocery-member-preferences-v1")
    # The same id is sent to the control plane, which logs it on its memory_decision event.
    assert event["correlation_id"] == control_plane["correlation_id"]


@pytest.mark.asyncio
async def test_health_and_rejected_values_are_masked(control_plane, caplog) -> None:
    caplog.set_level(logging.INFO)
    control_plane["result"] = RuntimeMutation(status="needs_confirmation", memberId="mbr_1")
    await memory_agent.save_preference("familygrocery.allergies", "peanuts", tool_context())

    control_plane["result"] = ControlPlaneApiError(
        status_code=400, code="INVALID_ARGUMENT", message="contains restricted content (pii_ssn)"
    )
    with pytest.raises(ControlPlaneApiError):
        await memory_agent.save_preference(
            "familygrocery.dislikes", "my SSN is 123-45-6789", tool_context()
        )

    pending, rejected = decisions(caplog)
    assert (pending["decision"], pending["value"], pending["health"]) == (
        "needs_confirmation",
        "***",
        True,
    )
    assert (rejected["decision"], rejected["value"], rejected["http_status"]) == (
        "rejected",
        "***",
        400,
    )
    assert "peanuts" not in caplog.text and "123-45-6789" not in caplog.text


@pytest.mark.asyncio
async def test_model_declines_are_recorded(caplog) -> None:
    caplog.set_level(logging.INFO)
    result = await memory_agent.record_memory_decision(
        "training for a marathon, call 555-123-4567", "no attribute or topic fits", tool_context()
    )
    await memory_agent.record_memory_decision(
        "is pregnant", "not something we store", tool_context(), sensitive=True
    )
    assert result == {"recorded": True, "saved": False}
    plain, sensitive = decisions(caplog)
    assert plain["decision"] == "declined" and plain["reason"] == "no attribute or topic fits"
    assert plain["value"] == "training for a marathon, call ***"
    assert sensitive["value"] == "***" and sensitive["sensitive"] is True
