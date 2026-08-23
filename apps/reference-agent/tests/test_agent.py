from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import reference_agent.agent as agent_module
from reference_agent.client import (
    EffectivePreferenceSnapshot,
    PreferenceCandidate,
    RuntimeMutation,
)


def make_snapshot(value: str, version: str) -> EffectivePreferenceSnapshot:
    return EffectivePreferenceSnapshot.model_validate(
        {
            "agentId": "grocery-agent",
            "scope": {
                "userId": "user-1",
                "appName": "grocery_shared_preferences",
                "domain": "grocery",
            },
            "sessionId": "session-1",
            "preferences": {
                "grocery.preferred_snack": {
                    "value": value,
                    "source": "MEMORY_PROFILE",
                    "ownerDomain": "grocery",
                    "resolutionReason": "DOMAIN_AUTHORITY",
                }
            },
            "snapshotVersion": version,
            "policyVersion": "p1",
            "schemaVersions": {"grocery-preferences-v1": "1"},
            "generatedAt": "2026-08-22T00:00:00Z",
        }
    )


@dataclass
class FakeSession:
    id: str = "session-1"
    user_id: str = "user-1"


@dataclass
class FakeContext:
    session: FakeSession = field(default_factory=FakeSession)
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def user_id(self) -> str:
        return self.session.user_id


class FakeLlmRequest:
    def __init__(self) -> None:
        self.instructions: list[str] = []

    def append_instructions(self, instructions: list[str]) -> list:
        self.instructions.extend(instructions)
        return []


class FakeMemoryClient:
    def __init__(self) -> None:
        self.value = "mango chips"
        self.resolve_calls = 0
        self.refresh_calls = 0
        self.updates: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def resolve_preferences(self, **_kwargs) -> EffectivePreferenceSnapshot:
        self.resolve_calls += 1
        return make_snapshot(self.value, "v1")

    async def refresh_preferences(self, **_kwargs) -> EffectivePreferenceSnapshot:
        self.refresh_calls += 1
        return make_snapshot(self.value, f"v{self.refresh_calls + 1}")

    async def update_preference(self, **kwargs) -> RuntimeMutation:
        self.updates.append(kwargs)
        self.value = kwargs["value"]
        return RuntimeMutation(status="accepted", reference="update-1", profile_version=2)

    async def ingest_event(
        self, *, candidates: list[PreferenceCandidate], **kwargs
    ) -> RuntimeMutation:
        self.events.append({**kwargs, "candidates": candidates})
        self.value = str(candidates[0].value)
        return RuntimeMutation(status="accepted", reference="event-1", profile_version=3)


@pytest.mark.asyncio
async def test_phase_5_session_context_update_and_refresh(monkeypatch) -> None:
    client = FakeMemoryClient()
    monkeypatch.setattr(agent_module, "build_memory_api_client", lambda: client)
    context = FakeContext()

    await agent_module.initialize_preference_snapshot(context)
    await agent_module.initialize_preference_snapshot(context)
    assert client.resolve_calls == 1
    assert (await agent_module.get_user_preferences(context))["snapshotVersion"] == "v1"
    assert client.resolve_calls == 1

    llm_request = FakeLlmRequest()
    await agent_module.inject_preference_snapshot(context, llm_request)
    assert "mango chips" in llm_request.instructions[0]

    result = await agent_module.update_user_preference(
        "grocery.preferred_snack",
        "grocery-preferences-v1",
        "potato chips",
        context,
    )
    assert result["mutation"]["status"] == "accepted"
    assert result["snapshot"]["preferences"]["grocery.preferred_snack"]["value"] == ("potato chips")
    assert client.refresh_calls == 1

    refreshed = await agent_module.refresh_user_preferences(context)
    assert refreshed["snapshotVersion"] == "v3"
    assert client.refresh_calls == 2


@pytest.mark.asyncio
async def test_event_refreshes_only_after_success(monkeypatch) -> None:
    client = FakeMemoryClient()
    monkeypatch.setattr(agent_module, "build_memory_api_client", lambda: client)
    context = FakeContext()

    result = await agent_module.submit_preference_event(
        "I prefer pretzels.",
        "grocery.preferred_snack",
        "grocery-preferences-v1",
        "pretzels",
        context,
    )

    assert client.events[0]["candidates"][0].attribute == "grocery.preferred_snack"
    assert result["snapshot"]["preferences"]["grocery.preferred_snack"]["value"] == "pretzels"
    assert client.refresh_calls == 1


@pytest.mark.asyncio
async def test_failed_update_does_not_replace_or_refresh_snapshot(monkeypatch) -> None:
    class FailingClient(FakeMemoryClient):
        async def update_preference(self, **kwargs) -> RuntimeMutation:
            raise RuntimeError("update rejected")

    client = FailingClient()
    monkeypatch.setattr(agent_module, "build_memory_api_client", lambda: client)
    context = FakeContext()
    await agent_module.initialize_preference_snapshot(context)
    original = context.state[agent_module.SNAPSHOT_STATE_KEY]

    with pytest.raises(RuntimeError, match="update rejected"):
        await agent_module.update_user_preference(
            "grocery.preferred_snack",
            "grocery-preferences-v1",
            "potato chips",
            context,
        )

    assert client.refresh_calls == 0
    assert context.state[agent_module.SNAPSHOT_STATE_KEY] == original


def test_reference_agent_has_no_memory_bank_sdk_imports() -> None:
    package = Path(agent_module.__file__).parent
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    forbidden = ("google.cloud.aiplatform", "vertexai", "agentplatform", "MemoryBank")
    assert not any(name in source for name in forbidden)
